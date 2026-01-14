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
            try:
                response = self.db.table('organization_members')\
                    .select('user_id, status')\
                    .eq('user_id', user_id)\
                    .eq('org_id', org_id)\
                    .execute()
                
                is_member = len(response.data) > 0
                status = response.data[0].get('status', 'pending') if is_member else None
                
                if not is_member or status == 'pending':
                    if not is_member:
                        # Юзер пытается хакнуть или баг в UI — сбрасываем на личный
                        logger.warning(f"SECURITY ALERT: User {user_id} tried to write to forbidden org {org_id}. Fallback to personal.")
                        org_id = None
                    else:
                        # Юзер состоит, но еще не подтвержден
                        logger.info(f"Access Blocked: User {user_id} is 'pending' in org {org_id}.")
                        raise ValueError("Дождитесь подтверждения участия")
            except ValueError:
                # Re-raise our specific error for the service layer
                raise
            except Exception as e:
                logger.error(f"Error checking org membership: {e}")
                org_id = None # Fail safe
                
        # --- SECURITY CHECK END ---
                
        # Форсируем данные (не доверяем входному словарю целиком)
        contact_data['org_id'] = org_id
        contact_data['user_id'] = user_id 
        
        return self.db.table('contacts').insert(contact_data).execute()

    async def get_user_orgs(self, user_id: int):
        """
        Returns list of orgs user belongs to.
        Optimization: Join with organizations table to get names
        """
        # Return format: [{'id': uuid, 'name': 'Python Heroes'}, ...]
        try:
            res = self.db.table('organization_members').select('org_id, organizations(name)').eq('user_id', user_id).execute()
            
            return [
                {'id': row['org_id'], 'name': row['organizations']['name']} 
                for row in res.data if row.get('organizations')
            ]
        except Exception as e:
            logger.error(f"Error fetching user orgs: {e}")
            return []

    async def search(self, user_id: int, query: str):
        """
        Hybrid search (Story 15)
        """
        return self.db.rpc('search_hybrid', {'p_user_id': user_id, 'p_query': query}).execute()

    async def create_org(self, name: str, owner_id: int):
        """
        Creates an organization and adds owner. (Story 17)
        """
        try:
            # 1. Create Org
            res = self.db.table('organizations').insert({'name': name, 'owner_id': owner_id}).execute()
            if not res.data:
                raise ValueError("Failed to create org")
            
            org_id = res.data[0]['id']
            invite_code = res.data[0]['invite_code']
            
            # 2. Add Owner as Member
            self.db.table('organization_members').insert({
                'user_id': owner_id, 
                'org_id': org_id,
                'role': 'owner',
                'status': 'approved'
            }).execute()
            
            return {'id': org_id, 'invite_code': invite_code}
        except Exception as e:
            logger.error(f"Create Org failed: {e}")
            raise
