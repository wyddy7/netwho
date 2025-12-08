from datetime import datetime
from typing import List
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import UserCreate, UserInDB, UserSettings
from app.config import settings

class UserService:
    def __init__(self):
        self.supabase = get_supabase()

    async def upsert_user(self, user: UserCreate) -> UserInDB:
        try:
            data = user.model_dump(exclude_none=True)
            data["updated_at"] = datetime.now().isoformat()
            
            # Для настроек используем merge стратегию по умолчанию, если их нет
            # Но так как мы передаем объект, он перезапишет. 
            # Лучше сначала получить текущего юзера, если надо сохранить настройки.
            # Но для MVP при /start можно и сбросить или оставить как есть.
            
            response = self.supabase.table("users").upsert(data).execute()
            if not response.data:
                raise ValueError("Failed to upsert user")
            return UserInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error upserting user: {e}")
            raise

    async def get_user(self, user_id: int) -> UserInDB | None:
        try:
            response = self.supabase.table("users").select("*").eq("id", user_id).execute()
            if not response.data:
                return None
            return UserInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    async def update_settings(self, user_id: int, settings: UserSettings) -> bool:
        try:
            logger.info(f"Updating settings for {user_id}: {settings}")
            response = self.supabase.table("users")\
                .update({"settings": settings.model_dump()})\
                .eq("id", user_id)\
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return False

    async def accept_terms(self, user_id: int) -> bool:
        try:
            response = self.supabase.table("users")\
                .update({"terms_accepted": True})\
                .eq("id", user_id)\
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error accepting terms: {e}")
            return False

    async def delete_user_full(self, user_id: int) -> bool:
        try:
            logger.warning(f"DELETING ALL DATA for user {user_id}")
            response = self.supabase.table("users").delete().eq("id", user_id).execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            raise

    async def get_chat_history(self, user_id: int) -> List[dict]:
        """
        Получает историю чата для формирования контекста.
        """
        try:
            limit = settings.CHAT_HISTORY_DEPTH
            # Вызываем RPC функцию
            response = self.supabase.rpc("get_chat_history", {
                "p_user_id": user_id,
                "p_limit": limit
            }).execute()
            
            if not response.data:
                return []
                
            return [{"role": item["role"], "content": item["content"]} for item in response.data]
        except Exception as e:
            logger.error(f"Failed to fetch chat history: {e}")
            return []

    async def save_chat_message(self, user_id: int, role: str, content: str):
        """
        Сохраняет сообщение в историю.
        """
        try:
            data = {
                "user_id": user_id,
                "role": role,
                "content": content
            }
            self.supabase.table("chat_history").insert(data).execute()
        except Exception as e:
            logger.error(f"Failed to save chat message: {e}")

    async def clear_history(self, user_id: int):
        """
        Очищает историю сообщений пользователя.
        """
        try:
            # Удаляем все записи из chat_history для данного user_id
            self.supabase.table("chat_history").delete().eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Failed to clear chat history: {e}")

user_service = UserService()
