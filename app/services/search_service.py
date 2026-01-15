import re
from uuid import UUID
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import ContactCreate, ContactInDB, SearchResult
from app.repositories.contact_repo import ContactRepository
from app.repositories.org_repo import OrgRepository
from app.services.user_service import user_service

class AccessDenied(Exception):
    """Исключение при отсутствии прав доступа к ресурсу."""
    pass

class SearchService:
    def __init__(self):
        self.supabase = get_supabase()
        self.repo = ContactRepository(self.supabase)
        self.org_repo = OrgRepository(self.supabase)

    async def create_contact(self, contact_data: ContactCreate) -> ContactInDB:
        try:
            # 1. Security Check: Block 'pending' members from creating org contacts
            if contact_data.org_id:
                res = self.supabase.table('organization_members')\
                    .select('status')\
                    .eq('user_id', contact_data.user_id)\
                    .eq('org_id', str(contact_data.org_id))\
                    .execute()
                
                if res.data and res.data[0].get('status') == 'pending':
                    logger.warning(f"[AUTH] Create blocked: user {contact_data.user_id} is pending in org {contact_data.org_id}")
                    raise AccessDenied("Дождитесь подтверждения участия")

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
        return await self.org_repo.get_user_orgs(user_id)

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
            
            # 4.1. Check Organization Access if applicable
            if contact.org_id:
                # If contact belongs to org, check if user is an APPROVED member
                res = self.supabase.table('organization_members')\
                    .select('status')\
                    .eq('user_id', user_id)\
                    .eq('org_id', str(contact.org_id))\
                    .execute()
                
                if not res.data:
                    logger.warning(f"[AUTH] Access Denied: user {user_id} not a member of org {contact.org_id}")
                    return None
                
                if res.data[0].get('status') == 'pending':
                    logger.info(f"[AUTH] Access Restricted: user {user_id} is pending in org {contact.org_id}")
                    # For search/view, we might return None or something else. 
                    # If it's pending, they shouldn't see it yet according to story.
                    return None

            elif db_owner_id != request_user_id:
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
            # 1. Попытка выделить организацию из запроса (Story 16)
            q = query.strip()
            q_lower = q.lower()
            
            org_id = None
            org_name_query = None

            if "org:" in q_lower:
                match = re.search(r'org:(\S+)', q_lower)
                if match:
                    org_name_query = match.group(1)
                    q = q.replace(f"org:{org_name_query}", "").strip()
                    if not q: q = "*"
            
            # Если не нашли через org:, попробуем найти упоминание организации в тексте
            if not org_name_query:
                user_memberships = await self.get_user_orgs(user_id)
                for org in user_memberships:
                    if org['name'].lower() in q_lower:
                        org_id = org['id']
                        break
            else:
                user_memberships = await self.get_user_orgs(user_id)
                for org in user_memberships:
                    if org_name_query == org['name'].lower() or org_name_query in org['name'].lower():
                        org_id = org['id']
                        break

            # --- STORY 23: GLOBAL LIMIT CHECK ---
            # Если поиск касается организации, проверяем лимиты ПЕРЕД любыми действиями
            if org_id:
                allowed, message = await user_service.check_search_limit(user_id, str(org_id))
                if not allowed:
                    logger.info(f"[LIMIT] Search blocked for user {user_id} in org {org_id}")
                    raise AccessDenied(message)
            # ------------------------------------

            # 2. Если организация найдена, и запрос был только про неё (или "все"), 
            # возвращаем список контактов этой организации
            if org_id and (q == "*" or not q):
                # Double check: if user is pending, they should only see this via the limit logic above
                # But here we are already after the limit check. 
                # Let's add an extra security layer: check if user is actually APPROVED to bypass limits
                # or if they are PENDING but have searches left (already checked).
                
                # However, the direct select below bypasses our search_hybrid SQL function's security.
                # Let's make it respect the membership status.
                
                response = self.supabase.table("contacts")\
                    .select("id, name, summary, meta, org_id, organizations(name)")\
                    .eq("org_id", str(org_id))\
                    .eq("is_archived", False)\
                    .order("created_at", desc=True)\
                    .limit(limit)\
                    .execute()

                # Filter results to ensure user is allowed to see them if they are pending
                # (Actually, if they reached here, check_search_limit already passed)

                results: list[SearchResult] = []
                for item in response.data:
                    org_rel = item.get("organizations")
                    item["org_name"] = org_rel.get("name") if isinstance(org_rel, dict) else None
                    item.pop("organizations", None)
                    results.append(SearchResult(**item))
                
                # Story 23: Increment counter for simple list search
                await user_service.increment_free_searches(user_id, str(org_id))
                
                return results

            # 3. Гибридный поиск по оставшемуся запросу
            q_lower = q.lower()
            
            # ХАК: Если запрос похож на "покажи всех", вызываем get_recent_contacts
            if q == "*" or q_lower in ["все", "all", "все контакты"]:
                return await self.get_recent_contacts(user_id, limit)

            logger.debug(f"Searching for '{q}' (org_id={org_id}) for user {user_id}...")
            
            # --- TRUE HYBRID SEARCH (SQL + Vector) ---
            
            # 1. SQL Search (Exact/Partial Match) - Priority 1
            sql_results = []
            try:
                # 1.1 Поиск по имени и описанию через RPC
                response = await self.repo.search(user_id, q)
                if response.data:
                    sql_results = [SearchResult(**item) for item in response.data]
                    logger.debug(f"SQL Search found {len(sql_results)} items via RPC")
                
                # 1.2 Если мы в контексте конкретной организации, фильтруем или добавляем её
                if org_id:
                    # Фильтруем SQL результаты, оставляя только те, что в этой орге
                    sql_results = [r for r in sql_results if str(r.org_id) == str(org_id)]
                else:
                    # Ищем организации пользователя, подходящие под запрос
                    user_orgs = await self.get_user_orgs(user_id)
                    matched_org_ids = [str(org['id']) for org in user_orgs if q_lower in org['name'].lower()]
                    
                    if matched_org_ids:
                        org_response = self.supabase.table("contacts")\
                            .select("id, name, summary, meta, org_id, organizations(name)")\
                            .in_("org_id", matched_org_ids)\
                            .eq("is_archived", False)\
                            .execute()
                        
                        if org_response.data:
                            for item in org_response.data:
                                org_rel = item.get("organizations")
                                item["org_name"] = org_rel.get("name") if isinstance(org_rel, dict) else None
                                item.pop("organizations", None)
                                res = SearchResult(**item)
                                if not any(r.id == res.id for r in sql_results):
                                    sql_results.append(res)
            except Exception as e:
                logger.error(f"SQL Search failed: {e}")

            # 2. Vector Search (Semantic) - Priority 2
            vector_results = []
            try:
                from app.services.ai_service import ai_service
                embedding = await ai_service.get_embedding(q)
                
                if embedding:
                    params = {
                        "query_embedding": embedding,
                        "match_user_id": user_id,
                        "match_threshold": 0.2, # Еще ниже порог для гибкости (Story 18)
                        "match_count": limit
                    }
                    
                    vec_response = self.supabase.rpc("match_contacts", params).execute()
                    if vec_response.data:
                        vector_results = [SearchResult(**item) for item in vec_response.data]
                        # Если есть org_id, фильтруем
                        if org_id:
                            vector_results = [r for r in vector_results if str(r.org_id) == str(org_id)]
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
            
            # Story 23: Increment counter for pending users in org context
            if org_id:
                await user_service.increment_free_searches(user_id, str(org_id))
                
            return final_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

search_service = SearchService()
