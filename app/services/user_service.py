from datetime import datetime
from typing import Any, List
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import RecallSettings, UserCreate, UserInDB, UserSettings
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

    async def update_user_field(self, user_id: int, field: str, value: Any) -> bool:
        try:
            response = self.supabase.table("users")\
                .update({field: value})\
                .eq("id", user_id)\
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error updating user field {field}: {e}")
            return False

    async def update_settings(self, user_id: int, settings: UserSettings) -> bool:
        return await self.update_user_field(user_id, "settings", settings.model_dump())

    async def update_recall_settings(self, user_id: int, settings: RecallSettings) -> bool:
        return await self.update_user_field(user_id, "recall_settings", settings.model_dump())
    
    async def update_bio(self, user_id: int, bio: str) -> bool:
        return await self.update_user_field(user_id, "bio", bio)

    async def is_pro(self, user_id: int) -> bool:
        """
        Check if user has an active Pro subscription.
        """
        user = await self.get_user(user_id)
        if not user or not user.pro_until:
            return False
        
        # Check if pro_until is in the future
        # Note: user.pro_until is timezone aware (TIMESTAMPTZ)
        return user.pro_until > datetime.now(user.pro_until.tzinfo)

    async def update_subscription(self, user_id: int, days: int) -> bool:
        """
        Extend or set subscription.
        """
        from datetime import timedelta, timezone
        
        try:
            current_user = await self.get_user(user_id)
            if not current_user:
                return False
            
            now = datetime.now(timezone.utc)
            
            # If already Pro, extend. If not, start from now.
            if current_user.pro_until and current_user.pro_until > now:
                new_date = current_user.pro_until + timedelta(days=days)
            else:
                new_date = now + timedelta(days=days)
                
            return await self.update_user_field(user_id, "pro_until", new_date.isoformat())
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
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
            logger.warning(f"RESETTING DATA for user {user_id} (Subscription preserved)")
            
            # 1. Delete Contacts (if not cascaded)
            try:
                self.supabase.table("contacts").delete().eq("user_id", user_id).execute()
            except Exception as e:
                logger.error(f"Error deleting contacts: {e}")

            # 2. Delete Chat History
            try:
                self.supabase.table("chat_history").delete().eq("user_id", user_id).execute()
            except Exception as e:
                logger.error(f"Error deleting chat history: {e}")

            # 3. Wipe User Data (BUT KEEP ID & SUBSCRIPTION)
            # We do NOT delete the user row anymore to prevent subscription abuse (re-registering for trial).
            # Instead, we clear bio, settings, etc.
            
            updates = {
                "bio": None,
                "settings": UserSettings().model_dump(),
                "recall_settings": RecallSettings().model_dump(),
                # We can reset terms too if needed, but main trigger for onboarding is empty bio
                "terms_accepted": False 
            }
            
            response = self.supabase.table("users").update(updates).eq("id", user_id).execute()
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
            # Check if user exists, if not - skip saving history to avoid FK violation
            # Or simpler: Just try insert, if fails on FK - ignore.
            # But let's be cleaner: check existence is expensive on every log.
            
            # Better approach: Just try-catch the specific error.
            data = {
                "user_id": user_id,
                "role": role,
                "content": content
            }
            self.supabase.table("chat_history").insert(data).execute()
        except Exception as e:
            # Suppress Foreign Key violation error (happens if user deleted account or not started yet)
            if "violates foreign key constraint" in str(e):
                logger.warning(f"Skipped saving chat log for non-existent user {user_id}")
            else:
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

    async def delete_last_messages(self, user_id: int, count: int) -> int:
        """
        Удаляет последние N сообщений из истории.
        """
        try:
            # 1. Получаем ID последних N сообщений
            response = self.supabase.table("chat_history")\
                .select("id")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(count)\
                .execute()
            
            if not response.data:
                return 0
                
            ids_to_delete = [item['id'] for item in response.data]
            
            # 2. Удаляем их
            self.supabase.table("chat_history")\
                .delete()\
                .in_("id", ids_to_delete)\
                .execute()
                
            return len(ids_to_delete)
        except Exception as e:
            logger.error(f"Failed to delete last {count} messages: {e}")
            return 0

user_service = UserService()
