from datetime import datetime
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import UserCreate, UserInDB

class UserService:
    def __init__(self):
        self.supabase = get_supabase()

    async def upsert_user(self, user: UserCreate) -> UserInDB:
        """
        Создает или обновляет пользователя при входе (/start).
        """
        try:
            data = user.model_dump(exclude_none=True)
            data["updated_at"] = datetime.now().isoformat()
            
            # upsert: insert + on conflict update
            response = self.supabase.table("users").upsert(data).execute()
            
            if not response.data:
                raise ValueError("Failed to upsert user")
                
            return UserInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error upserting user: {e}")
            raise

    async def accept_terms(self, user_id: int) -> bool:
        """
        Обновляет флаг terms_accepted.
        """
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
        """
        Полное удаление пользователя и всех его данных (GDPR).
        Благодаря ON DELETE CASCADE в SQL, удаление юзера удалит и контакты.
        """
        try:
            logger.warning(f"DELETING ALL DATA for user {user_id}")
            response = self.supabase.table("users").delete().eq("id", user_id).execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            raise

# Глобальный инстанс
user_service = UserService()

