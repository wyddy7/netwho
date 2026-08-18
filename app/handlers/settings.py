from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger
from app.services.user_service import user_service
from app.schemas import UserSettings, RecallSettings
from app.config import settings as app_settings

router = Router()

class SettingsStates(StatesGroup):
    waiting_for_focus = State()
    waiting_for_time = State()

async def get_settings_menu(user_id: int):
    """
    Generates the text and markup for the main settings menu.
    """
    user = await user_service.get_user(user_id)
    is_pro = await user_service.is_pro(user_id)
    
    # Status Text
    if is_pro:
        if user.pro_until:
            expiry = user.pro_until.strftime("%d.%m.%Y")
            sub_status = f"⭐️ <b>PRO Active</b> (до {expiry})"
        elif user.trial_ends_at:
            expiry = user.trial_ends_at.strftime("%d.%m.%Y %H:%M")
            sub_status = f"🎁 <b>Pro Trial</b> (до {expiry})"
        else:
            # Should not happen if is_pro is True, but fallback
            sub_status = "⭐️ <b>PRO Active</b>"
    else:
        sub_status = "Free Plan"

    # Effective History Depth
    history_depth = app_settings.CHAT_HISTORY_DEPTH if is_pro else 3

    text = (
        "⚙️ <b>Настройки NetWho</b>\n\n"
        f"Статус: {sub_status}\n"
        f"Глубина памяти: <b>{history_depth} сообщений</b>\n\n"
        "Выберите раздел:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 Recall (Напоминания)", callback_data="settings_recall")
    builder.button(text="✅ Approves (Подтверждения)", callback_data="settings_approves")
    builder.button(text="📜 History (История)", callback_data="settings_history")
    
    # Add Buy Button if not Pro (or expiring soon)
    if not is_pro:
         builder.button(text=f"💎 Купить Pro ({app_settings.PRICE_MONTH_STARS} ⭐️)", callback_data="buy_pro_callback")

    builder.button(text="❌ Закрыть", callback_data="close_settings")
    builder.adjust(1)
    
    return text, builder.as_markup()

@router.callback_query(F.data == "open_settings")
async def open_settings_callback(callback: types.CallbackQuery, state: FSMContext):
    # Очищаем состояние
    await state.clear()
    
    # Используем ID пользователя, нажавшего кнопку, а не ID бота из сообщения
    user_id = callback.from_user.id
    text, reply_markup = await get_settings_menu(user_id)
    
    # Отправляем новым сообщением, так как это результат нажатия на кнопку "Настройки" в финальном сообщении
    # (или можно редактировать, но обычно настройки открываются поверх)
    # Если мы хотим поведение как /settings - то новое сообщение.
    await callback.message.answer(text, reply_markup=reply_markup)
    await callback.answer()

@router.message(Command("settings"))
async def cmd_settings(message: types.Message, state: FSMContext):
    """
    Главное меню настроек.
    """
    await state.clear()
    
    user_id = message.from_user.id
    text, reply_markup = await get_settings_menu(user_id)
    
    await message.answer(text, reply_markup=reply_markup)

# --- RECALL SETTINGS ---

