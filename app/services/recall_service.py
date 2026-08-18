import asyncio
import datetime
from loguru import logger
from aiogram import Bot
import tenacity
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
            
        except Exception:
            logger.exception(f"Error getting priority contacts for {user_id}")
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
            logger.info(f"LLM Recall Request | User Context: {user_context[:200]}...")
            
            # Логируем промпты через ai_service хелпер
            ai_service._log_llm_messages([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ])

            response = await ai_service.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            content = response.choices[0].message.content.strip()
            logger.info(f"LLM Recall Response | Content: {content}")
            
            # Очистка
            content = content.replace("**", "")
            if content.startswith("```html"): content = content[7:]
            if content.endswith("```"): content = content[:-3]
                
            return content.strip()
        except Exception:
            logger.exception("Error generating recall message")
            return "Не смог придумать повод. Попробуй позже."

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=lambda retry_state: logger.warning(f"Retrying recall process (attempt {retry_state.attempt_number}) due to error: {retry_state.outcome.exception()}"),
        reraise=True
    )
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
                
                if not rs.get('enabled', True):
                    continue
                
                days = rs.get('days', [4])

                # --- FREEMIUM CHECK ---
                is_pro = await user_service.is_pro(user_id)
                if not is_pro:
                    active_days = sorted(days)
                    if active_days:
                        allowed_day = active_days[0]
                        if today_weekday != allowed_day:
                             logger.debug(f"Free user {user_id} has days {days}, but allowed only {allowed_day}. Skip.")
                             continue
                
                if today_weekday not in days:
                    continue
                
                last_sent = rs.get('last_sent_date')
                if last_sent == current_date_str:
                    continue
                
                user_time_str = rs.get('time', '15:00')
                try:
                    uh, um = map(int, user_time_str.split(':'))
                    user_time = now.replace(hour=uh, minute=um, second=0, microsecond=0)
                except Exception:
                    user_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
                
                diff_minutes = (now - user_time).total_seconds() / 60
                if not (0 <= diff_minutes < 60):
                   continue
                
                contacts = await self.get_random_contacts_for_user(user_id, limit=4)
                if not contacts:
                    logger.warning(f"User {user_id} has no contacts for recall.")
                    continue

                bio = user.get('bio')
                focus = rs.get('focus')
                message_text = await self.generate_recall_message(contacts, bio=bio, focus=focus)
                
                try:
                    footer = ""
                    if not is_pro:
                        footer = "\n\n📅 <i>В Pro-версии я могу напоминать о людях каждый день.</i>"
                    
                    final_text = message_text + footer
                    await bot.send_message(chat_id=user_id, text=final_text)

                    count += 1
                    logger.info(f"Sent smart recall to {user_id}")
                    
                    rs['last_sent_date'] = current_date_str
                    await user_service.update_recall_settings(user_id, RecallSettings(**rs))
                    
                except Exception as e:
                    logger.warning("Failed to send message for {uid}: {err}", uid=user_id, err=repr(e))
                
                await asyncio.sleep(0.5)

            logger.info(f"Recall finished. Sent {count} messages.")

        except Exception as e:
            # We re-raise to let tenacity retry, unless it's the last attempt
            logger.exception("Recall process attempt failed")
            raise e

recall_service = RecallService()
