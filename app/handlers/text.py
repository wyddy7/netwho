from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.services.user_service import user_service
from app.schemas import ContactCreate, ContactDraft, UserSettings

router = Router()

# In-memory storage for drafts (для MVP сойдет, в проде лучше Redis)
# {user_id: ContactCreate}
pending_contacts = {}

async def handle_agent_response(message: types.Message, response):
    try:
        # 1. Поиск (Список)
        if isinstance(response, list):
            if not response:
                await message.reply("Ничего не нашел 🤷‍♂️")
                return
            
            # Собираем всё в одно сообщение
            header = f"🔎 <b>Нашел {len(response)} контактов:</b>\n\n"
            items_text = []
            
            builder = InlineKeyboardBuilder()
            
            for res in response:
                # Короткий ID (первые 5 символов) для визуальной идентификации
                short_id = str(res.id)[:5]
                
                # Формируем блок текста для контакта
                # 🆔 a1b2c | 👤 Имя
                item_str = f"🆔 <code>{short_id}</code> | 👤 <b>{res.name}</b>"
                if res.summary:
                    item_str += f"\n📝 {res.summary}"
                
                items_text.append(item_str)
                
                # Добавляем кнопку удаления с коротким ID
                # Callback data хранит полный ID
                builder.button(text=f"🗑 {short_id}", callback_data=f"pre_del_{res.id}")

            # Объединяем через пустую строку для читаемости
            full_text = header + "\n\n".join(items_text)
            
            # Выравниваем кнопки (по 3 в ряд, чтобы было компактно)
            builder.adjust(3)
            
            await message.reply(full_text, reply_markup=builder.as_markup())
        
        # 2. ДРАФТ (Нужно подтверждение)
        elif isinstance(response, ContactDraft):
            # Сохраняем во временное хранилище
            pending_contacts[message.from_user.id] = response
            
            text = (
                f"📝 <b>Проверь перед сохранением:</b>\n\n"
                f"👤 <b>{response.name}</b>\n"
                f"{response.summary}\n\n"
                "Сохранить?"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text="💾 Сохранить", callback_data="confirm_save")
            builder.button(text="❌ Отмена", callback_data="cancel_save")
            builder.adjust(2)
            await message.reply(text, reply_markup=builder.as_markup())

        # 3. УСПЕХ (Rage Mode или авто-сохранение)
        elif isinstance(response, ContactCreate):
            res_text = (
                f"✅ <b>Записал:</b> {response.name}\n\n"
                f"📝 {response.summary}"
            )
            await message.reply(res_text)

        # 4. Текст
        elif isinstance(response, str):
            await message.reply(response)

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

# Обработка подтверждения сохранения
@router.callback_query(F.data == "confirm_save")
async def on_save_confirm(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    draft = pending_contacts.pop(user_id, None)
    
    if not draft:
        await callback.answer("Время ожидания истекло", show_alert=True)
        await callback.message.delete()
        return

    try:
        await search_service.create_contact(draft)
        await callback.message.edit_text(
            f"✅ <b>Записал:</b> {draft.name}\n\n📝 {draft.summary}"
        )
        await callback.answer("Сохранено!")
    except Exception as e:
        logger.error(f"Save confirm error: {e}")
        await callback.answer("Ошибка сохранения", show_alert=True)

@router.callback_query(F.data == "cancel_save")
async def on_save_cancel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    pending_contacts.pop(user_id, None)
    await callback.message.delete()
    await callback.answer("Отменено")

# --- ЛОГИКА УДАЛЕНИЯ ---

@router.callback_query(F.data.startswith("pre_del_"))
async def on_pre_delete_click(callback: types.CallbackQuery):
    """
    Нажатие на корзину. Проверяем настройки.
    """
    contact_id = callback.data.replace("pre_del_", "")
    user_id = callback.from_user.id
    
    user = await user_service.get_user(user_id)
    settings = user.settings if user else UserSettings()
    
    if settings.confirm_delete:
        # Safe Mode: Спрашиваем подтверждение
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, удалить", callback_data=f"real_del_{contact_id}")
        builder.button(text="❌ Отмена", callback_data="cancel_del")
        builder.adjust(2)
        
        await callback.message.reply(
            f"⚠️ <b>Вы уверены, что хотите удалить этот контакт?</b>\nID: <code>{contact_id[:5]}</code>", 
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    else:
        # Rage Mode: Удаляем сразу
        await perform_delete(callback, contact_id, user_id)

@router.callback_query(F.data.startswith("real_del_"))
async def on_real_delete_confirm(callback: types.CallbackQuery):
    """
    Подтвержденное удаление.
    """
    contact_id = callback.data.replace("real_del_", "")
    user_id = callback.from_user.id
    await perform_delete(callback, contact_id, user_id)

@router.callback_query(F.data == "cancel_del")
async def on_cancel_delete(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("Отменено")

async def perform_delete(callback: types.CallbackQuery, contact_id: str, user_id: int):
    try:
        success = await search_service.delete_contact(contact_id, user_id)
        if success:
            if callback.message.reply_to_message:
                # Если это был ответ на сообщение с кнопками (диалог подтверждения), удаляем вопрос
                await callback.message.delete()
                await callback.message.answer(f"🗑 Контакт <code>{contact_id[:5]}</code> удален.")
            else:
                # Если это Rage mode (сразу нажали в списке)
                await callback.answer("Контакт удален!", show_alert=True)
                # Можно отправить сообщение в чат для лога
                await callback.message.answer(f"🗑 Контакт <code>{contact_id[:5]}</code> удален.")
        else:
            await callback.answer("Ошибка: Контакт не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Delete error: {e}")
        await callback.answer("Ошибка при удалении", show_alert=True)
