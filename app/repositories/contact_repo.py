from loguru import logger

class ContactRepository:
    def __init__(self, supabase):
        self.db = supabase

    async def create(self, user_id: int, contact_data: dict, org_id: str = None):
        """
        Создает контакт. Если передан org_id, ПРОВЕРЯЕТ права доступа.
        """
        # --- SECURITY CHECK START ---
        if org_id:
            # 1. Проверяем, реально ли юзер состоит в этой организации
            # Таблица называется organization_members, поля user_id и org_id
            response = self.db.table('organization_members')\
                .select('user_id, status')\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            
            is_member = len(response.data) > 0
            status = response.data[0].get('status', 'pending') if is_member else None
            
            if not is_member:
                # Юзер пытается хакнуть или баг в UI — сбрасываем на личный
                logger.warning(f"SECURITY ALERT: User {user_id} tried to write to forbidden org {org_id}. Fallback to personal.")
                org_id = None
            elif status == 'pending':
                # Юзер состоит, но еще не подтвержден
                logger.info(f"Access Blocked: User {user_id} is 'pending' in org {org_id}.")
                # Выбрасываем конкретную ошибку, которую сервис слой поймет
                from app.services.search_service import AccessDenied
                raise AccessDenied("Дождитесь подтверждения участия")
        # --- SECURITY CHECK END ---
                
        # Форсируем данные (не доверяем входному словарю целиком)
        contact_data['org_id'] = org_id
        contact_data['user_id'] = user_id 
        
        return self.db.table('contacts').insert(contact_data).execute()

    async def search(self, user_id: int, query: str):
        """
        Hybrid search (Story 15)
        """
        return self.db.rpc('search_hybrid', {'p_user_id': user_id, 'p_query': query}).execute()

    async def increment_free_searches(self, user_id: int, org_id: str) -> int:
        """
        Story 23: Increment free searches counter for pending members.
        """
        try:
            res = self.db.table('organization_members')\
                .select('free_searches_used, status')\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            
            if not res.data:
                return 0
                
            member = res.data[0]
            if member.get('status') != 'pending':
                logger.debug(f"[LIMIT] User {user_id} is not pending ({member.get('status')}), skipping increment.")
                return 0

            new_count = (member.get('free_searches_used') or 0) + 1
            
            logger.debug(f"[LIMIT] Incrementing searches for user {user_id} in org {org_id}: {member.get('free_searches_used')} -> {new_count}")
            
            self.db.table('organization_members')\
                .update({'free_searches_used': new_count})\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .eq('status', 'pending')\
                .execute()
            
            return new_count
        except Exception as e:
            logger.error(f"Error incrementing counter: {e}")
            return 0
