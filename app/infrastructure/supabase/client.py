from supabase import create_client, Client
from app.config import settings
from loguru import logger

class SupabaseClient:
    _instance: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            try:
                cls._instance = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_KEY
                )
                logger.info("Supabase client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                raise
        return cls._instance

# Глобальный инстанс
def get_supabase() -> Client:
    return SupabaseClient.get_client()

