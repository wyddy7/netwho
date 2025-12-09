import asyncio
import datetime
from loguru import logger
from aiogram import Bot
from app.infrastructure.supabase.client import get_supabase
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.services.user_service import user_service
from app.schemas import RecallSettings
from app.config import settings
from app.prompts_loader import get_prompt

class RecallService:
    def __init__(self):
        self.supabase = get_supabase()

    async def get_random_contacts_for_user(self, user_id: int, limit: int = 3):
        """
        Теперь выбирает не чисто случайно, а с приоритетом "давно забытых".
        """
        try:
            # 1. Сначала пробуем получить самые старые по last_interaction (NULLS FIRST)
            # Мы делаем это простым запросом, а не RPC, чтобы контролировать сортировку.
            # (Хотя RPC тоже можно было бы обновить)
            
            response = self.supabase.table("contacts")\
                .select("id, name, summary, meta, last_interaction, created_at")\
                .eq("user_id", user_id)\
                .eq("is_archived", False)\
                .order("last_interaction", nullsfirst=True)\
                .limit(20)\
                .execute()
                
            candidates = response.data
            
            if not candidates:
                return []
                
            # 2. Из топ-20 "кандидатов на забвение" выбираем случайных N
            import random
            selected = random.sample(candidates, min(len(candidates), limit))
            
            return selected
            
        except Exception as e:
            logger.error(f"Error getting priority contacts for {user_id}: {e}")
            return []

    async def generate_recall_message(self, contacts: list, bio: str = None, focus: str = None) -> str:
        """
        Генерирует стратегический совет по нетворку на основе списка контактов.
        """
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        contacts_str = "\n".join([
            f"- ID: {get_val(c, 'id', 'N/A')}\n  Name: {get_val(c, 'name', 'N/A')}\n  Summary: {get_val(c, 'summary', 'N/A')}\n  Meta: {get_val(c, 'meta', {})}"
            for c in contacts
        ])

        system_prompt = get_prompt("recall_advisor")
        
        # Добавляем контекст пользователя
        user_context = ""
        if bio:
            user_context += f"\nUSER BIO (WHO AM I): {bio}"
        if focus:
            user_context += f"\nCURRENT FOCUS/GOAL: {focus}"
            
        user_content = f"{user_context}\n\nContacts List:\n{contacts_str}"

        try:
            response = await ai_service.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            content = response.choices[0].message.content.strip()
            
            # Очистка
            content = content.replace("**", "")
            if content.startswith("```html"): content = content[7:]
            if content.endswith("```"): content = content[:-3]
                
            return content.strip()
        except Exception as e:
            logger.error(f"Error generating recall message: {e}")
            return "Не смог придумать повод. Попробуй позже."

    async def process_recalls(self, bot: Bot):
        """
        Основной цикл: берет пользователей и шлет напоминания.
        """
        logger.info("Starting Active Recall process...")
        try:
            # 1. Получаем всех пользователей со всеми полями
            users_response = self.supabase.table("users").select("*").execute()
            users = users_response.data
            
            if not users:
                return

            # Текущий день недели (0=Mon, 6=Sun)
            now = datetime.datetime.now()
            today_weekday = now.weekday()
            current_date_str = now.strftime("%Y-%m-%d")
            
            count = 0
            for user in users:
                user_id = user['id']
                
                # Проверка настроек
                rs = user.get('recall_settings') or {}
                
                # 1. Проверка Enabled
                if not rs.get('enabled', True):
                    continue
                
                # 2. Проверка Дня Недели (User settings)
                days = rs.get('days', [4])

                # --- FREEMIUM CHECK (1 Day Limit) ---
                is_pro = await user_service.is_pro(user_id)
                if not is_pro:
                    # Allow only 1 day per week.
                    # If user has multiple days set (e.g. from before), we accept only the FIRST one.
                    active_days = sorted(days)
                    if active_days:
                        allowed_day = active_days[0]
                        if today_weekday != allowed_day:
                             logger.debug(f"Free user {user_id} has days {days}, but allowed only {allowed_day}. Today {today_weekday}. Skip.")
                             continue
                # ------------------------------------
                
                if today_weekday not in days:
                    logger.debug(f"Day mismatch for user {user_id}. Today: {today_weekday}, Target: {days}")
                    continue
                
                # 3. Latch (Защелка): Не отправлять, если уже отправляли сегодня
                last_sent = rs.get('last_sent_date')
                if last_sent == current_date_str:
                    continue
                
                # 4. Проверка Времени (С окном)
                # Формат времени: "15:00"
                user_time_str = rs.get('time', '15:00')
                try:
                    uh, um = map(int, user_time_str.split(':'))
                    user_time = now.replace(hour=uh, minute=um, second=0, microsecond=0)
                except Exception:
                    user_time = now.replace(hour=15, minute=0, second=0, microsecond=0) # Default
                
                # Debug logs
                logger.debug(f"Checking recall for user {user_id}. Now: {now}, Target: {user_time}")
                
                # Окно: [user_time, user_time + 15 min]
                # Если сейчас 15:05, а юзер хотел 15:00 -> Отправляем.
                # Если сейчас 14:59 -> Ждем.
                # Если сейчас 15:20 -> Опоздали (но в следующий раз скорректируем частоту чека)
                
                diff_minutes = (now - user_time).total_seconds() / 60
                
                logger.debug(f"Diff minutes: {diff_minutes}")

                # Допускаем отправку, если мы опоздали не более чем на 59 минут (в рамках часа)
                # Или, если мы запускаем каждую минуту, то 0 <= diff <= 2.
                # Но для надежности (вдруг бот лежал) берем окно 60 минут.
                # Если юзер поставил 15:00, мы можем отправить в 15:00...15:59.
                if not (0 <= diff_minutes < 60):
                   logger.debug(f"Time mismatch for user {user_id}. Skipping.")
                   continue
                
                # 2. Берем БАТЧ контактов (3-5 штук) для анализа
                contacts = await self.get_random_contacts_for_user(user_id, limit=4)
                if not contacts:
                    # Если контактов нет, а напоминание нужно отправить -> шлем алерт один раз
                    # Но чтобы не спамить, можно проверить, отправляли ли мы уже такой алерт?
                    # Пока просто скипнем, но с логом.
                    logger.warning(f"User {user_id} has no contacts for recall.")
                    # TODO: Можно отправить сообщение юзеру: "Добавьте контакты, чтобы получать напоминания!"
                    continue

                # 3. Генерируем умный совет с учетом Bio и Focus
                bio = user.get('bio')
                focus = rs.get('focus')
                message_text = await self.generate_recall_message(contacts, bio=bio, focus=focus)
                
                # 4. Отправляем и обновляем Latch
                try:
                    # Add Freemium footer
                    footer = ""
                    if not is_pro:
                        footer = "\n\n📅 <i>В Pro-версии я могу напоминать о людях каждый день.</i>"
                    
                    final_text = message_text + footer
                    await bot.send_message(chat_id=user_id, text=final_text)

                    count += 1
                    logger.info(f"Sent smart recall to {user_id}")
                    
                    # Обновляем last_sent_date в БД
                    rs['last_sent_date'] = current_date_str
                    await user_service.update_recall_settings(user_id, RecallSettings(**rs))
                    
                except Exception as e:
                    logger.warning(f"Failed to send message or update settings for {user_id}: {e}")
                
                await asyncio.sleep(0.5)

            logger.info(f"Recall finished. Sent {count} messages.")

        except Exception as e:
            logger.error(f"Recall process failed: {e}")

recall_service = RecallService()
