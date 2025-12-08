import os
import sys
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

# Настройка логгера
logger.remove()
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # AI (OpenRouter / OpenAI)
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Models
    LLM_MODEL: str = "openai/gpt-4o-mini"  # Основная модель
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Voice (Groq)
    GROQ_API_KEY: str | None = None

    # App Settings
    CHAT_HISTORY_DEPTH: int = 10
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

logger.info("Configuration loaded successfully")
