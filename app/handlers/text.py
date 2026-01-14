import secrets
from uuid import UUID
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.utils.chat_action import KeepTyping
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.services.user_service import user_service
from app.services.news_service import news_service
from app.services.recall_service import recall_service
from app.services.subscription_service import check_limits, get_limit_message
from app.config import settings
from app.schemas import (
    ContactCreate, ContactDraft, UserSettings, 
    ContactDeleteAsk, ContactUpdateAsk, ActionConfirmed, ActionCancelled
)

router = Router()

# {user_id: {"type": "add"|"del"|"update", "data": ..., "request_id": "..."}}
pending_actions = {}

def generate_request_id() -> str:
    """Генерирует короткий случайный ID для запроса (8 символов)."""
    return secrets.token_urlsafe(6)[:8]  # Берем первые 8 символов

async def handle_agent_response(message: types.Message, response):
    try:
        user_id = message.from_user.id

        # 1. Поиск (Список)
        if isinstance(response, list):
            if not response:
                await message.reply("Ничего не нашел 🤷‍♂️")
                return
            
            header = f"🔎 <b>Нашел {len(response)} контактов:</b>\n\n"
            items_text = []
            builder = InlineKeyboardBuilder()
            
            for res in response:
                short_id = str(res.id)[:5]
                org_name = getattr(res, "org_name", None)
                if org_name:
                    scope_badge = f" <i>📢 {org_name}</i>"
                else:
                    scope_badge = " <i>🔒 Личное</i>"

                item_str = f"🆔 <code>{short_id}</code> | 👤 <b>{res.name}</b>{scope_badge}"
                if res.summary:
                    item_str += f"\n📝 {res.summary}"
                items_text.append(item_str)
                builder.button(text=f"🗑 {short_id}", callback_data=f"pre_del_{res.id}")

            full_text = header + "\n\n".join(items_text)
            builder.adjust(3)
            await message.reply(full_text, reply_markup=builder.as_markup())
        
        # 2. ДРАФТ СОЗДАНИЯ (Нужно подтверждение)
        elif isinstance(response, ContactDraft):
            # Check limits
            if not await check_limits(user_id):
                limit_msg = await get_limit_message(user_id)
                await message.reply(limit_msg)
                return

            request_id = generate_request_id()
            # --- Story 16: Scope Selection ---
            orgs = await search_service.get_user_orgs(user_id)
            pending_actions[user_id] = {"type": "add", "data": response, "request_id": request_id, "orgs": orgs}
            
            builder = InlineKeyboardBuilder()
            
            if orgs:
                text = (
                    f"📝 <b>Проверь перед сохранением:</b>\n"
                    f"<i>(Выбери, куда сохранить)</i>\n\n"
                    f"👤 <b>{response.name}</b>\n"
                    f"{response.summary}"
                )
                # Personal
                builder.button(text="🔒 Личное", callback_data=f"scope_{request_id}_personal")
                # Orgs
                for org in orgs:
                    builder.button(text=f"📢 {org['name']}", callback_data=f"scope_{request_id}_{org['id']}")
                
                builder.button(text="❌ Отмена", callback_data="cancel_action")
                builder.adjust(1)
            else:
                text = (
                    f"📝 <b>Проверь перед сохранением:</b>\n"
                    f"<i>(Нажми кнопку или напиши «Да»)</i>\n\n"
                    f"👤 <b>{response.name}</b>\n"
                    f"{response.summary}\n\n"
                    "Сохранить?"
                )
                builder.button(text="💾 Сохранить", callback_data=f"confirm_{request_id}")
                builder.button(text="❌ Отмена", callback_data="cancel_action")
                builder.adjust(2)
            
            await message.reply(text, reply_markup=builder.as_markup())

        # 3. ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ (Нужно подтверждение)
        elif isinstance(response, ContactDeleteAsk):
            request_id = generate_request_id()
            pending_actions[user_id] = {"type": "del", "data": response.contact_id, "request_id": request_id}
            
            text = (
                f"⚠️ <b>Удалить этот контакт?</b>\n"
                f"<i>(Нажми кнопку или напиши «Да»)</i>\n\n"
                f"👤 <b>{response.name}</b>\n"
                f"{response.summary}"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text="🗑 Удалить", callback_data=f"confirm_{request_id}")
            builder.button(text="❌ Отмена", callback_data="cancel_action")
            builder.adjust(2)
            await message.reply(text, reply_markup=builder.as_markup())

        # 4. ПОДТВЕРЖДЕНИЕ ОБНОВЛЕНИЯ
        elif isinstance(response, ContactUpdateAsk):
            request_id = generate_request_id()
            pending_actions[user_id] = {"type": "update", "data": response, "request_id": request_id}
            
            text = (
                f"✏️ <b>Обновить контакт?</b>\n"
                f"<i>(Нажми кнопку или напиши «Да»)</i>\n\n"
                f"👤 <b>{response.name}</b>\n"
                f"Было:\n{response.old_summary or '...'}\n\n"
                f"Станет:\n{response.new_summary}"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text="💾 Сохранить", callback_data=f"confirm_{request_id}")
            builder.button(text="❌ Отмена", callback_data="cancel_action")
            builder.adjust(2)
            await message.reply(text, reply_markup=builder.as_markup())
        
        # 5. ДЕЙСТВИЕ ПОДТВЕРЖДЕНО (из текста "да")
        elif isinstance(response, ActionConfirmed):
            action = pending_actions.pop(user_id, None)
            if not action:
                await message.reply("⚠️ Нет ожидающих действий.")
                return

            if action["type"] == "add":
                draft = action["data"]
                await search_service.create_contact(draft)
                await message.reply(f"✅ <b>Записал:</b> {draft.name}")
            
            elif action["type"] == "del":
                contact_id = action["data"]
                logger.error(f"[handle_agent_response.ActionConfirmed.del] ENTRY: contact_id={contact_id} (type: {type(contact_id).__name__}), user_id={user_id} (type: {type(user_id).__name__})")
                try:
                    logger.error(f"[handle_agent_response.ActionConfirmed.del] Calling delete_contact...")
                    success = await search_service.delete_contact(contact_id, user_id)
                    logger.error(f"[handle_agent_response.ActionConfirmed.del] delete_contact returned: success={success}")
                    if success:
                        logger.error(f"[handle_agent_response.ActionConfirmed.del] SUCCESS: Contact deleted. Sending confirmation message.")
                        await message.reply(f"🗑 Контакт удален.")
                    else:
                        logger.error(f"[handle_agent_response.ActionConfirmed.del] FAILED: Contact not found (success=False)")
                        await message.reply("❌ Ошибка: контакт не найден")
                except Exception as e:
                    from app.services.search_service import AccessDenied
                    logger.error(f"[handle_agent_response.ActionConfirmed.del] EXCEPTION: {type(e).__name__}: {e}", exc_info=True)
                    if isinstance(e, AccessDenied):
                        logger.error(f"[handle_agent_response.ActionConfirmed.del] AccessDenied caught: {e}")
                        await message.reply("❌ Контакт не найден или не принадлежит вам")
                    else:
                        logger.error(f"[handle_agent_response.ActionConfirmed.del] Other exception: {e}")
                        await message.reply("❌ Ошибка при удалении")

            elif action["type"] == "update":
                update_ask = action["data"]
                await search_service.update_contact(update_ask.contact_id, user_id, update_ask.updates)
                await message.reply(f"✅ <b>Обновил:</b> {update_ask.name}")
            
        # 6. ДЕЙСТВИЕ ОТМЕНЕНО (из текста "нет")
        elif isinstance(response, ActionCancelled):
            pending_actions.pop(user_id, None)
            await message.reply("❌ Действие отменено.")


        # 6. УСПЕХ (Rage Mode или авто-сохранение)
        elif isinstance(response, ContactCreate):
            # Check limits
            if not await check_limits(user_id):
                limit_msg = await get_limit_message(user_id)
                await message.reply(limit_msg)
                return

            res_text = (
                f"✅ <b>Записал:</b> {response.name}\n\n"
                f"📝 {response.summary}"
            )
            await message.reply(res_text)

        # 7. Текст
        elif isinstance(response, str):
            try:
                await message.reply(response)
            except Exception as e:
                logger.warning(f"Failed to send text with parse_mode (HTML?): {e}. Sending plain text.")
                await message.reply(response, parse_mode=None)

    except Exception as e:
        logger.error(f"Agent response handler error: {e}")
        await message.reply("Ошибка при отображении ответа.")

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    
    # --- Confirmation Lock (Блокировка действий) ---
    if user_id in pending_actions:
        # Пропускаем, пусть агент подтверждает или отменяет
        pass 
        
    async with KeepTyping(message.bot, message.chat.id):
        # --- NEWS JACKING (Реакция на ссылки) ---
        url = news_service.extract_url(user_text)
        if url:
            logger.info(f"Detected URL: {url}. Starting News-Jacking flow.")
            
            # Check Limits for News Jacking
            is_pro = await user_service.is_pro(user_id)
            
            if not is_pro:
                user_db = await user_service.get_user(user_id)
                current_count = user_db.news_jacks_count
                if current_count >= settings.FREE_NEWS_JACKS_LIMIT:
                    await message.reply(
                        f"😎 <b>Я знаю, кому это скинуть, но топливо кончилось.</b>\n\n"
                        f"Лимит Free-версии: {settings.FREE_NEWS_JACKS_LIMIT} анализа ссылок.\n"
                        f"Pro-версия снимет лимиты за {settings.PRICE_MONTH_STARS}⭐️.\n\n"
                        "👉 /buy_pro"
                    )
                    return
            
            status_msg = await message.reply("👀 Читаю статью...")
            
            # 1. Скачиваем контент
            article_text = await news_service.fetch_article_content(url)
            if article_text:
                # 2. Ищем, кому это может быть интересно
                # Формируем поисковый запрос для Vector DB из заголовка/начала статьи
                # (Можно попросить LLM сделать саммари для поиска, но для скорости берем первые 500 символов)
                query_text = article_text[:500] 
                
                # Ищем контакты, близкие по смыслу к статье
                relevant_contacts = await search_service.search(query_text, user_id, limit=5)
                
                if relevant_contacts:
                    # 3. Генерируем "Connect" сообщение
                    # Используем recall_service для генерации совета, но с контекстом статьи
                    
                    # Хак: используем generate_recall_message, но передаем статью как "focus"
                    user = await user_service.get_user(user_id)
                    bio = user.bio if user else None
                    
                    # Кастомизируем промпт "на лету" (или создадим отдельный метод, если нужно супер качество)
                    # Пока попробуем через существующий метод, передав статью в focus
                    focus_context = f"Found interesting article: {url}\nSummary: {article_text[:300]}...\nGoal: Suggest who to send this article to and why."
                    
                    advice = await recall_service.generate_recall_message(relevant_contacts, bio=bio, focus=focus_context)
                    
                    # Increment counter and add footer
                    limit_note = ""
                    if not is_pro:
                        new_count = await user_service.increment_news_jacks(user_id)
                        remaining = max(0, settings.FREE_NEWS_JACKS_LIMIT - new_count)
                        limit_note = f"\n\n<i>🔥 Осталось бесплатных анализов: {remaining}</i>"

                    await status_msg.edit_text(
                        f"🔗 <b>Анализ ссылки:</b>\n\n"
                        f"{advice}"
                        f"{limit_note}"
                    )
                    return # Прерываем стандартный флоу, чтобы не запускать агента на ссылку
                else:
                     await status_msg.edit_text("Прочитал, но не нашел в базе никого, кому это точно было бы интересно.")
                     return
            else:
                 await status_msg.edit_text("Не смог прочитать статью (Jina не справилась).")
                 # Fallback to standard agent flow if link fails
        
        # --- STANDARD AGENT FLOW ---
        try:
            response = await ai_service.run_router_agent(user_text, user_id)
            await handle_agent_response(message, response)
        except Exception as e:
            logger.error(f"Text handler error: {e}")
            await message.reply("Что-то пошло не так.")

