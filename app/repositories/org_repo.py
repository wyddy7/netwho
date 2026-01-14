from loguru import logger
from typing import List, Dict, Optional

class OrgRepository:
    def __init__(self, supabase):
        self.db = supabase

    async def get_org_by_id(self, org_id: str) -> Optional[Dict]:
        """
        Returns organization details.
        """
        try:
            res = self.db.table('organizations').select('*').eq('id', org_id).execute()
            if res.data:
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting org {org_id}: {e}")
            return None

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

    async def add_member(self, user_id: int, org_id: str, role: str = 'member', status: str = 'pending') -> bool:
        """
        Adds a member to an organization.
        Returns True if added, False if already a member.
        """
        try:
            # Check for existing membership
            existing = self.db.table('organization_members')\
                .select('user_id')\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            
            if existing.data:
                logger.info(f"User {user_id} is already a member of org {org_id}")
                return False
            
            # Add new member
            self.db.table('organization_members').insert({
                'user_id': user_id,
                'org_id': org_id,
                'role': role,
                'status': status
            }).execute()
            
            return True
        except Exception as e:
            logger.error(f"Error adding member {user_id} to org {org_id}: {e}")
            raise

    async def get_user_memberships(self, user_id: int) -> List[Dict]:
        """
        Returns list of orgs user belongs to.
        """
        try:
            res = self.db.table('organization_members').select('org_id, status, organizations(name)').eq('user_id', user_id).execute()
            return res.data
        except Exception as e:
            logger.error(f"Error fetching memberships for user {user_id}: {e}")
            return []

    async def get_pending_members_for_owner(self, owner_id: int) -> List[Dict]:
        """
        Returns list of pending members for all orgs owned by owner_id.
        """
        try:
            # 1. Get all orgs owned by this user
            orgs_res = self.db.table('organizations').select('id, name').eq('owner_id', owner_id).execute()
            if not orgs_res.data:
                return []
            
            org_ids = [org['id'] for org in orgs_res.data]
            org_names = {org['id']: org['name'] for org in orgs_res.data}
            
            # 2. Get pending members for these orgs
            res = self.db.table('organization_members')\
                .select('user_id, org_id, users(full_name, username)')\
                .eq('status', 'pending')\
                .in_('org_id', org_ids)\
                .execute()
            
            pending = []
            for row in res.data:
                user_info = row.get('users', {})
                pending.append({
                    'user_id': row['user_id'],
                    'org_id': row['org_id'],
                    'org_name': org_names.get(row['org_id']),
                    'username': user_info.get('username'),
                    'full_name': user_info.get('full_name', 'Unknown')
                })
            return pending
        except Exception as e:
            logger.error(f"Error fetching pending members: {e}")
            return []

    async def update_member_status(self, user_id: int, org_id: str, status: str) -> bool:
        """
        Updates member status (approved, banned, pending).
        """
        try:
            res = self.db.table('organization_members')\
                .update({'status': status})\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            return bool(res.data)
        except Exception as e:
            logger.error(f"Error updating member status: {e}")
            return False

    async def is_org_owner(self, user_id: int) -> bool:
        """
        Checks if user owns at least one organization.
        """
        try:
            res = self.db.table('organizations').select('id').eq('owner_id', user_id).limit(1).execute()
            return bool(res.data)
        except Exception as e:
            logger.error(f"Error checking org ownership: {e}")
            return False

    async def is_specific_org_owner(self, user_id: int, org_id: str) -> bool:
        """
        Checks if user owns a specific organization.
        """
        try:
            res = self.db.table('organizations').select('id').eq('owner_id', user_id).eq('id', org_id).limit(1).execute()
            return bool(res.data)
        except Exception as e:
            logger.error(f"Error checking specific org ownership: {e}")
            return False
