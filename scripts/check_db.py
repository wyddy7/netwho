import asyncio
import sys
import os

# Добавляем корень проекта в путь
sys.path.append(os.getcwd())

from app.infrastructure.supabase.client import get_supabase
from loguru import logger

async def check_connection():
    logger.info("Checking Supabase connection...")
    try:
        client = get_supabase()
        # Пробуем простой запрос, например, получить версию PostgreSQL или просто count из пустой таблицы
        # В Supabase API напрямую выполнить SQL 'SELECT version()' сложно без прав, 
        # но мы можем попробовать обратиться к таблице users.
        # Даже если она пустая, запрос должен пройти (вернет пустой список), если соединение есть.
        
        response = client.table("users").select("*", count="exact").limit(1).execute()
        
        logger.success(f"Connection successful! Users count: {response.count}")
        return True
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(check_connection())

