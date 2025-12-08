import json
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from typing import Union, List

from app.config import settings
from app.schemas import ContactExtracted, ContactCreate, SearchResult
from app.prompts_loader import get_prompt

# Описание инструментов для Router Agent
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Искать контакты. Search for contacts.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (cleaned from noise)"
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
            "name": "add_contact",
            "description": "Добавить новый контакт или заметку из текста. Add new contact/note from text.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Full raw text of the contact description"
                    }
                },
                "required": ["text"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_contact",
            "description": "Удалить контакт по ID. Delete contact by ID.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "string",
                        "description": "UUID of the contact"
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
        self.llm_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL
        )
        self.embedding_client = self.llm_client 
        
        self.groq_client = None
        if settings.GROQ_API_KEY:
            self.groq_client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )

    async def transcribe_audio(self, audio_file_path: str) -> str:
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
        raise RuntimeError("STT service unavailable")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def extract_contact_info(self, text: str) -> ContactExtracted:
        system_prompt = get_prompt("extractor")
        
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
        try:
            response = await self.embedding_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def run_router_agent(self, user_text: str, user_id: int) -> Union[str, List[SearchResult], ContactCreate]:
        """
        Агент-маршрутизатор.
        Возвращает:
        - str: Ответ пользователю
        - list[SearchResult]: Результаты поиска
        - ContactCreate: Если был добавлен контакт (чтобы хендлер красиво ответил)
        """
        logger.debug(f"Router Agent processing: {user_text}")
        
        system_prompt = get_prompt("router")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            if not msg.tool_calls:
                return msg.content

            tool_call = msg.tool_calls[0]
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"Agent called: {fn_name}")

            # ЛОКАЛЬНЫЙ ИМПОРТ (чтобы избежать цикла)
            from app.services.search_service import search_service

            if fn_name == "search_contacts":
                results = await search_service.search(fn_args["query"], user_id)
                return results
            
            elif fn_name == "add_contact":
                # Логика добавления (как в voice handler)
                text_to_process = fn_args["text"]
                extracted = await self.extract_contact_info(text_to_process)
                
                full_text = f"{extracted.name} {extracted.summary} {extracted.meta}"
                embedding = await self.get_embedding(full_text)
                
                contact_create = ContactCreate(
                    user_id=user_id,
                    name=extracted.name,
                    summary=extracted.summary,
                    raw_text=text_to_process,
                    meta=extracted.meta.model_dump(),
                    embedding=embedding
                )
                
                await search_service.create_contact(contact_create)
                return contact_create # Возвращаем объект, чтобы хендлер отрендерил "✅ Записал"
            
            elif fn_name == "delete_contact":
                contact_id = fn_args.get("contact_id")
                if contact_id:
                    success = await search_service.delete_contact(contact_id, user_id)
                    return f"🗑 Контакт {'удален' if success else 'не найден'}."
                return "Ошибка ID."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка (Agent Error)."

ai_service = AIService()
