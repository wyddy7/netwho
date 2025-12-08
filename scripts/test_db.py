import asyncio
import sys
import os
from uuid import uuid4

sys.path.append(os.getcwd())

from app.services.search_service import search_service
from app.services.user_service import user_service
from app.schemas import UserCreate, ContactCreate
from loguru import logger

TEST_USER_ID = 123456789

async def test_db_pipeline():
    logger.info("--- Starting DB Pipeline Test ---")

    # 1. Создаем пользователя
    try:
        logger.info("Creating user...")
        user_data = UserCreate(
            id=TEST_USER_ID,
            full_name="Test User",
            username="test_user"
        )
        user = await user_service.upsert_user(user_data)
        logger.success(f"User created: {user.id}")
    except Exception as e:
        logger.error(f"User creation failed: {e}")
        return

    # 2. Создаем контакт
    contact_id = None
    try:
        logger.info("Creating contact...")
        # Генерируем фейковый эмбеддинг (просто нули, для теста вставки)
        # В реальности он приходит от AI
        fake_embedding = [0.1] * 1536 
        
        contact_data = ContactCreate(
            user_id=TEST_USER_ID,
            name="Test Contact",
            summary="Just a test contact",
            raw_text="Test raw text",
            meta={"role": "Tester"},
            embedding=fake_embedding
        )
        
        contact = await search_service.create_contact(contact_data)
        contact_id = contact.id
        logger.success(f"Contact created: {contact.id}")
    except Exception as e:
        logger.error(f"Contact creation failed: {e}")

    # 3. Ищем контакт (поиск не сработает адекватно на фейковом векторе, 
    # но проверим что RPC вызывается без ошибок)
    try:
        logger.info("Testing search...")
        # Тут вызовется реальный AI для генерации вектора запроса
        results = await search_service.search("Test", TEST_USER_ID)
        logger.info(f"Search executed. Found: {len(results)}")
    except Exception as e:
        logger.error(f"Search failed: {e}")

    # 4. Удаляем контакт
    if contact_id:
        try:
            logger.info(f"Deleting contact {contact_id}...")
            deleted = await search_service.delete_contact(contact_id, TEST_USER_ID)
            if deleted:
                logger.success("Contact deleted")
            else:
                logger.warning("Contact not found for deletion")
        except Exception as e:
            logger.error(f"Deletion failed: {e}")

    # 5. Удаляем пользователя (чистим за собой)
    try:
        logger.info("Deleting user...")
        deleted = await user_service.delete_user_full(TEST_USER_ID)
        logger.success("User deleted")
    except Exception as e:
        logger.error(f"User deletion failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_db_pipeline())

