from datetime import datetime, timezone, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from app.utils.chat_action import KeepTyping
from app.config import settings

from app.services.user_service import user_service
from app.schemas import RecallSettings
from app.services.recall_service import recall_service

router = Router()

# Note: CommandStart is now handled in app/handlers/onboarding.py

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "🤖 <b>Помощь</b>\n\n"
        "🎤 <b>Голосовые:</b> Просто отправь голосовое сообщение, чтобы сохранить контакт или заметку.\n"
        "🔎 <b>Поиск:</b> Напиши <i>'Кто такой Дима?'</i> или <i>'Найди дизайнеров'</i>.\n"
        "🗑 <b>Удаление:</b> Напиши <i>'Удали Диму'</i> (я уточню, кого именно).\n\n"
        "⚙ <b>Команды:</b>\n"
        "/start - Перезапустить бота (Onboarding)\n"
        "/delete_me - Удалить все мои данные"
    )
    await message.answer(text)

@router.message(Command("recall"))
async def cmd_recall_manual(message: types.Message):
    """
    Debug: Принудительный запуск напоминания для текущего юзера
    """
    user_id = message.from_user.id
    
    # --- FREEMIUM CHECK ---
    user = await user_service.get_user(user_id)
    rs = user.recall_settings if user and user.recall_settings else RecallSettings()
    is_pro = await user_service.is_pro(user_id)

    if not is_pro:
        now = datetime.now(timezone.utc)
        if rs.last_manual_recall:
            # Ensure timezone awareness if pydantic parsed it as aware
            last_run = rs.last_manual_recall
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
                
            if now - last_run < timedelta(hours=24):
                await message.answer(
                    f"⏳ <b>Лимит Free-версии:</b> 1 ручной запуск в сутки.\n\n"
                    f"В Pro-версии можно вызывать recall сколько угодно.\n"
                    f"👉 /buy_pro ({settings.PRICE_MONTH_STARS} ⭐️)"
                )
                return

        # Update timestamp (we do it BEFORE sending to prevent spamming while generating)
        rs.last_manual_recall = now
        await user_service.update_recall_settings(user_id, rs)
    # ----------------------

    async with KeepTyping(message.bot, message.chat.id):
        # Получаем контекст пользователя (Bio, Focus)
        # user already fetched
        bio = user.bio if user else None
        focus = rs.focus

        # Теперь берем пачку контактов
        contacts = await recall_service.get_random_contacts_for_user(message.from_user.id, limit=4)
        
        if not contacts:
            await message.answer("🤷‍♂️ Контактов нет или все заархивированы.")
            return

        # Генерируем умное сообщение
        msg = await recall_service.generate_recall_message(contacts, bio=bio, focus=focus)
        
        # Кнопка Reroll
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Другой вариант", callback_data="recall_reroll")
        
        await message.answer(msg, reply_markup=builder.as_markup())

@router.callback_query(F.data == "recall_manual")
async def on_recall_manual_callback(callback: types.CallbackQuery):
    """
    Обработчик кнопки "Вспомнить кого-то" - просто вызывает команду /recall
    """
    user_id = callback.from_user.id
    
    # --- FREEMIUM CHECK ---
    user = await user_service.get_user(user_id)
    rs = user.recall_settings if user and user.recall_settings else RecallSettings()
    is_pro = await user_service.is_pro(user_id)

    if not is_pro:
        now = datetime.now(timezone.utc)
        if rs.last_manual_recall:
            last_run = rs.last_manual_recall
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
                
            if now - last_run < timedelta(hours=24):
                await callback.answer("⏳ Лимит Free: 1 раз в 24ч", show_alert=True)
                return

        rs.last_manual_recall = now
        await user_service.update_recall_settings(user_id, rs)
    # ----------------------

    await callback.answer()
    
    async with KeepTyping(callback.message.bot, callback.message.chat.id):
        # Получаем контекст пользователя (Bio, Focus)
        # user already fetched
        bio = user.bio if user else None
        focus = rs.focus

        # Теперь берем пачку контактов
        contacts = await recall_service.get_random_contacts_for_user(callback.from_user.id, limit=4)
        
        if not contacts:
            await callback.message.answer("🤷‍♂️ Контактов нет или все заархивированы.")
            return

        # Генерируем умное сообщение
        msg = await recall_service.generate_recall_message(contacts, bio=bio, focus=focus)
        
        # Кнопка Reroll
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Другой вариант", callback_data="recall_reroll")
        
        await callback.message.answer(msg, reply_markup=builder.as_markup())

@router.callback_query(F.data == "recall_reroll")
async def on_recall_reroll(callback: types.CallbackQuery):
    # --- FREEMIUM CHECK ---
    user_id = callback.from_user.id
    is_pro = await user_service.is_pro(user_id)
    if not is_pro:
        await callback.answer("🔒 Reroll (перегенерация) доступен только в Pro-версии.", show_alert=True)
        return
    # ----------------------

    await callback.message.edit_reply_markup(reply_markup=None) # Убираем кнопку у старого
    
    async with KeepTyping(callback.message.bot, callback.message.chat.id):
        user = await user_service.get_user(callback.from_user.id)
        bio = user.bio if user else None
        rs = user.recall_settings if user and user.recall_settings else RecallSettings()
        focus = rs.focus

        contacts = await recall_service.get_random_contacts_for_user(callback.from_user.id, limit=4)
        if not contacts:
            await callback.answer("Контактов не осталось", show_alert=True)
            return

        msg = await recall_service.generate_recall_message(contacts, bio=bio, focus=focus)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Другой вариант", callback_data="recall_reroll")
        
        await callback.message.answer(msg, reply_markup=builder.as_markup())
        await callback.answer()

@router.message(Command("delete_me"))
async def cmd_delete_me(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Да, удалить всё", callback_data="confirm_delete_me")
    builder.button(text="Отмена", callback_data="cancel_delete")
    
    await message.answer(
        "⚠ <b>Вы уверены?</b>\n\n"
        "Это удалит ВСЕ ваши контакты и историю безвозвратно.",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "confirm_delete_me")
async def on_delete_confirm(callback: types.CallbackQuery):
    await user_service.delete_user_full(callback.from_user.id)
    await callback.message.edit_text("🗑 Все ваши данные удалены. Нажмите /start для новой регистрации.")
    await callback.answer()

@router.callback_query(F.data == "cancel_delete")
async def on_delete_cancel(callback: types.CallbackQuery):
    await callback.message.delete()
