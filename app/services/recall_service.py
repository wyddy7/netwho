import asyncio
from loguru import logger
from aiogram import Bot
from app.infrastructure.supabase.client import get_supabase
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.config import settings

class RecallService:
    def __init__(self):
        self.supabase = get_supabase()

    async def get_random_contacts_for_user(self, user_id: int, limit: int = 3):
        try:
            response = self.supabase.rpc("get_random_contacts", {
                "p_user_id": user_id, 
                "p_limit": limit
            }).execute()
            if response.data:
                return response.data
            return []
        except Exception as e:
            logger.error(f"Error getting random contacts for {user_id}: {e}")
            return []

    async def generate_recall_message(self, contacts: list) -> str:
        """
        Генерирует стратегический совет по нетворку на основе списка контактов.
        """
        contacts_str = "\n".join([
            f"- ID: {c['id']}\n  Name: {c['name']}\n  Summary: {c['summary']}\n  Meta: {c.get('meta', {})}"
            for c in contacts
        ])

        prompt = (
            f"Ты — стратегический советник по нетворку (Business Development Assistant). "
            f"Твоя цель — создать ПОВОД (Reason) для общения, а не просто 'приветствие'.\n\n"
            f"Вот список случайных контактов пользователя (Дани):\n{contacts_str}\n\n"
            f"Твоя задача:\n"
            f"1. Выбери 1-2 самых интересных контакта (или пару для синергии).\n"
            f"2. Сгенерируй КОНКРЕТНУЮ идею (Action Item).\n"
            f"3. Формат ответа строго HTML (без Markdown **bold**):\n"
            f"   🎲 <b>Анализ связей...</b>\n\n"
            f"   <b>Кандидат:</b> [Имя] ([Коротко кто он])\n"
            f"   <b>Контекст:</b> [Почему именно он?]\n\n"
            f"   💡 <b>Идея:</b> [Дерзкий и конкретный совет, что сделать/написать. Например: 'Скинь ему статью про X', 'Позови в бар с Y', 'Спроси про Z'.]\n\n"
            f"Если выбрал пару:\n"
            f"   <b>Пара:</b> [Имя 1] + [Имя 2]\n"
            f"   <b>Синергия:</b> [Почему их надо свести]\n\n"
            f"   💡 <b>Идея:</b> [Что сделать]\n\n"
            f"Не пиши общих фраз. Будь краток, дерзок и полезен. Пиши от лица советника, который обращается к Дане."
        )
        
        try:
            response = await ai_service.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content.strip()
            
            # Очистка от маркдауна
            content = content.replace("**", "")
            # Очистка от кавычек по краям
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]
            if content.startswith("'") and content.endswith("'"):
                content = content[1:-1]
                
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
            # 1. Получаем всех пользователей
            users_response = self.supabase.table("users").select("id").execute()
            users = users_response.data
            
            if not users:
                return

            count = 0
            for user in users:
                user_id = user['id']
                
                # 2. Берем БАТЧ контактов (3-5 штук) для анализа
                contacts = await self.get_random_contacts_for_user(user_id, limit=4)
                if not contacts:
                    continue

                # 3. Генерируем умный совет
                message_text = await self.generate_recall_message(contacts)
                
                # 4. Отправляем
                try:
                    # Убираем заголовок "Случайный контакт", так как он теперь внутри генерации
                    await bot.send_message(chat_id=user_id, text=message_text)
                    count += 1
                    logger.info(f"Sent smart recall to {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to send message to {user_id}: {e}")
                
                await asyncio.sleep(0.5)
                
            logger.info(f"Recall finished. Sent {count} messages.")

        except Exception as e:
            logger.error(f"Recall process failed: {e}")

recall_service = RecallService()

