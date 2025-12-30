from uuid import UUID
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import ContactCreate, ContactInDB, SearchResult

class AccessDenied(Exception):
    """Исключение при отсутствии прав доступа к ресурсу."""
    pass

class SearchService:
    def __init__(self):
        self.supabase = get_supabase()

    async def create_contact(self, contact_data: ContactCreate) -> ContactInDB:
        try:
            data = contact_data.model_dump(exclude_none=True)
            logger.debug(f"[CREATE] Creating contact: name='{contact_data.name}', user_id={contact_data.user_id}")
            response = self.supabase.table("contacts").insert(data).execute()
            if not response.data:
                raise ValueError("Failed to insert contact")
            contact = ContactInDB(**response.data[0])
            logger.info(f"[CREATE] Contact created: id={contact.id}, name='{contact.name}', user_id={contact.user_id}")
            return contact
        except Exception as e:
            logger.error(f"[CREATE] Error creating contact: {e}", exc_info=True)
            raise

    async def get_contact_by_id(self, contact_id: UUID | str, user_id: int) -> ContactInDB | None:
        """
        Получает контакт по ID с проверкой прав доступа.
        Возвращает None, если контакт не найден или не принадлежит пользователю.
        
        ВАЖНО: Запрос делается ТОЛЬКО по ID (без фильтра по user_id), чтобы избежать
        конфликтов с RLS политиками Supabase. Проверка прав выполняется в Python коде.
        """
        logger.debug(f"[AUTH] get_contact_by_id: contact_id={contact_id}, user_id={user_id}")
        try:
            # 1. Запрос ТОЛЬКО по ID (без фильтра по user_id для избежания RLS конфликтов)
            contact_id_str = str(contact_id)
            response = self.supabase.table("contacts")\
                .select("*")\
                .eq("id", contact_id_str)\
                .execute()
            
            # 2. Если пусто - значит реально нет контакта
            if not response.data:
                logger.debug(f"[AUTH] Contact {contact_id_str} not found in DB")
                return None
            
            # 3. Парсим объект
            contact = ContactInDB(**response.data[0])
            
            # 4. ПРОВЕРКА ПРАВ В КОДЕ (Самое важное!)
            # Приводим к строке, чтобы избежать багов int vs str
            db_owner_id = str(contact.user_id)
            request_user_id = str(user_id)
            
            if db_owner_id != request_user_id:
                logger.warning(f"[AUTH] Access Denied: contact_id={contact_id_str}, DB_Owner={contact.user_id}, Request_User={user_id}")
                return None
            
            logger.debug(f"[AUTH] Access granted: contact_id={contact_id_str}, user_id={user_id}")
            return contact
        except Exception as e:
            logger.error(f"[AUTH] Exception in get_contact_by_id: {type(e).__name__}: {e}", exc_info=True)
            raise

    async def update_contact(self, contact_id: UUID | str, user_id: int, updates: dict) -> ContactInDB | None:
        """
        Обновляет контакт с явной проверкой прав доступа.
        Выбрасывает AccessDenied, если контакт не принадлежит пользователю.
        """
        # КРИТИЧНО: Проверяем права ДО обновления
        contact = await self.get_contact_by_id(contact_id, user_id)
        if not contact:
            logger.warning(f"[UPDATE] AccessDenied: contact_id={contact_id}, user_id={user_id}")
            raise AccessDenied(
                f"Contact {contact_id} does not belong to user {user_id}"
            )
        
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
        """
        Удаляет контакт с явной проверкой прав доступа.
        Выбрасывает AccessDenied, если контакт не принадлежит пользователю.
        """
        logger.debug(f"[DELETE] delete_contact: contact_id={contact_id}, user_id={user_id}")
        
        # КРИТИЧНО: Проверяем права ДО удаления
        contact = await self.get_contact_by_id(contact_id, user_id)
        
        if not contact:
            logger.warning(f"[DELETE] AccessDenied: contact_id={contact_id}, user_id={user_id}")
            raise AccessDenied(
                f"Contact {contact_id} does not belong to user {user_id}"
            )
        
        try:
            response = self.supabase.table("contacts")\
                .delete()\
                .eq("id", str(contact_id))\
                .eq("user_id", user_id)\
                .execute()
            
            deleted = bool(response.data)
            
            if deleted:
                logger.info(f"[DELETE] Contact {contact_id} deleted by user {user_id}")
            else:
                logger.warning(f"[DELETE] DB returned empty response - contact may not exist or already deleted")
            
            return deleted
        except Exception as e:
            logger.error(f"[DELETE] Exception during DB delete: {type(e).__name__}: {e}", exc_info=True)
            raise
    
    async def count_contacts(self, user_id: int) -> int:
        try:
            response = self.supabase.table("contacts")\
                .select("*", count="exact", head=True)\
                .eq("user_id", user_id)\
                .execute()
            return response.count or 0
        except Exception as e:
            logger.error(f"Error counting contacts: {e}")
            return 0

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
        
        ИСПРАВЛЕНО: Используем прямой запрос к таблице вместо RPC функции,
        которая возвращала несуществующие данные.
        """
        try:
            logger.debug(f"[get_recent_contacts] user_id={user_id}, limit={limit}")
            # Прямой запрос к таблице вместо RPC (которая возвращала несуществующие данные)
            response = self.supabase.table("contacts")\
                .select("id, name, summary, meta")\
                .eq("user_id", user_id)\
                .eq("is_archived", False)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            
            count = len(response.data) if response.data else 0
            logger.debug(f"[get_recent_contacts] Found {count} contacts")
            
            if not response.data:
                return []
            
            results = [SearchResult(**item) for item in response.data]
            return results
        except Exception as e:
            logger.error(f"[get_recent_contacts] Exception: {e}", exc_info=True)
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
