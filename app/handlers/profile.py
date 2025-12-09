from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.user_service import user_service

router = Router()

class ProfileStates(StatesGroup):
    waiting_for_bio = State()

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """
    Показать профиль пользователя.
    """
    user_id = message.from_user.id
    user = await user_service.get_user(user_id)
    
    if not user:
        # Если юзера нет в базе (странно, но бывает), создаем пустышку или ругаемся
        await message.answer("Странно, я вас не знаю. Нажмите /start.")
        return

    bio = user.bio if user.bio else "<i>Не задано</i>"
    
    text = (
        f"👤 <b>Твой Профиль</b>\n\n"
        f"💼 <b>О себе (Bio):</b>\n{bio}\n\n"
        f"<i>Это описание используется агентом, чтобы давать более точные советы. "
        f"Напиши сюда, кто ты, чем занимаешься и кого ищешь.</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Изменить Bio", callback_data="edit_bio")
    builder.button(text="❌ Закрыть", callback_data="close_profile")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "edit_bio")
async def on_edit_bio(callback: types.CallbackQuery, state: FSMContext):
    """
    Начало редактирования Bio.
    """
    await callback.message.edit_text(
        "📝 <b>Расскажи о себе</b>\n\n"
        "Напиши мне, кто ты, какие у тебя цели и кого ты ищешь.\n"
        "Например: <i>'Я продакт-менеджер в EdTech. Ищу инвесторов для своего стартапа и крутых разработчиков.'</i>\n\n"
        "👇 <b>Напиши текст и отправь его:</b>",
        reply_markup=None
    )
    await state.set_state(ProfileStates.waiting_for_bio)
    await callback.answer()

@router.message(ProfileStates.waiting_for_bio)
async def on_bio_entered(message: types.Message, state: FSMContext):
    """
    Сохранение Bio.
    """
    user_id = message.from_user.id
    new_bio = message.text
    
    await user_service.update_bio(user_id, new_bio)
    await state.clear()
    
    await message.answer(
        f"✅ <b>Профиль обновлен!</b>\n\n"
        f"💼 <b>О себе:</b>\n{new_bio}\n\n"
        "Теперь советы Recall будут учитывать этот контекст."
    )

@router.callback_query(F.data == "close_profile")
async def on_close_profile(callback: types.CallbackQuery):
    await callback.message.delete()

