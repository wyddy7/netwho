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

    async def get_random_contact_for_user(self, user_id: int):
        try:
            response = self.supabase.rpc("get_random_contact", {"p_user_id": user_id}).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting random contact for {user_id}: {e}")
            return None

    async def generate_recall_message(self, contact: dict) -> str:
        """
        Генерирует 'напоминалку' с помощью LLM.
        """
        prompt = (
            f"Задача: Сгенерируй короткое, неформальное напоминание пользователю о человеке из его записной книжки.\n"
            f"Контакт: {contact['name']}\n"
            f"Описание: {contact['summary']}\n\n"
            f"Инструкция:\n"
            f"1. Напиши 1-2 предложения.\n"
            f"2. Стиль: дружеский 'пинок', Random Coffee.\n"
            f"3. Используй контекст из описания, чтобы предложить тему для разговора.\n"
            f"4. НИКАКИХ кавычек вокруг всего текста.\n"
            f"5. НИКАКИХ вводных слов ('Вот напоминание:', 'Привет!'). Сразу к делу.\n"
            f"6. НЕ используй Markdown (**bold**), используй HTML теги (<b>bold</b>), если очень надо что-то выделить.\n"
            f"7. Имена выделяй жирным (<b>Имя</b>)."
        )
        
        try:
            response = await ai_service.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content.strip()
            
            # Очистка от маркдауна, если он все-таки пролез
            content = content.replace("**", "")
            
            # Очистка от кавычек по краям (но не внутри)
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]
            if content.startswith("'") and content.endswith("'"):
                content = content[1:-1]
                
            return content.strip()
        except Exception as e:
            logger.error(f"Error generating recall message: {e}")
            return f"Давно не общались с {contact['name']}. Может, напишешь?"

    async def process_recalls(self, bot: Bot):
        """
        Основной цикл: берет пользователей и шлет напоминания.
        В MVP берем всех пользователей.
        """
        logger.info("Starting Active Recall process...")
        try:
            # 1. Получаем всех пользователей (Pagination нужен для продакшена, пока так)
            users_response = self.supabase.table("users").select("id").execute()
            users = users_response.data
            
            if not users:
                logger.info("No users found.")
                return

            count = 0
            for user in users:
                user_id = user['id']
                
                # 2. Берем случайный контакт
                contact = await self.get_random_contact_for_user(user_id)
                if not contact:
                    continue

                # 3. Генерируем сообщение
                message_text = await self.generate_recall_message(contact)
                
                # 4. Отправляем (с обработкой блокировки бота)
                try:
                    text = f"🎲 <b>Случайный контакт</b>\n\n{message_text}"
                    await bot.send_message(chat_id=user_id, text=text)
                    count += 1
                    logger.info(f"Sent recall to {user_id} about {contact['name']}")
                except Exception as e:
                    logger.warning(f"Failed to send message to {user_id}: {e}")
                
                # Пауза чтобы не спамить API
                await asyncio.sleep(0.5)
                
            logger.info(f"Recall finished. Sent {count} messages.")

        except Exception as e:
            logger.error(f"Recall process failed: {e}")

recall_service = RecallService()

