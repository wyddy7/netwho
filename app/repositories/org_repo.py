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
