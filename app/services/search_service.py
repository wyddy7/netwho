from uuid import UUID
from loguru import logger
from app.infrastructure.supabase.client import get_supabase
from app.schemas import ContactCreate, ContactInDB, SearchResult
# Убрали импорт ai_service отсюда

class SearchService:
    def __init__(self):
        self.supabase = get_supabase()

    async def create_contact(self, contact_data: ContactCreate) -> ContactInDB:
        """
        Создание нового контакта в БД.
        """
        try:
            # Преобразуем Pydantic модель в словарь для вставки
            data = contact_data.model_dump(exclude_none=True)
            
            # В Supabase-py insert возвращает APIResponse
            response = self.supabase.table("contacts").insert(data).execute()
            
            if not response.data:
                raise ValueError("Failed to insert contact")
                
            return ContactInDB(**response.data[0])
        except Exception as e:
            logger.error(f"Error creating contact: {e}")
            raise

    async def get_contact_by_id(self, contact_id: UUID | str, user_id: int) -> ContactInDB | None:
        """
        Получение контакта по ID с проверкой владельца (RLS).
        """
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

    async def delete_contact(self, contact_id: UUID | str, user_id: int) -> bool:
        """
        Удаление контакта по ID.
        """
        try:
            # Сначала проверяем существование (опционально, но полезно для логики агента)
            response = self.supabase.table("contacts")\
                .delete()\
                .eq("id", str(contact_id))\
                .eq("user_id", user_id)\
                .execute()
                
            # Если data не пуста, значит что-то удалили
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error deleting contact: {e}")
            raise

    async def search(self, query: str, user_id: int, limit: int = 5) -> list[SearchResult]:
        """
        Семантический поиск контактов через RPC функцию match_contacts.
        """
        try:
            logger.debug(f"Searching for '{query}' for user {user_id}...")
            
            # Локальный импорт для разрыва цикла
            from app.services.ai_service import ai_service
            
            # 1. Генерируем вектор запроса
            embedding = await ai_service.get_embedding(query)
            
            # 2. Вызываем RPC функцию в Supabase
            params = {
                "query_embedding": embedding,
                "match_user_id": user_id,
                "match_threshold": 0.4, # Можно вынести в конфиг
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

# Глобальный инстанс
search_service = SearchService()

