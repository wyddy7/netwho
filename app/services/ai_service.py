import json
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
import httpx

from app.config import settings
from app.schemas import ContactExtracted, ContactMeta

class AIService:
    def __init__(self):
        # Клиент для LLM (OpenRouter)
        self.llm_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL
        )
        
        # Клиент для Embeddings (напрямую OpenAI или через OpenRouter, если поддерживает)
        # В ТЗ указано использовать OpenAI SDK, но OpenRouter тоже поддерживает embeddings.
        # Для простоты используем тот же клиент, если модель доступна, иначе нужен отдельный ключ OpenAI.
        # Обычно embeddings дешевле брать напрямую у OpenAI или использовать бесплатные альтернативы.
        # Предполагаем, что OPENROUTER_API_KEY позволяет доступ к embeddings или модель доступна.
        # Если нет - код придется адаптировать под отдельный ключ.
        self.embedding_client = self.llm_client 

        # Клиент для Groq (STT)
        self.groq_client = None
        if settings.GROQ_API_KEY:
            self.groq_client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )

    async def transcribe_audio(self, audio_file_path: str) -> str:
        """
        Транскрибация аудио.
        Приоритет: Groq (Whisper-large-v3) -> OpenAI/OpenRouter (Fallback).
        """
        if self.groq_client:
            try:
                logger.debug("Transcribing with Groq Whisper...")
                with open(audio_file_path, "rb") as file:
                    transcription = await self.groq_client.audio.transcriptions.create(
                        file=(audio_file_path, file.read()),
                        model="whisper-large-v3",
                        response_format="text"
                    )
                return transcription
            except Exception as e:
                logger.warning(f"Groq STT failed: {e}. Falling back...")
        
        # Fallback (если Groq нет или упал)
        # В MVP мы не подключали платный OpenAI для STT, поэтому здесь либо ошибка, либо
        # если OpenRouter поддерживает STT (обычно нет).
        # Для надежности можно использовать локальный faster-whisper (как в ТЗ), 
        # но пока вернем ошибку или попробуем через основной клиент (вдруг там есть модель).
        raise RuntimeError("STT service unavailable (Groq failed or not configured)")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def extract_contact_info(self, text: str) -> ContactExtracted:
        """
        Извлечение сущностей из текста с помощью LLM.
        """
        system_prompt = """
        You are a smart CRM assistant. Extract contact details from the text into JSON.
        
        Output format (JSON):
        {
          "name": "string (required, use 'Unknown' if not found)",
          "summary": "string (short summary of who is this and context)",
          "meta": {
            "role": "string or null",
            "company": "string or null",
            "interests": ["list of strings"],
            "hobbies": ["list of strings"],
            "phones": ["list of strings"],
            "emails": ["list of strings"],
            "social": ["list of strings"],
            "needs": ["list of strings"]
          }
        }
        
        If the text is just a note without a person, set name to "Note" and summary to the content.
        """

        try:
            logger.debug("Extracting entities with LLM...")
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")

            data = json.loads(content)
            
            # Валидация через Pydantic
            return ContactExtracted(**data)

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            raise

    async def get_embedding(self, text: str) -> list[float]:
        """
        Генерация векторного представления текста.
        """
        try:
            # Важно: OpenRouter может маппить модели по-разному.
            # Если не работает, можно использовать text-embedding-ada-002
            response = await self.embedding_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

# Глобальный инстанс
ai_service = AIService()

