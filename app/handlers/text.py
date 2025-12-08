from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.services.user_service import user_service
from app.schemas import (
    ContactCreate, ContactDraft, UserSettings, 
    ContactDeleteAsk, ContactUpdateAsk, ActionConfirmed, ActionCancelled
)

router = Router()

# {user_id: {"type": "add"|"del"|"update", "data": ...}}
pending_actions = {}

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
                item_str = f"🆔 <code>{short_id}</code> | 👤 <b>{res.name}</b>"
                if res.summary:
                    item_str += f"\n📝 {res.summary}"
                items_text.append(item_str)
                builder.button(text=f"🗑 {short_id}", callback_data=f"pre_del_{res.id}")

            full_text = header + "\n\n".join(items_text)
            builder.adjust(3)
            await message.reply(full_text, reply_markup=builder.as_markup())
        
        # 2. ДРАФТ СОЗДАНИЯ (Нужно подтверждение)
        elif isinstance(response, ContactDraft):
            pending_actions[user_id] = {"type": "add", "data": response}
            
            text = (
                f"📝 <b>Проверь перед сохранением:</b>\n"
                f"<i>(Нажми кнопку или напиши «Да»)</i>\n\n"
                f"👤 <b>{response.name}</b>\n"
                f"{response.summary}\n\n"
                "Сохранить?"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text="💾 Сохранить", callback_data="confirm_action")
            builder.button(text="❌ Отмена", callback_data="cancel_action")
            builder.adjust(2)
            await message.reply(text, reply_markup=builder.as_markup())

        # 3. ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ (Нужно подтверждение)
        elif isinstance(response, ContactDeleteAsk):
            pending_actions[user_id] = {"type": "del", "data": response.contact_id}
            
            text = (
                f"⚠️ <b>Удалить этот контакт?</b>\n"
                f"<i>(Нажми кнопку или напиши «Да»)</i>\n\n"
                f"👤 <b>{response.name}</b>\n"
                f"{response.summary}"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text="🗑 Удалить", callback_data="confirm_action")
            builder.button(text="❌ Отмена", callback_data="cancel_action")
            builder.adjust(2)
            await message.reply(text, reply_markup=builder.as_markup())

        # 4. ПОДТВЕРЖДЕНИЕ ОБНОВЛЕНИЯ
        elif isinstance(response, ContactUpdateAsk):
            pending_actions[user_id] = {"type": "update", "data": response}
            
            text = (
                f"✏️ <b>Обновить контакт?</b>\n"
                f"<i>(Нажми кнопку или напиши «Да»)</i>\n\n"
                f"👤 <b>{response.name}</b>\n"
                f"Было:\n{response.old_summary or '...'}\n\n"
                f"Станет:\n{response.new_summary}"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text="💾 Сохранить", callback_data="confirm_action")
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
                await search_service.delete_contact(contact_id, user_id)
                await message.reply(f"🗑 Контакт удален.")

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
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = await ai_service.run_router_agent(user_text, user_id)
        await handle_agent_response(message, response)
    except Exception as e:
        logger.error(f"Text handler error: {e}")
        await message.reply("Что-то пошло не так.")

# --- CALLBACK HANDLERS ---

@router.callback_query(F.data == "confirm_action")
async def on_action_confirm(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = pending_actions.pop(user_id, None)
    
    if not action:
        await callback.answer("Время ожидания истекло", show_alert=True)
        await callback.message.delete()
        return

    try:
        if action["type"] == "add":
            draft = action["data"]
            await search_service.create_contact(draft)
            await callback.message.edit_text(
                f"✅ <b>Записал:</b> {draft.name}\n\n📝 {draft.summary}"
            )
            await callback.answer("Сохранено!")
            
        elif action["type"] == "del":
            contact_id = action["data"]
            success = await search_service.delete_contact(contact_id, user_id)
            if success:
                await callback.message.edit_text(f"🗑 Контакт удален.")
                await callback.answer("Удалено!")
            else:
                await callback.answer("Ошибка: контакт не найден", show_alert=True)
        
        elif action["type"] == "update":
            update_ask = action["data"]
            await search_service.update_contact(update_ask.contact_id, user_id, update_ask.updates)
            await callback.message.edit_text(
                f"✅ <b>Обновил:</b> {update_ask.name}\n\n📝 {update_ask.new_summary}"
            )
            await callback.answer("Обновлено!")
                
    except Exception as e:
        logger.error(f"Action confirm error: {e}")
        await callback.answer("Ошибка выполнения", show_alert=True)

@router.callback_query(F.data == "cancel_action")
async def on_action_cancel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    pending_actions.pop(user_id, None)
    await callback.message.delete()
    await callback.answer("Отменено")

# --- ЛОГИКА УДАЛЕНИЯ ЧЕРЕЗ КНОПКУ КОРЗИНЫ В СПИСКЕ ---

@router.callback_query(F.data.startswith("pre_del_"))
async def on_pre_delete_click(callback: types.CallbackQuery):
    """
    Нажатие на корзину из списка поиска.
    """
    contact_id = callback.data.replace("pre_del_", "")
    user_id = callback.from_user.id
    
    user = await user_service.get_user(user_id)
    settings = user.settings if user else UserSettings()
    
    if settings.confirm_delete:
        # Получаем инфу для красоты
        contact = await search_service.get_contact_by_id(contact_id, user_id)
        contact_name = contact.name if contact else "???"
        
        # Сохраняем в pending_actions, чтобы работала общая логика
        pending_actions[user_id] = {"type": "del", "data": contact_id}
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 Удалить", callback_data="confirm_action") # Используем общий колбэк
        builder.button(text="❌ Отмена", callback_data="cancel_action")
        builder.adjust(2)
        
        await callback.message.reply(
            f"⚠️ <b>Удалить этот контакт?</b>\n\n👤 {contact_name}\nID: <code>{contact_id[:5]}</code>", 
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    else:
        # Rage Mode
        await perform_delete(callback, contact_id, user_id)

async def perform_delete(callback: types.CallbackQuery, contact_id: str, user_id: int):
    try:
        success = await search_service.delete_contact(contact_id, user_id)
        if success:
            await callback.answer("Контакт удален!", show_alert=True)
            await callback.message.answer(f"🗑 Контакт <code>{contact_id[:5]}</code> удален.")
        else:
            await callback.answer("Ошибка: Контакт не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Delete error: {e}")
        await callback.answer("Ошибка при удалении", show_alert=True)
