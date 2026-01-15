from datetime import datetime, timezone, timedelta
from typing import Any, List, Dict
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
        return await self.update_user_field(user_id, "settings", settings.model_dump(mode='json'))

    async def update_recall_settings(self, user_id: int, settings: RecallSettings) -> bool:
        return await self.update_user_field(user_id, "recall_settings", settings.model_dump(mode='json'))
    
    async def update_bio(self, user_id: int, bio: str) -> bool:
        return await self.update_user_field(user_id, "bio", bio)

    async def is_pro(self, user_id: int) -> bool:
        """
        Check if user has an active Pro subscription OR active Trial.
        """
        user = await self.get_user(user_id)
        if not user:
            return False
        
        now = datetime.now(timezone.utc)
        
        # 1. Check Paid Subscription
        if user.pro_until and user.pro_until > now:
            logger.debug(f"User {user_id} is PRO (Paid until {user.pro_until})")
            return True
            
        # 2. Check Trial
        if user.trial_ends_at and user.trial_ends_at > now:
            logger.debug(f"User {user_id} is PRO (Trial until {user.trial_ends_at})")
            return True
        
        logger.debug(f"User {user_id} is FREE (Trial ends: {user.trial_ends_at}, Pro until: {user.pro_until}, Now: {now})")
        return False

    async def update_subscription(self, user_id: int, days: int) -> bool:
        """
        Extend or set subscription.
        Also updates is_premium flag based on pro_until date.
        """
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
            
            # Update both pro_until and is_premium
            # is_premium should be True if new_date is in the future
            is_premium = new_date > now
            
            # Use bulk update to set both fields at once
            updates = {
                "pro_until": new_date.isoformat(),
                "is_premium": is_premium
            }
            
            response = self.supabase.table("users")\
                .update(updates)\
                .eq("id", user_id)\
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            return False

    async def revoke_subscription(self, user_id: int) -> bool:
        """
        Revoke subscription by clearing pro_until AND trial_ends_at.
        """
        try:
            # Just clear the date. 
            response = self.supabase.table("users")\
                .update({
                    "pro_until": None, 
                    "trial_ends_at": None, # Also revoke trial
                    "is_premium": False
                })\
                .eq("id", user_id)\
                .execute()
            
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error revoking subscription: {e}")
            return False
            
    async def grant_trial(self, user_id: int, days: int = None) -> bool:
        """
        Grant trial period.
        """
        if days is None:
            days = settings.TRIAL_DAYS
            
        try:
            now = datetime.now(timezone.utc)
            trial_end = now + timedelta(days=days)
            
            response = self.supabase.table("users")\
                .update({"trial_ends_at": trial_end.isoformat()})\
                .eq("id", user_id)\
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error granting trial: {e}")
            return False

    async def increment_news_jacks(self, user_id: int) -> int:
        """
        Increment news_jacks_count and return new value.
        Doing this via fetch+update is prone to race conditions, 
        but Supabase client usually doesn't expose atomic increment easily without RPC.
        For MVP this is fine.
        """
        try:
            user = await self.get_user(user_id)
            if not user: return 0
            
            new_count = user.news_jacks_count + 1
            await self.update_user_field(user_id, "news_jacks_count", new_count)
            return new_count
        except Exception as e:
            logger.error(f"Error incrementing news jacks: {e}")
            return 999

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
        Учитывает Pro-статус для определения глубины контекста.
        """
        try:
            is_pro = await self.is_pro(user_id)
            
            if is_pro:
                limit = settings.CHAT_HISTORY_DEPTH # 10-20
            else:
                limit = 3 # "Короткая память" для Free
                
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

    async def join_org(self, user_id: int, org_id: str) -> dict:
        """
        Adds user to organization as 'pending'.
        Returns dict with status and org_name.
        """
        from app.repositories.org_repo import OrgRepository
        repo = OrgRepository(self.supabase)
        
        org = await repo.get_org_by_id(org_id)
        if not org:
            return {"status": "not_found", "org_name": None}
            
        success = await repo.add_member(user_id, org_id, status='pending')
        if not success:
            return {"status": "already_member", "org_name": org['name']}
            
        return {"status": "joined", "org_name": org['name']}

    async def is_org_owner(self, user_id: int, org_id: str = None) -> bool:
        from app.repositories.org_repo import OrgRepository
        repo = OrgRepository(self.supabase)
        if org_id:
            return await repo.is_specific_org_owner(user_id, org_id)
        return await repo.is_org_owner(user_id)

    async def get_pending_members(self, owner_id: int) -> List[Dict]:
        from app.repositories.org_repo import OrgRepository
        repo = OrgRepository(self.supabase)
        return await repo.get_pending_members_for_owner(owner_id)

    async def approve_member(self, user_id: int, org_id: str) -> bool:
        from app.repositories.org_repo import OrgRepository
        repo = OrgRepository(self.supabase)
        return await repo.update_member_status(user_id, org_id, 'approved')

    async def reject_member(self, user_id: int, org_id: str) -> bool:
        from app.repositories.org_repo import OrgRepository
        repo = OrgRepository(self.supabase)
        return await repo.update_member_status(user_id, org_id, 'banned')

    async def increment_free_searches(self, user_id: int, org_id: str) -> int:
        """
        Story 23: Increment free searches counter for pending members.
        """
        from app.repositories.contact_repo import ContactRepository
        repo = ContactRepository(self.supabase)
        return await repo.increment_free_searches(user_id, org_id)

    async def check_search_limit(self, user_id: int, org_id: str) -> tuple[bool, str]:
        """
        Story 23: Check if pending user reached free limit in organization.
        """
        try:
            res = self.supabase.table('organization_members')\
                .select('status, free_searches_used')\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            
            if not res.data:
                return True, ""
                
            member = res.data[0]
            status = member.get('status', 'pending')
            used = member.get('free_searches_used', 0)
            
            logger.debug(f"[LIMIT] Checking user {user_id} in org {org_id}: status={status}, used={used}/3")
            
            if status == 'pending' and used >= 3:
                msg = (
                    "Лимит демо-поисков исчерпан (3/3).\n"
                    "Чтобы продолжить, администратор должен подтвердить твою заявку."
                )
                return False, msg
                
            return True, ""
        except Exception as e:
            logger.error(f"Error checking search limit: {e}")
            return True, ""

user_service = UserService()
