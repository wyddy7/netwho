import re
import aiohttp
from loguru import logger
from app.config import settings

class NewsService:
    def __init__(self):
        self.jina_base_url = "https://r.jina.ai/"
        
    def extract_url(self, text: str) -> str | None:
        """
        Находит первую ссылку в тексте.
        """
        url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        match = url_pattern.search(text)
        return match.group(0) if match else None

    async def fetch_article_content(self, url: str) -> str:
        """
        Получает чистый текст статьи через Jina Reader.
        """
        target_url = f"{self.jina_base_url}{url}"
        headers = {
            "X-With-Images-Summary": "false",
            "X-With-Links-Summary": "false"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url, headers=headers) as response:
                    if response.status == 200:
                        text = await response.text()
                        # Обрезаем слишком длинные статьи для LLM (например, первые 4000 символов)
                        return text[:4000]
                    else:
                        logger.error(f"Jina API error: {response.status}")
                        return ""
        except Exception as e:
            logger.error(f"Failed to fetch article: {e}")
            return ""

news_service = NewsService()

