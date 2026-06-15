import re
import aiohttp
from loguru import logger

# Match an http(s) URL: scheme + a run of characters that are legal inside a
# URL. The class excludes whitespace and the RFC 3986 delimiters/illegal chars
# (<>"'`{}|\^[]) that bound a URL inside prose, so we stop at the first one
# instead of swallowing trailing markup like "http://x.com<script>".
#
# The previous pattern used `[$-_@.&+]`, where the intended literal set
# `$ - _ @ . & +` was silently turned into the range $(0x24)..._(0x5F) by the
# stray hyphen. That range matched delimiters such as < > [ ] \ ^ ? (extracting
# garbage into the URL) while at the same time *dropping* legal chars outside
# the range like ~ and # (truncating valid URLs). An explicit exclusion class
# fixes both directions.
_URL_RE = re.compile(r"""https?://[^\s<>"'`{}|\\^\[\]]+""")

# Trailing punctuation that is almost always prose, not part of the URL.
_URL_TRAILING = ".,;:!?"


class NewsService:
    def __init__(self):
        self.jina_base_url = "https://r.jina.ai/"

    def extract_url(self, text: str) -> str | None:
        """
        Находит первую ссылку в тексте.
        """
        match = _URL_RE.search(text)
        if not match:
            return None
        return match.group(0).rstrip(_URL_TRAILING) or None

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