@router.callback_query(F.data == "settings_recall")
async def show_recall_settings(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await user_service.get_user(user_id)
    rs = user.recall_settings if user else RecallSettings()
    is_pro = await user_service.is_pro(user_id)
    
    status_icon = "✅" if rs.enabled else "❌"
    focus_text = rs.focus if rs.focus else "<i>Общий (Без фильтра)</i>"
    time_text = rs.time if rs.time else "15:00"
    
    # Дни недели
    days_map = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    days_str = ", ".join([days_map[d] for d in sorted(rs.days)]) if rs.days else "Никогда"

    text = (
        "🎲 <b>Настройки Active Recall</b>\n\n"
        f"Статус: <b>{status_icon}</b>\n"
        f"Дни: <b>{days_str}</b>\n"
        f"Время: <b>{time_text}</b> (МСК)\n"
        f"Фокус: {focus_text}\n\n"
        "<i>Нажми на день, чтобы включить/выключить его.</i>"
    )
    
    if not is_pro:
        text += "\n\n⚠️ <i>В Free-версии можно выбрать только 1 день в неделю.</i>"
    
    builder = InlineKeyboardBuilder()
    
    # 1. Toggle On/Off
    builder.button(
        text=f"{'Выключить' if rs.enabled else 'Включить'}", 
        callback_data=f"recall_toggle_{not rs.enabled}"
    )
    
    # 2. Days Row
    for idx, name in enumerate(days_map):
        is_active = idx in rs.days
        btn_text = f"✅ {name}" if is_active else name
        builder.button(text=btn_text, callback_data=f"recall_day_{idx}")
    
    # 3. Focus & Back & Time
    builder.button(text="🎯 Изменить Фокус", callback_data="recall_focus_edit")
    builder.button(text=f"⏰ Время: {time_text}", callback_data="recall_time_edit")
    builder.button(text="⬅️ Назад", callback_data="settings_main")
    
    # Layout: 1 (Toggle), 7 (Days), 2 (Focus, Time), 1 (Back)
    builder.adjust(1, 7, 2, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("recall_toggle_"))
async def on_recall_toggle(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_val = callback.data.split("_")[2] == "True"
    
    user = await user_service.get_user(user_id)
    rs = user.recall_settings
    rs.enabled = new_val
    
    await user_service.update_recall_settings(user_id, rs)
    await show_recall_settings(callback)

@router.callback_query(F.data.startswith("recall_day_"))
async def on_recall_day(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    day_idx = int(callback.data.split("_")[2])
    
    user = await user_service.get_user(user_id)
    rs = user.recall_settings
    
    if day_idx in rs.days:
        rs.days.remove(day_idx)
    else:
        # Check limit
        is_pro = await user_service.is_pro(user_id)
        if not is_pro and len(rs.days) >= 1:
            await callback.answer("🔒 Лимит Free: только 1 день. Отключите другой день сначала.", show_alert=True)
            return

        rs.days.append(day_idx)
        rs.days.sort()
        
    await user_service.update_recall_settings(user_id, rs)
    await show_recall_settings(callback)

@router.callback_query(F.data == "recall_focus_edit")
async def on_recall_focus_edit(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_focus_input")
    
    await callback.message.edit_text(
        "🎯 <b>Настройка Фокуса</b>\n\n"
        "Напиши тему или категорию людей, о которых ты хочешь получать напоминания.\n"
        "Например: <i>'Инвесторы', 'IT-директора', 'Друзья со школы'</i>.\n"
        "Или напиши <b>'-'</b> чтобы сбросить фокус.\n\n"
        "<i>Используй /settings или /cancel чтобы выйти.</i>",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SettingsStates.waiting_for_focus)
    await callback.answer()

@router.message(SettingsStates.waiting_for_focus, ~F.text.startswith("/"))
async def on_focus_entered(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    
    user = await user_service.get_user(user_id)
    rs = user.recall_settings
    
    if text == "-" or text.lower() == "сброс":
        rs.focus = None
        reply = "✅ Фокус сброшен. Теперь ищем по всей базе."
    else:
        rs.focus = text
        reply = f"✅ Фокус установлен: <b>{text}</b>"
        
    await user_service.update_recall_settings(user_id, rs)
    await state.clear()
    
    await message.answer(reply)

@router.callback_query(F.data == "recall_time_edit")
async def on_recall_time_edit(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_time_input")
    
    await callback.message.edit_text(
        "⏰ <b>Настройка Времени</b>\n\n"
        "Во сколько присылать напоминания? (МСК)\n"
        "Напиши время в формате <b>ЧЧ:ММ</b>.\n"
        "Например: <i>09:00</i>, <i>18:30</i>.\n\n"
        "<i>Используй /settings или /cancel чтобы выйти.</i>",
        reply_markup=builder.as_markup()
    )
    await state.set_state(SettingsStates.waiting_for_time)
    await callback.answer()

@router.message(SettingsStates.waiting_for_time, ~F.text.startswith("/"))
async def on_time_entered(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Simple validation
    try:
        hour, minute = map(int, text.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        formatted_time = f"{hour:02d}:{minute:02d}"
    except Exception:
        await message.answer("⚠ Неверный формат. Пожалуйста, введите время как <b>09:00</b> или <b>15:30</b>.")
        return

    user = await user_service.get_user(user_id)
    rs = user.recall_settings
    rs.time = formatted_time
        
    await user_service.update_recall_settings(user_id, rs)
    await state.clear()
    
    await message.answer(f"✅ Время напоминаний установлено: <b>{formatted_time}</b>")

# --- APPROVES SETTINGS ---


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
    user_id = callback.from_user.id
    is_pro = await user_service.is_pro(user_id)
    depth = app_settings.CHAT_HISTORY_DEPTH if is_pro else 3
    
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
            logger.exception("Error resetting history UI")

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
    user_id = callback.from_user.id
    text, reply_markup = await get_settings_menu(user_id)
    await callback.message.edit_text(text, reply_markup=reply_markup)

@router.callback_query(F.data == "close_settings")
async def on_close(callback: types.CallbackQuery):
    await callback.message.delete()

# --- Cancel Handlers ---

@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """
    Отмена текущего действия и выход из состояния FSM.
    """
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Действие отменено.")
    else:
        await message.answer("Нет активных действий для отмены.")

@router.callback_query(F.data == "cancel_focus_input")
async def cancel_focus_input(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ввод фокуса отменен.")
    await callback.answer()

@router.callback_query(F.data == "cancel_time_input")
async def cancel_time_input(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ввод времени отменен.")
    await callback.answer()
