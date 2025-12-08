import json
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
import httpx

from app.config import settings
from app.schemas import ContactExtracted, ContactMeta
from app.services.search_service import search_service

# Описание инструментов для Router Agent
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search for contacts, people, or memories using semantic search.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'Who is Dima?', 'find developers', 'fishing lovers')"
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_contact",
            "description": "Delete a specific contact by UUID. Use this ONLY after finding the contact ID via search_contacts.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "string",
                        "description": "The UUID of the contact to delete"
                    }
                },
                "required": ["contact_id"],
                "additionalProperties": False
            }
        }
    }
]

class AIService:
    def __init__(self):
        # Клиент для LLM (OpenRouter)
        self.llm_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL
        )
        
        # Клиент для Embeddings (напрямую OpenAI или через OpenRouter)
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
            return ContactExtracted(**data)

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            raise

    async def get_embedding(self, text: str) -> list[float]:
        """
        Генерация векторного представления текста.
        """
        try:
            response = await self.embedding_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def run_router_agent(self, user_text: str, user_id: int) -> str | list:
        """
        Агент-маршрутизатор.
        Возвращает либо строку (ответ пользователю), либо список результатов поиска.
        """
        logger.debug(f"Router Agent processing: {user_text}")
        
        messages = [
            {
                "role": "system", 
                "content": (
                    "You are a helpful Personal CRM assistant. "
                    "Determine user intent from the message. "
                    "If user asks to FIND someone -> use 'search_contacts'. "
                    "If user asks to DELETE someone -> you MUST first SEARCH for them using 'search_contacts' to get their ID. "
                    "If user just chats (hello, how are you) -> reply with text."
                )
            },
            {"role": "user", "content": user_text}
        ]

        try:
            # 1. Запрос к LLM с инструментами
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            
            # 2. Если LLM не хочет вызывать функции -> это просто болтовня
            if not msg.tool_calls:
                return msg.content

            # 3. Обработка вызовов функций
            tool_call = msg.tool_calls[0] # Берем первый вызов (DeepSeek V3 обычно делает по одному)
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"Agent decided to call: {fn_name} with {fn_args}")

            if fn_name == "search_contacts":
                results = await search_service.search(fn_args["query"], user_id)
                return results # Возвращаем список объектов SearchResult
            
            elif fn_name == "delete_contact":
                contact_id = fn_args.get("contact_id")
                # Тут тонкий момент: LLM могла галлюцинировать ID, если не искала до этого.
                # Но мы в промпте попросили сначала искать.
                if contact_id:
                    success = await search_service.delete_contact(contact_id, user_id)
                    return f"🗑 Контакт {'удален' if success else 'не найден'}."
                return "Ошибка: Не указан ID контакта."
                
            return "Неизвестная функция."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка при обработке запроса."

# Глобальный инстанс
ai_service = AIService()
