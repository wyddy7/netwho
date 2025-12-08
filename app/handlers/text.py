from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.schemas import ContactCreate, ContactDraft

router = Router()

# In-memory storage for drafts (для MVP сойдет, в проде лучше Redis)
# {user_id: ContactCreate}
pending_contacts = {}

async def handle_agent_response(message: types.Message, response):
    try:
        # 1. Поиск
        if isinstance(response, list):
            if not response:
                await message.reply("Ничего не нашел 🤷‍♂️")
                return
            await message.reply(f"🔎 <b>Нашел {len(response)} контактов:</b>")
            for res in response:
                text = f"👤 <b>{res.name}</b>"
                if res.summary:
                    text += f"\n📝 {res.summary}"
                builder = InlineKeyboardBuilder()
                builder.button(text="🗑 Удалить", callback_data=f"del_contact_{res.id}")
                await message.answer(text, reply_markup=builder.as_markup())
        
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

# ... delete callback (остается старым) ...
@router.callback_query(F.data.startswith("del_contact_"))
async def on_delete_click(callback: types.CallbackQuery):
    contact_id = callback.data.replace("del_contact_", "")
    user_id = callback.from_user.id
    
    try:
        success = await search_service.delete_contact(contact_id, user_id)
        if success:
            original_text = callback.message.html_text if callback.message.html_text else "Контакт"
            await callback.message.edit_text(f"🗑 {original_text}\n\n<b>(Удалено)</b>")
            await callback.answer("Контакт удален")
        else:
            await callback.answer("Ошибка: Контакт не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Delete callback error: {e}")
        await callback.answer("Ошибка при удалении", show_alert=True)
