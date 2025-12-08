from uuid import UUID
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import ContactCreate, ContactInDB, SearchResult

class SearchService:
    def __init__(self):
        self.supabase = get_supabase()

    async def create_contact(self, contact_data: ContactCreate) -> ContactInDB:
        try:
            data = contact_data.model_dump(exclude_none=True)
            response = self.supabase.table("contacts").insert(data).execute()
            if not response.data:
                raise ValueError("Failed to insert contact")
            return ContactInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error creating contact: {e}")
            raise

    async def get_contact_by_id(self, contact_id: UUID | str, user_id: int) -> ContactInDB | None:
        try:
            response = self.supabase.table("contacts")\
                .select("*")\
                .eq("id", str(contact_id))\
                .eq("user_id", user_id)\
                .execute()
            if not response.data:
                return None
            return ContactInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error getting contact: {e}")
            raise

    async def update_contact(self, contact_id: UUID | str, user_id: int, updates: dict) -> ContactInDB | None:
        try:
            response = self.supabase.table("contacts")\
                .update(updates)\
                .eq("id", str(contact_id))\
                .eq("user_id", user_id)\
                .execute()
            if not response.data:
                return None
            return ContactInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error updating contact: {e}")
            raise

    async def delete_contact(self, contact_id: UUID | str, user_id: int) -> bool:
        try:
            response = self.supabase.table("contacts")\
                .delete()\
                .eq("id", str(contact_id))\
                .eq("user_id", user_id)\
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error deleting contact: {e}")
            raise
    
    async def find_similar_contacts_by_name(self, name: str, user_id: int) -> list[ContactInDB]:
        """
        Ищет контакты с похожим именем (ILike).
        """
        try:
            # Простой поиск по подстроке case-insensitive
            response = self.supabase.table("contacts")\
                .select("*")\
                .eq("user_id", user_id)\
                .ilike("name", f"%{name}%")\
                .execute()
            
            if not response.data:
                return []
                
            return [ContactInDB(**item) for item in response.data]
        except Exception as e:
            logger.error(f"Find similar failed: {e}")
            return []

    async def get_recent_contacts(self, user_id: int, limit: int = 10) -> list[SearchResult]:
        """
        Получить последние добавленные контакты (для запроса "Кто у меня есть").
        """
        try:
            # Вызываем нашу новую SQL функцию
            response = self.supabase.rpc("get_recent_contacts", {
                "match_user_id": user_id,
                "match_count": limit
            }).execute()
            
            if not response.data:
                return []
            
            return [SearchResult(**item) for item in response.data]
        except Exception as e:
            logger.error(f"Get recent contacts failed: {e}")
            return []

    async def search(self, query: str, user_id: int, limit: int = 10) -> list[SearchResult]:
        try:
            # ХАК: Если запрос похож на "покажи всех", вызываем get_recent_contacts
            # Но лучше это делать через логику агента (он может передать query='*')
            if query.strip() == "*" or query.lower() in ["все", "all", "все контакты"]:
                logger.info(f"Fetching recent contacts for user {user_id}")
                return await self.get_recent_contacts(user_id, limit)

            logger.debug(f"Searching for '{query}' for user {user_id}...")
            
            from app.services.ai_service import ai_service
            
            embedding = await ai_service.get_embedding(query)
            
            params = {
                "query_embedding": embedding,
                "match_user_id": user_id,
                "match_threshold": 0.15, 
                "match_count": limit
            }
            
            response = self.supabase.rpc("match_contacts", params).execute()
            
            if not response.data:
                logger.debug("No matches found")
                return []
                
            logger.debug(f"Found {len(response.data)} matches")
            return [SearchResult(**item) for item in response.data]
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

search_service = SearchService()
