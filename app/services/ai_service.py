import json
from typing import List, Union
from openai import AsyncOpenAI
from loguru import logger
from app.config import settings
from app.schemas import ContactCreate, SearchResult, ContactExtracted, ContactDraft, UserSettings
from app.prompts_loader import get_prompt

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Поиск контактов в базе знаний.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос (имя, профессия, контекст). Для 'всех' используй 'все контакты'."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_contact",
            "description": "Добавление нового контакта или заметки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Полный текст заметки или описания контакта."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_contact",
            "description": "Удаление контакта по ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "string",
                        "description": "UUID контакта для удаления."
                    }
                },
                "required": ["contact_id"]
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

    async def get_embedding(self, text: str) -> list[float]:
        try:
            # Используем OpenAI клиент для эмбеддингов (OpenRouter поддерживает некоторые модели, 
            # но часто для эмбеддингов используют напрямую OpenAI или другую модель в OpenRouter)
            # В конфиге у нас OPENROUTER_API_KEY, предполагаем что OpenRouter роутит к модели эмбеддингов.
            response = await self.llm_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    async def transcribe_audio(self, file_path: str) -> str:
        """
        Транскрибация аудио через Groq (Whisper).
        """
        if not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY is not set. Voice disabled.")
            return ""
            
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            
            with open(file_path, "rb") as file:
                # Читаем файл в память, так как клиент Groq ожидает (filename, content) или file-like object
                content = file.read()
                
            transcription = await client.audio.transcriptions.create(
                file=(file_path, content),
                model="whisper-large-v3",
                response_format="json",
                language="ru",
                temperature=0.0
            )
            return transcription.text
        except Exception as e:
            logger.error(f"STT failed: {e}")
            return ""

    async def extract_contact_info(self, text: str) -> ContactExtracted:
        """
        Извлекает структурированные данные из текста.
        """
        system_prompt = get_prompt("extractor")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
        
        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            return ContactExtracted(**data)
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise

    async def run_router_agent(self, user_text: str, user_id: int) -> Union[str, List[SearchResult], ContactCreate, ContactDraft]:
        """
        Агент-маршрутизатор.
        """
        # ЛОКАЛЬНЫЙ ИМПОРТ для предотвращения циклической зависимости
        from app.services.user_service import user_service
        from app.services.search_service import search_service
        
        user = await user_service.get_user(user_id)
        settings_obj = user.settings if user and user.settings else UserSettings()
        
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

            if fn_name == "search_contacts":
                results = await search_service.search(fn_args["query"], user_id)
                return results
            
            elif fn_name == "add_contact":
                # Логика добавления
                text_to_process = fn_args["text"]
                extracted = await self.extract_contact_info(text_to_process)
                
                full_text = f"{extracted.name} {extracted.summary} {extracted.meta}"
                embedding = await self.get_embedding(full_text)
                
                # Создаем объект
                contact_create = ContactCreate(
                    user_id=user_id,
                    name=extracted.name,
                    summary=extracted.summary,
                    raw_text=text_to_process,
                    meta=extracted.meta.model_dump(),
                    embedding=embedding
                )
                
                # ПРОВЕРКА НАСТРОЕК (Approves)
                if settings_obj.confirm_add:
                    # Если нужно подтверждение -> возвращаем Draft
                    return ContactDraft(**contact_create.model_dump())
                else:
                    # Rage Mode: Сохраняем сразу
                    await search_service.create_contact(contact_create)
                    return contact_create 
            
            elif fn_name == "delete_contact":
                contact_id = fn_args.get("contact_id")
                
                if settings_obj.confirm_delete:
                    # Safe Mode: НЕ удаляем сразу.
                    # Вместо этого возвращаем контакт как результат поиска (с кнопкой "Удалить").
                    contact = await search_service.get_contact_by_id(contact_id, user_id)
                    if contact:
                        # Возвращаем список из одного SearchResult
                        return [SearchResult(
                            id=contact.id,
                            name=contact.name,
                            summary=contact.summary,
                            meta=contact.meta
                        )]
                    else:
                        return "Контакт не найден, чтобы его удалить."
                else:
                    # Rage Mode: Удаляем сразу
                    success = await search_service.delete_contact(contact_id, user_id)
                    status = 'удален' if success else 'не найден'
                    return f"🗑 Контакт {status}."

            return "Команда не распознана."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка (Agent Error)."

ai_service = AIService()
