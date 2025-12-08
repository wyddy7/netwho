import json
from typing import List, Union
from openai import AsyncOpenAI
from loguru import logger
from app.config import settings
from app.schemas import ContactCreate, SearchResult, ContactExtracted, ContactDraft, UserSettings, ContactConfirm
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
            "name": "confirm_save",
            "description": "Подтверждение сохранения текущего черновика контакта (когда пользователь пишет 'да', 'сохрани').",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
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
    },
    {
        "type": "function",
        "function": {
            "name": "update_contact",
            "description": "Обновление описания существующего контакта.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "string",
                        "description": "UUID контакта."
                    },
                    "text": {
                        "type": "string",
                        "description": "Новый текст описания или дополнения."
                    }
                },
                "required": ["contact_id", "text"]
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

    async def run_router_agent(self, user_text: str, user_id: int) -> Union[str, List[SearchResult], ContactCreate, ContactDraft, ContactConfirm]:
        """
        Агент-маршрутизатор с памятью.
        """
        # ЛОКАЛЬНЫЙ ИМПОРТ
        from app.services.user_service import user_service
        from app.services.search_service import search_service
        
        user = await user_service.get_user(user_id)
        settings_obj = user.settings if user and user.settings else UserSettings()
        
        # 1. Получаем историю
        history = await user_service.get_chat_history(user_id)
        
        system_prompt = get_prompt("router")
        
        # 2. Формируем контекст: System -> History -> Current User Message
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        try:
            # 3. Запрос к LLM
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            
            # 4. Сохраняем сообщение Юзера в историю (только если успешно получили ответ)
            await user_service.save_chat_message(user_id, "user", user_text)

            # Обработка ответа
            final_response = None
            
            if not msg.tool_calls:
                final_response = msg.content
                # Сохраняем текстовый ответ ассистента
                if final_response:
                    await user_service.save_chat_message(user_id, "assistant", final_response)
                return final_response

            # Если был Tool Call
            tool_call = msg.tool_calls[0]
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"Agent called: {fn_name}")
            
            # Сохраняем в историю факт вызова инструмента (как system, чтобы не мусорить пользователю, но LLM это увидит)
            tool_summary = f"[Tool Used: {fn_name}, Args: {json.dumps(fn_args, ensure_ascii=False)}]"
            await user_service.save_chat_message(user_id, "system", tool_summary)

            if fn_name == "search_contacts":
                results = await search_service.search(fn_args["query"], user_id)
                final_response = results
                
                # ХАК: Сохраняем результаты поиска в историю, чтобы агент "видел" ID контактов на следующем шаге
                # Формируем компактный JSON или текст для LLM
                if results:
                    search_context = "Search Results:\n" + "\n".join(
                        [f"ID: {r.id} | Name: {r.name} | Summary: {r.summary}" for r in results]
                    )
                    # Сохраняем это как сообщение от SYSTEM или ASSISTANT (но скрытое от юзера в UI, здесь мы пишем в базу)
                    await user_service.save_chat_message(user_id, "system", f"[Context Memory] {search_context}")
            
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
                
                if settings_obj.confirm_add:
                    final_response = ContactDraft(**contact_create.model_dump())
                    # ВАЖНО: Добавляем в историю, что мы ждем подтверждения
                    await user_service.save_chat_message(user_id, "system", "[System] Draft created. Waiting for user confirmation (click button OR type 'confirm/yes').")
                else:
                    await search_service.create_contact(contact_create)
                    final_response = contact_create 
            
            elif fn_name == "confirm_save":
                # Агент решил подтвердить сохранение (поняв это из текста юзера)
                final_response = ContactConfirm()

            elif fn_name == "delete_contact":
                contact_id = fn_args.get("contact_id")
                if settings_obj.confirm_delete:
                    contact = await search_service.get_contact_by_id(contact_id, user_id)
                    if contact:
                        final_response = [SearchResult(
                            id=contact.id,
                            name=contact.name,
                            summary=contact.summary,
                            meta=contact.meta
                        )]
                    else:
                        final_response = "Контакт не найден."
                else:
                    success = await search_service.delete_contact(contact_id, user_id)
                    status = 'удален' if success else 'не найден'
                    final_response = f"🗑 Контакт {status}."

            elif fn_name == "update_contact":
                contact_id = fn_args["contact_id"]
                new_text = fn_args["text"]
                
                existing = await search_service.get_contact_by_id(contact_id, user_id)
                if not existing:
                    final_response = "Контакт не найден."
                else:
                    # Объединяем старый текст и правку, чтобы пересобрать контекст
                    updated_raw_text = f"{existing.raw_text}\n\n[Update]: {new_text}"
                    
                    extracted = await self.extract_contact_info(updated_raw_text)
                    
                    full_text = f"{extracted.name} {extracted.summary} {extracted.meta}"
                    embedding = await self.get_embedding(full_text)
                    
                    updates = {
                        "name": extracted.name,
                        "summary": extracted.summary,
                        "meta": extracted.meta.model_dump(),
                        "raw_text": updated_raw_text,
                        "embedding": embedding
                    }
                    
                    updated_contact = await search_service.update_contact(contact_id, user_id, updates)
                    
                    if updated_contact:
                        # Возвращаем объект как при создании, чтобы хендлер красиво ответил
                        final_response = ContactCreate(
                            user_id=user_id,
                            name=updated_contact.name,
                            summary=updated_contact.summary,
                            raw_text=updated_contact.raw_text,
                            meta=updated_contact.meta,
                            embedding=embedding
                        )
                    else:
                        final_response = "Ошибка при обновлении."

            # Если ответ текстовый (от инструмента, например ошибка), сохраняем его
            # ВАЖНО: Если мы уже вернули результат инструмента (final_response не None и не str),
            # то сюда мы не попадаем. Если final_response это строка, то мы ее логируем.
            
            logger.debug(f"Returning final_response type: {type(final_response)}")
            if isinstance(final_response, list):
                logger.debug(f"List length: {len(final_response)}")

            if isinstance(final_response, str):
                await user_service.save_chat_message(user_id, "assistant", final_response)
            
            return final_response if final_response else "Ошибка обработки."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка (Agent Error)."

ai_service = AIService()
