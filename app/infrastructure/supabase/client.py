from supabase import create_client, Client
from app.config import settings
from loguru import logger

class SupabaseClient:
    _instance: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            try:
                # Используем Service Role Key (обходит RLS) или fallback на обычный ключ
                api_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
                if settings.SUPABASE_SERVICE_ROLE_KEY:
                    logger.info("Supabase client initialized with SERVICE_ROLE_KEY (RLS bypassed)")
                else:
                    logger.warning("Supabase client initialized with regular key (RLS may block operations)")
                
                cls._instance = create_client(
                    settings.SUPABASE_URL,
                    api_key
                )
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                raise
        return cls._instance

# Глобальный инстанс
def get_supabase() -> Client:
    return SupabaseClient.get_client()

