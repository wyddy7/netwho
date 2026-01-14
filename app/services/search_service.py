from uuid import UUID
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import ContactCreate, ContactInDB, SearchResult
from app.repositories.contact_repo import ContactRepository

class AccessDenied(Exception):
    """Исключение при отсутствии прав доступа к ресурсу."""
    pass

class SearchService:
    def __init__(self):
        self.supabase = get_supabase()
        self.repo = ContactRepository(self.supabase)

    async def create_contact(self, contact_data: ContactCreate) -> ContactInDB:
        try:
            data = contact_data.model_dump(exclude_none=True)
            logger.debug(f"[CREATE] Creating contact: name='{contact_data.name}', user_id={contact_data.user_id}, org_id={contact_data.org_id}")
            
            # Use Repository for creation (handles security check if org_id is present)
            org_id = data.pop('org_id', None)
            
            # repo.create returns the response object from supabase
            response = await self.repo.create(contact_data.user_id, data, org_id)
            
            if not response.data:
                raise ValueError("Failed to insert contact")
            contact = ContactInDB(**response.data[0])
            logger.info(f"[CREATE] Contact created: id={contact.id}, name='{contact.name}', user_id={contact.user_id}")
            return contact
        except Exception as e:
            logger.error(f"[CREATE] Error creating contact: {e}", exc_info=True)
            raise

    async def get_user_orgs(self, user_id: int):
        return await self.repo.get_user_orgs(user_id)

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
                # TODO: Check if user is member of contact's organization?
                # For now, stick to strict ownership for editing/deleting?
                # Story says: "User sees personal contacts... and org contacts".
                # But editing rules are not fully specified yet. Assuming Owner/Admin logic or strict user_id for now.
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
        """
        try:
            logger.debug(f"[get_recent_contacts] user_id={user_id}, limit={limit}")
            response = self.supabase.table("contacts")\
                .select("id, name, summary, meta, org_id, organizations(name)")\
                .eq("user_id", user_id)\
                .eq("is_archived", False)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            
            if not response.data:
                return []

            results: list[SearchResult] = []
            for item in response.data:
                org_rel = item.get("organizations")
                org_name = None
                if isinstance(org_rel, dict):
                    org_name = org_rel.get("name")
                item.pop("organizations", None)
                item["org_name"] = org_name
                results.append(SearchResult(**item))

            return results
        except Exception as e:
            logger.error(f"[get_recent_contacts] Exception: {e}", exc_info=True)
            return []

    async def search(self, query: str, user_id: int, limit: int = 10) -> list[SearchResult]:
        try:
            q = query.strip()
            q_lower = q.lower()

            # Org scoped list: query like "org:<org_name>"
            if q_lower.startswith("org:"):
                org_name_query = q[4:].strip()
                if not org_name_query:
                    return []

                orgs = await self.get_user_orgs(user_id)
                matched_org = None
                for org in orgs:
                    name = (org.get("name") or "").strip()
                    if name and name.lower() == org_name_query.lower():
                        matched_org = org
                        break
                if not matched_org:
                    # fallback: substring match
                    for org in orgs:
                        name = (org.get("name") or "").strip()
                        if name and org_name_query.lower() in name.lower():
                            matched_org = org
                            break

                if not matched_org:
                    return []

                org_id = matched_org.get("id")
                response = self.supabase.table("contacts")\
                    .select("id, name, summary, meta, org_id, organizations(name)")\
                    .eq("org_id", str(org_id))\
                    .eq("is_archived", False)\
                    .order("created_at", desc=True)\
                    .limit(limit)\
                    .execute()

                if not response.data:
                    return []

                results: list[SearchResult] = []
                for item in response.data:
                    org_rel = item.get("organizations")
                    org_name = None
                    if isinstance(org_rel, dict):
                        org_name = org_rel.get("name")
                    item.pop("organizations", None)
                    item["org_name"] = org_name
                    results.append(SearchResult(**item))
                return results

            # ХАК: Если запрос похож на "покажи всех", вызываем get_recent_contacts
            if q == "*" or q_lower in ["все", "all", "все контакты"]:
                logger.info(f"Fetching recent contacts for user {user_id}")
                return await self.get_recent_contacts(user_id, limit)

            logger.debug(f"Searching for '{q}' for user {user_id}...")
            
            # --- TRUE HYBRID SEARCH (SQL + Vector) ---
            
            # 1. SQL Search (Exact/Partial Match) - Priority 1
            sql_results = []
            try:
                response = await self.repo.search(user_id, q)
                if response.data:
                    sql_results = [SearchResult(**item) for item in response.data]
                    logger.debug(f"SQL Search found {len(sql_results)} items")
            except Exception as e:
                logger.error(f"SQL Search failed: {e}")

            # 2. Vector Search (Semantic) - Priority 2
            vector_results = []
            try:
                from app.services.ai_service import ai_service
                
                # Get embedding for the query
                embedding = await ai_service.get_embedding(q)
                
                if embedding:
                    params = {
                        "query_embedding": embedding,
                        "match_user_id": user_id,
                        "match_threshold": 0.5, # Strict threshold
                        "match_count": limit
                    }
                    
                    # Call the new secure match_contacts RPC (v3)
                    vec_response = self.supabase.rpc("match_contacts", params).execute()
                    
                    if vec_response.data:
                        vector_results = [SearchResult(**item) for item in vec_response.data]
                        logger.debug(f"Vector Search found {len(vector_results)} items")
            except Exception as e:
                logger.error(f"Vector Search failed: {e}")

            # 3. Merge & Deduplicate
            # Use a dict to keep unique contacts, preserving order (SQL first)
            seen_ids = set()
            final_results = []

            # Add SQL results first (they are more "exact")
            for res in sql_results:
                if res.id not in seen_ids:
                    final_results.append(res)
                    seen_ids.add(res.id)
            
            # Add Vector results (only if not seen)
            for res in vector_results:
                if res.id not in seen_ids:
                    final_results.append(res)
                    seen_ids.add(res.id)
            
            # Limit total results
            final_results = final_results[:limit]
            
            logger.info(f"Hybrid Search Total: {len(final_results)} (SQL: {len(sql_results)}, Vector: {len(vector_results)})")
            return final_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

search_service = SearchService()
