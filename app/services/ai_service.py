import json
import re
from typing import List, Union
from openai import AsyncOpenAI
from loguru import logger
from app.config import settings
from app.schemas import (
    ContactCreate, SearchResult, ContactExtracted, 
    ContactDraft, UserSettings, ContactDeleteAsk, ContactUpdateAsk,
    ActionConfirmed, ActionCancelled
)
from app.prompts_loader import get_prompt

# Fixed schema syntax
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
            "description": "Добавление нового контакта. Если имя похоже на существующее, используй force_new=False для проверки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Полный текст заметки или описания контакта."
                    },
                    "force_new": {
                        "type": "boolean",
                        "description": "Если True - создает контакт даже если есть дубликат по имени. Default: False."
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
    },
    {
        "type": "function",
        "function": {
            "name": "check_subscription",
            "description": "Проверить статус подписки пользователя (есть ли Pro и когда истекает).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

class AIService:
    def __init__(self):
        # Настройка HTTP клиента с прокси, если он задан
        http_client = None
        if settings.PROXY_URL:
            import httpx
            logger.info(f"Using PROXY: {settings.PROXY_URL}")
            http_client = httpx.AsyncClient(proxy=settings.PROXY_URL)

        self.llm_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            http_client=http_client
        )
        self.http_client = http_client

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
            import os
            
            # Передаем http_client с прокси, если он есть
            client = AsyncGroq(
                api_key=settings.GROQ_API_KEY,
                http_client=self.http_client
            )

            logger.debug(f"Starting transcription for file: {file_path}")

            with open(file_path, "rb") as audio_file:
                transcription = await client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3",
                    response_format="json",
                    language="ru",
                    temperature=0.0
                )
            logger.debug(f"Transcription result: '{transcription.text}'")
            return transcription.text
        except Exception as e:
            logger.error(f"STT failed: {e}")
            logger.error(f"Error type: {type(e)}")
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

    async def refine_contact_info(self, old_summary: str, update_text: str) -> ContactExtracted:
        """
        Обновляет информацию о контакте на основе старой инфы и обновления.
        """
        system_prompt = get_prompt("refiner")
        user_content = f"OLD_SUMMARY:\n{old_summary}\n\nUPDATE:\n{update_text}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
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
            logger.error(f"Refinement failed: {e}")
            # Fallback: просто используем экстрактор на новом тексте, если рефайнер упал
            return await self.extract_contact_info(update_text)

    async def rerank_contacts(self, query: str, candidates: List[SearchResult]) -> List[SearchResult]:
        """
        Фильтрует и переранжирует кандидатов с помощью LLM.
        """
        if not candidates:
            return []
            
        # Если запрос "все", "all", то не фильтруем (это обрабатывается в search_service, но на всякий случай)
        if query.strip() == "*" or query.lower() in ["все", "all", "все контакты"]:
            return candidates

        # Формируем компактный список для LLM
        candidates_list = [
            {"id": str(c.id), "name": c.name, "summary": c.summary, "meta": c.meta}
            for c in candidates
        ]
        
        system_prompt = (
            "You are a strict relevance filter. "
            "Your task is to analyze the user's search query and the list of candidate contacts.\n"
            "Return a JSON object with key 'relevant_ids' containing a list of UUIDs (strings) of contacts that are STRICTLY relevant to the query.\n"
            "If a contact matches loosely but is not what the user asked for (e.g. name match but wrong context, or wrong company), exclude it.\n"
            "If no contacts are relevant, return empty list."
        )
        
        user_content = f"Query: {query}\nCandidates: {json.dumps(candidates_list, ensure_ascii=False)}"
        
        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            relevant_ids = set(data.get("relevant_ids", []))
            
            filtered = [c for c in candidates if str(c.id) in relevant_ids]
            
            logger.info(f"Rerank: {len(candidates)} -> {len(filtered)}")
            return filtered
            
        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            return candidates

    async def extract_user_bio(self, text: str) -> str:
        """
        Извлекает Bio и интересы пользователя из текста.
        """
        system_prompt = (
            "You are an expert profile analyzer. "
            "Extract a concise professional bio and interests from the user's text. "
            "Format the output as a short 1-2 sentence summary in Russian. "
            "Example input: 'Я продакт менеджер, делаю стартап в крипте, ищу инвесторов' "
            "Example output: 'Product Manager в крипто-стартапе. Интересы: инвестиции, блокчейн.'"
        )
        
        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Bio extraction failed: {e}")
            return text  # Fallback to raw text

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

        max_steps = 10
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
                    
                    # --- CLEANUP RAW TOOL CALL LEAKS ---
                    if final_text:
                        # Удаляем все, что похоже на xml-теги инструментов, если они просочились в текст
                        final_text = re.sub(r"<tool_calls_begin>.*", "", final_text, flags=re.DOTALL).strip()
                        final_text = re.sub(r"<tool_code>.*", "", final_text, flags=re.DOTALL).strip()
                    # -----------------------------------

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
                    
                    # Re-ranking / Filtering
                    if results:
                        results = await self.rerank_contacts(fn_args["query"], results)

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
                    force_new = fn_args.get("force_new", False)
                    
                    extracted = await self.extract_contact_info(text_to_process)

                    # --- Name Fallback (Fix for None validation error) ---
                    if not extracted.name or not extracted.name.strip():
                        # Пробуем сгенерировать имя из текста
                        words = text_to_process.split()[:5]
                        generated_name = " ".join(words)
                        if not generated_name:
                            generated_name = "Новая заметка"
                        
                        extracted.name = f"Заметка: {generated_name}..."
                    # -----------------------------------------------------
                    
                    # --- Disambiguation Check ---
                    if not force_new:
                        duplicates = await search_service.find_similar_contacts_by_name(extracted.name, user_id)
                        # Фильтруем совсем левые совпадения, если надо, но пока верим базе
                        if duplicates:
                            dup_list_str = "\n".join([f"- ID: {d.id} | Name: {d.name} | Summary: {d.summary}" for d in duplicates])
                            tool_result_content = (
                                f"WARNING: Found existing contacts with similar name '{extracted.name}':\n{dup_list_str}\n\n"
                                "ACTION REQUIRED: Ask user if they want to UPDATE one of these (call update_contact) "
                                "or CREATE NEW (call add_contact with force_new=True)."
                            )
                            # Прерываем выполнение, возвращаем инфу агенту
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": tool_result_content
                            })
                            continue # Переход к следующему шагу цикла (LLM увидит предупреждение)

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
                        # Используем Refiner вместо тупого Append + Extract
                        extracted = await self.refine_contact_info(
                            old_summary=existing.summary or "",
                            update_text=new_text
                        )
                        
                        updated_raw_text = f"{existing.raw_text}\n\n[Refined Update]: {new_text}"
                        full_text = f"{extracted.name} {extracted.summary} {extracted.meta}"
                        embedding = await self.get_embedding(full_text)
                        
                        updates = {
                            "name": extracted.name,
                            "summary": extracted.summary,
                            "meta": extracted.meta.model_dump(),
                            "raw_text": updated_raw_text,
                            "embedding": embedding
                        }
                        
                        if settings_obj.confirm_update:
                             await user_service.save_chat_message(user_id, "system", f"[System] Update requested for ID {contact_id}. Waiting for confirmation.")
                             return ContactUpdateAsk(
                                 contact_id=str(existing.id),
                                 name=existing.name,
                                 old_summary=existing.summary,
                                 new_summary=extracted.summary,
                                 updates=updates
                             )
                        else:
                            await search_service.update_contact(contact_id, user_id, updates)
                            tool_result_content = f"Contact '{extracted.name}' updated."

                elif fn_name == "check_subscription":
                    is_pro = await user_service.is_pro(user_id)
                    user_data = await user_service.get_user(user_id)
                    
                    if is_pro and user_data.pro_until:
                        # Convert to readable format
                        expiry_str = user_data.pro_until.strftime("%d.%m.%Y %H:%M")
                        tool_result_content = f"У пользователя активна Pro подписка. Истекает: {expiry_str}"
                    elif is_pro and user_data.trial_ends_at:
                        expiry_str = user_data.trial_ends_at.strftime("%d.%m.%Y %H:%M")
                        tool_result_content = f"У пользователя активен Pro Trial (тестовый период). Истекает: {expiry_str}"
                    else:
                        tool_result_content = "У пользователя НЕТ активной Pro подписки. Предложи купить через /buy_pro."

                # Добавляем результат инструмента в messages для следующего шага LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_content
                })

            # --- Retry / Final Attempt Logic after Max Steps ---
            logger.warning(f"Agent reached MAX STEPS ({max_steps}) for user {user_id}")
            
            # Добавляем системное сообщение с требованием завершить и объясниться
            messages.append({
                "role": "system",
                "content": (
                    "CRITICAL: You have reached the MAXIMUM NUMBER OF STEPS (infinite loop detected).\n"
                    "STOP calling tools immediately.\n"
                    "REPLY to the user in your persona style (e.g., 'Бля, я затупил и ушел в цикл...').\n"
                    "Explain what you tried to do and ask for clarification."
                )
            })
            
            # Делаем финальный запрос без инструментов (force text)
            final_response = await self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                # tools=None, # Не передаем инструменты, чтобы он не пытался их вызвать
            )
            
            final_content = final_response.choices[0].message.content
            if final_content:
                await user_service.save_chat_message(user_id, "assistant", final_content)
                return final_content
            else:
                return "⚠ Бот устал и прилег отдохнуть (Max Steps Error)."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка (Agent Error)."

        except Exception as e:
            logger.error(f"Router Agent failed: {e}")
            return "Произошла ошибка (Agent Error)."

ai_service = AIService()