# --- CALLBACK HANDLERS ---

@router.callback_query(F.data.startswith("confirm_"))
async def on_action_confirm(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    request_id = callback.data.replace("confirm_", "")
    
    action = pending_actions.get(user_id)
    
    if not action:
        await callback.answer("Время ожидания истекло", show_alert=True)
        await callback.message.delete()
        return
    
    # Проверка request_id для защиты от устаревших кнопок
    if action.get("request_id") != request_id:
        await callback.answer("Кнопка устарела", show_alert=True)
        await callback.message.delete()
        return
    
    # Удаляем из pending только после проверки request_id
    pending_actions.pop(user_id)

    try:
        if action["type"] == "add":
            draft = action["data"]
            try:
                contact_db = await search_service.create_contact(draft)
                await callback.message.edit_text(
                    f"✅ <b>Записал:</b> {draft.name}\n\n📝 {draft.summary}"
                )
                await callback.answer("Сохранено!")
                # System Feedback Loop
                await user_service.save_chat_message(user_id, "system", f"[System] Contact '{draft.name}' (ID: {contact_db.id}) created successfully.")
            except Exception as e:
                from app.services.search_service import AccessDenied
                if isinstance(e, AccessDenied):
                    await callback.answer(str(e), show_alert=True)
                else:
                    raise
            
        elif action["type"] == "del":
            contact_id = action["data"]
            logger.error(f"[on_action_confirm.del] ENTRY: contact_id={contact_id} (type: {type(contact_id).__name__}), user_id={user_id} (type: {type(user_id).__name__})")
            try:
                logger.error(f"[on_action_confirm.del] Calling delete_contact...")
                # delete_contact теперь сам проверяет права и выбрасывает AccessDenied
                success = await search_service.delete_contact(contact_id, user_id)
                logger.error(f"[on_action_confirm.del] delete_contact returned: success={success}")
                if success:
                    logger.error(f"[on_action_confirm.del] SUCCESS: Contact deleted. Updating UI.")
                    await callback.message.edit_text(f"🗑 Контакт удален.")
                    await callback.answer("Удалено!")
                    # System Feedback Loop
                    await user_service.save_chat_message(user_id, "system", f"[System] Contact {contact_id} deleted successfully.")
                else:
                    logger.error(f"[on_action_confirm.del] FAILED: Contact not found (success=False)")
                    await callback.answer("Ошибка: контакт не найден", show_alert=True)
                    await user_service.save_chat_message(user_id, "system", f"[System] Failed to delete contact {contact_id}: Not found.")
            except Exception as e:
                from app.services.search_service import AccessDenied
                logger.error(f"[on_action_confirm.del] EXCEPTION: {type(e).__name__}: {e}", exc_info=True)
                if isinstance(e, AccessDenied):
                    logger.error(f"[on_action_confirm.del] AccessDenied caught: {e}")
                    await callback.answer("❌ Контакт не найден или не принадлежит вам", show_alert=True)
                    await user_service.save_chat_message(user_id, "system", f"[System] Failed to delete contact {contact_id}: Access denied.")
                else:
                    logger.error(f"[on_action_confirm.del] Other exception: {e}")
                    await callback.answer("Ошибка выполнения", show_alert=True)
                    await user_service.save_chat_message(user_id, "system", f"[System] Action failed with error: {e}")
        
        elif action["type"] == "update":
            update_ask = action["data"]
            try:
                # update_contact теперь сам проверяет права и выбрасывает AccessDenied
                await search_service.update_contact(update_ask.contact_id, user_id, update_ask.updates)
                await callback.message.edit_text(
                    f"✅ <b>Обновил:</b> {update_ask.name}\n\n📝 {update_ask.new_summary}"
                )
                await callback.answer("Обновлено!")
                # System Feedback Loop
                await user_service.save_chat_message(user_id, "system", f"[System] Contact '{update_ask.name}' updated successfully.")
            except Exception as e:
                from app.services.search_service import AccessDenied
                if isinstance(e, AccessDenied):
                    logger.error(f"AccessDenied in on_action_confirm (update): {e}")
                    await callback.answer("❌ Контакт не найден или не принадлежит вам", show_alert=True)
                    await user_service.save_chat_message(user_id, "system", f"[System] Failed to update contact {update_ask.contact_id}: Access denied.")
                else:
                    logger.error(f"Update error in on_action_confirm: {e}")
                    await callback.answer("Ошибка при обновлении", show_alert=True)
                    await user_service.save_chat_message(user_id, "system", f"[System] Failed to update contact {update_ask.contact_id}: {e}")

    except Exception as e:
        logger.error(f"Action confirm error: {e}")
        await callback.answer("Ошибка выполнения", show_alert=True)
        await user_service.save_chat_message(user_id, "system", f"[System] Action failed with error: {e}")

@router.callback_query(F.data == "cancel_action")
async def on_action_cancel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    pending_actions.pop(user_id, None)
    await callback.message.delete()
    await callback.answer("Отменено")
    # System Feedback Loop
    await user_service.save_chat_message(user_id, "system", "[System] User cancelled the action.")

@router.callback_query(F.data.startswith("scope_"))
async def on_scope_select(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    # Format: scope_{req_id}_{value}
    # Value can be "personal" or UUID (which contains hyphens)
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
        
    request_id = parts[1]
    scope_value = parts[2]
    
    action = pending_actions.get(user_id)
    if not action or action.get("request_id") != request_id:
        await callback.answer("Время истекло", show_alert=True)
        await callback.message.delete()
        return
        
    pending_actions.pop(user_id)
    
    draft = action["data"]
    org_name = "Личное"
    org_id = None
    
    if scope_value == "personal":
        draft.org_id = None
    else:
        draft.org_id = scope_value
        org_id = scope_value
        orgs = action.get("orgs") or []
        for org in orgs:
            if str(org.get("id")) == str(scope_value):
                org_name = org.get("name") or "Организация"
                break
        else:
            org_name = "Организация"
    
    try:
        contact_db = await search_service.create_contact(draft)
        await callback.message.edit_text(
            f"✅ <b>Записал в {'📢 ' + org_name if org_id else '🔒 Личное'}:</b> {draft.name}\n\n📝 {draft.summary}"
        )
        await callback.answer("Сохранено!")
        await user_service.save_chat_message(
            user_id,
            "system",
            f"[System] Contact '{draft.name}' created in scope={scope_value} org_name={org_name}."
        )
    except Exception as e:
        from app.services.search_service import AccessDenied
        if isinstance(e, AccessDenied):
            await callback.answer(str(e), show_alert=True)
            # Re-show the scope selection? Or just let it be. 
            # The pending_actions is already popped.
        else:
            logger.error(f"Scope save error: {e}")
            await callback.answer("Ошибка сохранения", show_alert=True)

# --- ЛОГИКА УДАЛЕНИЯ ЧЕРЕЗ КНОПКУ КОРЗИНЫ В СПИСКЕ ---

@router.callback_query(F.data.startswith("pre_del_"))
async def on_pre_delete_click(callback: types.CallbackQuery):
    """
    Нажатие на корзину из списка поиска.
    """
    contact_id_str = callback.data.replace("pre_del_", "")
    user_id = callback.from_user.id
    
    # Валидация UUID перед запросом к БД
    try:
        contact_id = UUID(contact_id_str)
    except (ValueError, AttributeError):
        logger.warning(f"Invalid UUID format in callback_data: {contact_id_str} from user {user_id}")
        await callback.answer("❌ Неверный формат ID контакта", show_alert=True)
        return
    
    # КРИТИЧНО: Проверяем права владения через БД ДО любых действий
    contact = await search_service.get_contact_by_id(contact_id, user_id)
    if not contact:
        await callback.answer("❌ Контакт не найден или не принадлежит вам", show_alert=True)
        return
    
    user = await user_service.get_user(user_id)
    settings = user.settings if user else UserSettings()
    
    if settings.confirm_delete:
        contact_name = contact.name
        
        # Сохраняем в pending_actions, чтобы работала общая логика
        request_id = generate_request_id()
        pending_actions[user_id] = {"type": "del", "data": contact_id, "request_id": request_id}
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 Удалить", callback_data=f"confirm_{request_id}") # Используем общий колбэк
        builder.button(text="❌ Отмена", callback_data="cancel_action")
        builder.adjust(2)
        
        await callback.message.reply(
            f"⚠️ <b>Удалить этот контакт?</b>\n\n👤 {contact_name}\nID: <code>{str(contact_id)[:8]}</code>", 
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    else:
        # Rage Mode
        await perform_delete(callback, contact_id, user_id)

async def perform_delete(callback: types.CallbackQuery, contact_id: UUID, user_id: int):
    """
    Выполняет удаление контакта с проверкой прав через БД.
    delete_contact теперь сам проверяет права и выбрасывает AccessDenied.
    """
    logger.debug(f"[perform_delete] contact_id={contact_id}, user_id={user_id}")
    try:
        # delete_contact теперь сам проверяет права и выбрасывает AccessDenied
        success = await search_service.delete_contact(contact_id, user_id)
        if success:
            logger.info(f"[perform_delete] Contact deleted: contact_id={contact_id}, user_id={user_id}")
            await callback.answer("Контакт удален!", show_alert=True)
            await callback.message.answer(f"🗑 Контакт <code>{str(contact_id)[:8]}</code> удален.")
        else:
            logger.warning(f"[perform_delete] Contact not found: contact_id={contact_id}, user_id={user_id}")
            await callback.answer("Ошибка: Контакт не найден", show_alert=True)
    except Exception as e:
        from app.services.search_service import AccessDenied
        if isinstance(e, AccessDenied):
            logger.warning(f"[perform_delete] AccessDenied: contact_id={contact_id}, user_id={user_id}, error={e}")
            await callback.answer("❌ Контакт не найден или не принадлежит вам", show_alert=True)
        else:
            logger.error(f"[perform_delete] Exception: {type(e).__name__}: {e}", exc_info=True)
            await callback.answer("Ошибка при удалении", show_alert=True)

# --- ВРЕМЕННЫЙ ТЕСТОВЫЙ ХЕНДЛЕР ДЛЯ ПЕНТЕСТА ---
# TODO: Удалить после проверки защиты

@router.message(Command("test_hack"))
async def cmd_test_hack(message: types.Message):
    """
    Временный handler для тестирования защиты от удаления чужих контактов.
    Создает кнопку с callback_data="pre_del_{ID}", чтобы проверить, что защита работает.
    """
    from app.config import settings
    
    # Проверка, что команда доступна только админу
    if message.from_user.id != settings.ADMIN_ID:
        await message.answer("❌ Только для админа")
        return
    
    user_id = message.from_user.id
    args = message.text.split()
    
    # Если передан ID контакта как аргумент
    if len(args) >= 2:
        contact_id_str = args[1]
        
        # Валидация UUID
        try:
            contact_id = UUID(contact_id_str)
        except (ValueError, AttributeError):
            await message.answer(
                f"❌ <b>Неверный формат UUID</b>\n\n"
                f"Переданное значение: <code>{contact_id_str}</code>\n\n"
                f"UUID должен быть в формате: <code>123e4567-e89b-12d3-a456-426614174000</code>\n\n"
                f"Используй <code>/test_hack</code> без аргументов, чтобы увидеть список своих контактов."
            )
            return
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔥 ВЗЛОМАТЬ (Удалить контакт)", callback_data=f"pre_del_{contact_id}")
        builder.adjust(1)
        
        await message.answer(
            f"⚠️ <b>Тестовая кнопка удаления</b>\n\n"
            f"ID контакта: <code>{contact_id}</code>\n"
            f"Твой ID: <code>{user_id}</code>\n\n"
            "Нажми кнопку ниже. Если контакт не твой — защита должна сработать.",
            reply_markup=builder.as_markup()
        )
    else:
        # Показываем список контактов пользователя с их UUID
        contacts = await search_service.get_recent_contacts(user_id, limit=10)
        
        if not contacts:
            await message.answer(
                "❌ <b>У тебя нет контактов</b>\n\n"
                "Создай контакт через бота, а затем используй эту команду снова.\n\n"
                "Или используй: <code>/test_hack &lt;uuid_контакта&gt;</code>\n"
                "где UUID можно взять из базы данных (таблица <code>contacts</code>)."
            )
            return
        
        text_parts = [
            "🔒 <b>Тест защиты от удаления чужих контактов</b>\n\n",
            "<b>Твои контакты (последние 10):</b>\n\n"
        ]
        
        builder = InlineKeyboardBuilder()
        
        for i, contact in enumerate(contacts[:5], 1):  # Показываем первые 5 для краткости
            contact_uuid = str(contact.id)
            short_uuid = contact_uuid[:8] + "..."
            text_parts.append(
                f"{i}. <b>{contact.name}</b>\n"
                f"   UUID: <code>{contact_uuid}</code>\n"
            )
            builder.button(
                text=f"🔥 Тест {i}: {contact.name[:15]}",
                callback_data=f"pre_del_{contact_uuid}"
            )
        
        if len(contacts) > 5:
            text_parts.append(f"\n... и еще {len(contacts) - 5} контактов")
        
        text_parts.append(
            "\n<b>Или используй:</b> <code>/test_hack &lt;uuid&gt;</code>\n\n"
            "Нажми кнопку ниже, чтобы протестировать удаление своего контакта.\n"
            "Для теста чужого контакта используй UUID из базы данных."
        )
        
        builder.adjust(1)
        
        await message.answer(
            "".join(text_parts),
            reply_markup=builder.as_markup()
        )
