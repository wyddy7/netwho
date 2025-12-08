import yaml
from pathlib import Path
from loguru import logger

class PromptsConfig:
    _prompts: dict = {}

    @classmethod
    def load(cls):
        try:
            path = Path("prompts.yaml")
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    cls._prompts = yaml.safe_load(f)
                logger.info("Prompts loaded from prompts.yaml")
            else:
                logger.warning("prompts.yaml not found!")
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")

    @classmethod
    def get(cls, key: str) -> str:
        if not cls._prompts:
            cls.load()
        return cls._prompts.get(key, "")

# Глобальный доступ
def get_prompt(key: str) -> str:
    return PromptsConfig.get(key)

