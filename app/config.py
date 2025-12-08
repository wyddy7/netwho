from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger
import sys

class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # AI Provider
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Models
    LLM_MODEL: str = "deepseek/deepseek-chat"
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    # Optional STT
    GROQ_API_KEY: str | None = None

    # Security & Logging
    USER_ID_SALT: str = "default-salt-change-me"
    LOG_LEVEL: str = "INFO"
    
    # Chat History
    CHAT_HISTORY_DEPTH: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Инициализация настроек
try:
    settings = Settings()
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    sys.exit(1)

# Настройка логгера
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL,
)

logger.info("Configuration loaded successfully")
