from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.services.user_service import user_service
from app.schemas import UserSettings
from app.config import settings as app_settings

router = Router()

@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    """
    Главное меню настроек.
    """
    text = (
        "⚙️ <b>Настройки NetWho</b>\n\n"
        "Выберите раздел:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approves (Подтверждения)", callback_data="settings_approves")
    builder.button(text="📜 History (История)", callback_data="settings_history")
    builder.button(text="❌ Закрыть", callback_data="close_settings")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "settings_approves")
async def show_approves(callback: types.CallbackQuery):
    """
    Подменю Approves (Rage Mode настройки).
    """
    user_id = callback.from_user.id
    user = await user_service.get_user(user_id)
    
    settings = user.settings if user and user.settings else UserSettings()
    
    # Иконки статусов
    add_icon = "✅" if settings.confirm_add else "❌"
    del_icon = "✅" if settings.confirm_delete else "❌"
    
    text = (
        "🛡 <b>Настройки Подтверждений (Approves)</b>\n\n"
        f"• <b>Добавление контакта:</b> {add_icon}\n"
        f"• <b>Удаление контакта:</b> {del_icon}\n\n"
        "<i>✅ — Бот спросит подтверждение.\n"
        "❌ — Бот сделает сразу (Rage Mode).</i>"
    )
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки переключения
    builder.button(
        text=f"Add: {'Выключить' if settings.confirm_add else 'Включить'}", 
        callback_data=f"toggle_add_{not settings.confirm_add}"
    )
    builder.button(
        text=f"Delete: {'Выключить' if settings.confirm_delete else 'Включить'}", 
        callback_data=f"toggle_del_{not settings.confirm_delete}"
    )
    
    # Общая кнопка Rage Mode (Вырубить всё)
    if settings.confirm_add or settings.confirm_delete:
        builder.button(text="🔥 Rage Mode (Все OFF)", callback_data="set_rage_on")
    else:
        builder.button(text="🛡 Safe Mode (Все ON)", callback_data="set_rage_off")

    builder.button(text="⬅️ Назад", callback_data="settings_main")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "settings_history")
async def show_history(callback: types.CallbackQuery):
    """
    Подменю History.
    """
    depth = app_settings.CHAT_HISTORY_DEPTH
    text = (
        "📜 <b>Настройки Истории</b>\n\n"
        f"Глубина контекста: <b>{depth} сообщений</b>.\n"
        "Вы можете сбросить (удалить) последние сообщения из памяти бота, чтобы начать диалог с чистого листа.\n\n"
        "<i>Это полезно, если бот запутался в контексте.</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Сбросить ВСЮ историю", callback_data="reset_history_confirm")
    builder.button(text="⬅️ Назад", callback_data="settings_main")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "reset_history_confirm")
async def reset_history_confirm(callback: types.CallbackQuery):
    """
    Выполнение сброса истории.
    """
    user_id = callback.from_user.id
    
    await user_service.clear_history(user_id)
    # Важно: Добавляем системное сообщение о сбросе, чтобы агент "почувствовал" это, если вдруг контекст сохранился где-то
    await user_service.save_chat_message(user_id, "system", "[System] User cleared conversation history. Memory wiped.")
    
    await callback.answer(f"История полностью очищена!", show_alert=True)
        
    # Возвращаемся в меню истории
    try:
        await show_history(callback)
    except Exception as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error resetting history UI: {e}")

@router.callback_query(F.data.startswith("toggle_"))
async def toggle_setting(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action, value_str = callback.data.split("_")[1], callback.data.split("_")[2]
    new_value = value_str == "True"
    
    user = await user_service.get_user(user_id)
    settings = user.settings if user else UserSettings()
    
    if action == "add":
        settings.confirm_add = new_value
    elif action == "del":
        settings.confirm_delete = new_value
        
    await user_service.update_settings(user_id, settings)
    await show_approves(callback) # Обновляем экран

@router.callback_query(F.data.startswith("set_rage_"))
async def set_rage_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    mode = callback.data.split("_")[2] # on или off
    
    user = await user_service.get_user(user_id)
    settings = user.settings if user else UserSettings()
    
    if mode == "on":
        settings.confirm_add = False
        settings.confirm_delete = False
    else:
        settings.confirm_add = True
        settings.confirm_delete = True
        
    await user_service.update_settings(user_id, settings)
    await show_approves(callback)

@router.callback_query(F.data == "settings_main")
async def back_to_main(callback: types.CallbackQuery):
    # Просто вызываем cmd_settings, но нужно передать Message, а у нас Callback
    # Проще отредактировать текст
    text = "⚙️ <b>Настройки NetWho</b>\n\nВыберите раздел:"
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approves (Подтверждения)", callback_data="settings_approves")
    builder.button(text="📜 History (История)", callback_data="settings_history")
    builder.button(text="❌ Закрыть", callback_data="close_settings")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "close_settings")
async def on_close(callback: types.CallbackQuery):
    await callback.message.delete()
