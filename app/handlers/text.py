from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.schemas import ContactCreate

router = Router()

async def handle_agent_response(message: types.Message, response):
    """
    Общая логика обработки ответа от агента (для текста и голоса).
    """
    try:
        # 1. Результаты поиска (list)
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
        
        # 2. Результат добавления контакта (ContactCreate)
        elif isinstance(response, ContactCreate):
            res_text = (
                f"✅ <b>Записал:</b> {response.name}\n\n"
                f"📝 {response.summary}"
            )
            await message.reply(res_text)

        # 3. Текстовый ответ (str)
        elif isinstance(response, str):
            await message.reply(response)

    except Exception as e:
        logger.error(f"Agent response handler error: {e}")
        await message.reply("Ошибка при отображении ответа.")

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    """
    Обработчик текстовых сообщений.
    """
    user_id = message.from_user.id
    user_text = message.text
    
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        response = await ai_service.run_router_agent(user_text, user_id)
        await handle_agent_response(message, response)
            
    except Exception as e:
        logger.error(f"Text handler error: {e}")
        await message.reply("Что-то пошло не так.")

@router.callback_query(F.data.startswith("del_contact_"))
async def on_delete_click(callback: types.CallbackQuery):
    contact_id = callback.data.replace("del_contact_", "")
    user_id = callback.from_user.id
    
    try:
        success = await search_service.delete_contact(contact_id, user_id)
        if success:
            # Пытаемся сохранить оригинальный текст сообщения, добавляя пометку
            original_text = callback.message.html_text if callback.message.html_text else "Контакт"
            await callback.message.edit_text(f"🗑 {original_text}\n\n<b>(Удалено)</b>")
            await callback.answer("Контакт удален")
        else:
            await callback.answer("Ошибка: Контакт не найден", show_alert=True)
    except Exception as e:
        logger.error(f"Delete callback error: {e}")
        await callback.answer("Ошибка при удалении", show_alert=True)
