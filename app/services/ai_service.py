import json
from typing import List, Union
from openai import AsyncOpenAI
from loguru import logger
from app.config import settings
from app.schemas import (
    ContactCreate, SearchResult, ContactExtracted, 
    ContactDraft, UserSettings, ContactDeleteAsk,
    ActionConfirmed, ActionCancelled
)
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
            "name": "confirm_action",
            "description": "Подтвердить ожидающее действие (сохранение или удаление), когда пользователь пишет 'да', 'сохрани', 'удаляй'.",
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
            "name": "cancel_action",
            "description": "Отменить ожидающее действие, когда пользователь пишет 'нет', 'отмена', 'не надо'.",
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

    async def run_router_agent(self, user_text: str, user_id: int) -> Union[str, List[SearchResult], ContactCreate, ContactDraft, ContactDeleteAsk, ActionConfirmed, ActionCancelled]:
        """
        Агент-маршрутизатор с памятью и поддержкой многошаговых вызовов (Loop).
        """
        # ЛОКАЛЬНЫЙ ИМПОРТ
        from app.services.user_service import user_service
        from app.services.search_service import search_service
        
        user = await user_service.get_user(user_id)
        settings_obj = user.settings if user and user.settings else UserSettings()
        
        # 1. Получаем историю
        history = await user_service.get_chat_history(user_id)
        
        system_prompt = get_prompt("router")
        
        # 2. Формируем начальный контекст
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        # 3. Сохраняем сообщение Юзера в историю (один раз)
        await user_service.save_chat_message(user_id, "user", user_text)

        max_steps = 5
        step_count = 0
        last_tool_list_result = None # Здесь будем хранить список контактов, если он был получен

        try:
            while step_count < max_steps:
                step_count += 1
                
                # Запрос к LLM
                response = await self.llm_client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                messages.append(msg) # Добавляем ответ ассистента в контекст текущей сессии
                
                # Если нет вызова инструментов - это финальный текстовый ответ
                if not msg.tool_calls:
                    final_text = msg.content
                    # Сохраняем в БД
                    if final_text:
                        await user_service.save_chat_message(user_id, "assistant", final_text)
                    
                    # ХАК: Если у нас в "кармане" есть список контактов от предыдущего шага поиска,
                    # и финальный ответ это просто текст, то вернем список, чтобы показались кнопки!
                    if last_tool_list_result and isinstance(last_tool_list_result, list) and len(last_tool_list_result) > 0:
                        return last_tool_list_result
                        
                    return final_text

                # Если есть вызов инструментов
                tool_call = msg.tool_calls[0]
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"Agent called step {step_count}: {fn_name}")
                
                # Сохраняем факт вызова в БД
                tool_summary = f"[Tool Used: {fn_name}, Args: {json.dumps(fn_args, ensure_ascii=False)}]"
                await user_service.save_chat_message(user_id, "system", tool_summary)

                # Выполняем инструмент
                tool_result_content = "" # Строка для LLM
                execution_result = None # Объект для логики

                if fn_name == "search_contacts":
                    results = await search_service.search(fn_args["query"], user_id)
                    execution_result = results
                    last_tool_list_result = results # Запоминаем для UI
                    
                    if results:
                        # Формируем JSON для LLM
                        tool_result_content = json.dumps([
                            {"id": str(r.id), "name": r.name, "summary": r.summary} 
                            for r in results
                        ], ensure_ascii=False)
                        
                        # Сохраняем в контекст БД
                        search_context = "Search Results:\n" + "\n".join(
                            [f"ID: {r.id} | Name: {r.name} | Summary: {r.summary}" for r in results]
                        )
                        await user_service.save_chat_message(user_id, "system", f"[Context Memory] {search_context}")
                    else:
                        tool_result_content = "No contacts found."
                
                elif fn_name == "add_contact":
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
                    
                    if settings_obj.confirm_add:
                        # Если нужно подтверждение, мы ПРЕРЫВАЕМ цикл и возвращаем Draft
                        await user_service.save_chat_message(user_id, "system", "[System] Draft created. Waiting for user confirmation via 'confirm_action' or 'cancel_action'.")
                        return ContactDraft(**contact_create.model_dump())
                    else:
                        await search_service.create_contact(contact_create)
                        tool_result_content = f"Contact '{extracted.name}' created successfully."
                        execution_result = contact_create

                elif fn_name == "confirm_action":
                    return ActionConfirmed()
                
                elif fn_name == "cancel_action":
                    return ActionCancelled()

                elif fn_name == "delete_contact":
                    contact_id = fn_args.get("contact_id")
                    if settings_obj.confirm_delete:
                        # Если нужно подтверждение, ищем контакт для отображения
                        contact = await search_service.get_contact_by_id(contact_id, user_id)
                        if contact:
                            await user_service.save_chat_message(user_id, "system", f"[System] Deletion requested for ID {contact_id}. Waiting for confirmation via 'confirm_action' or 'cancel_action'.")
                            return ContactDeleteAsk(
                                contact_id=str(contact.id),
                                name=contact.name,
                                summary=contact.summary
                            )
                        else:
                            tool_result_content = "Error: Contact not found."
                    else:
                        success = await search_service.delete_contact(contact_id, user_id)
                        status = 'deleted' if success else 'not found'
                        tool_result_content = f"Contact {status}."

                elif fn_name == "update_contact":
                    contact_id = fn_args["contact_id"]
                    new_text = fn_args["text"]
                    existing = await search_service.get_contact_by_id(contact_id, user_id)
                    if not existing:
                        tool_result_content = "Contact not found."
                    else:
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
                        await search_service.update_contact(contact_id, user_id, updates)
                        tool_result_content = f"Contact '{extracted.name}' updated."

                # Добавляем результат инструмента в messages для следующего шага LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_content
                })

            return "Agent stopped (max steps reached)."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка (Agent Error)."

ai_service = AIService()
