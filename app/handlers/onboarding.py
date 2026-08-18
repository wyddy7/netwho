import os
from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from loguru import logger

from app.config import settings
from app.utils.chat_action import KeepTyping
from app.states import OnboardingStates
from app.services.user_service import user_service
from app.services.ai_service import ai_service
from app.services.audio_service import AudioService
from app.services.search_service import search_service
from app.services.recall_service import recall_service
from app.schemas import UserCreate, ContactCreate, RecallSettings

router = Router()

async def process_voice_input(message: types.Message) -> str:
    """Helper to process voice input and return text"""
    user_id = message.from_user.id
    status_msg = await message.answer("🎧 Слушаю...")
    
    os.makedirs("temp_voice", exist_ok=True)
    ogg_path = os.path.join("temp_voice", f"voice_{user_id}_{message.message_id}.ogg")
    mp3_path = None
    
    try:
        bot = message.bot
        file_info = await bot.get_file(message.voice.file_id)
        await bot.download_file(file_info.file_path, ogg_path)
        
        mp3_path = AudioService.convert_ogg_to_mp3(ogg_path)
        text = await ai_service.transcribe_audio(mp3_path)
        
        await status_msg.delete()
        if text:
             await message.answer(f"🗣 <i>\"{text}\"</i>")
        return text
    except Exception:
        logger.exception("Voice error")
        await status_msg.edit_text("❌ Ошибка обработки голоса.")
        return ""
    finally:
        AudioService.cleanup_file(ogg_path)
        if mp3_path:
            AudioService.cleanup_file(mp3_path)

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user = message.from_user
    if not user:
        return

    logger.info(f"User {user.id} started bot (Onboarding)")
    
    # 1. Parse Deep Link (Story 21)
    # Format: /start join_UUID
    org_join_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("join_"):
        org_join_id = args[1].replace("join_", "")
        logger.info(f"User {user.id} attempting to join org via deep link: {org_join_id}")

    # Register/Update user
    try:
        # Check if user exists BEFORE upsert
        existing_user = await user_service.get_user(user.id)
        
        user_data = UserCreate(
            id=user.id,
            username=user.username,
            full_name=user.full_name
        )
        await user_service.upsert_user(user_data)
        
        # Grant Trial for NEW users
        if not existing_user:
            await user_service.grant_trial(user.id, settings.TRIAL_DAYS)
            logger.info(f"Granted {settings.TRIAL_DAYS}-day trial to new user {user.id}")
            # Explicit refresh
            existing_user = await user_service.get_user(user.id)
        
        # 2. Process Join Org (Story 21)
        if org_join_id:
            join_res = await user_service.join_org(user.id, org_join_id)
            if join_res["status"] == "joined":
                await message.answer(
                    f"Добро пожаловать в <b>{join_res['org_name']}</b>! 🎉\n\n"
                    "Твоя заявка на участие отправлена. Администратор скоро подтвердит доступ.\n"
                    f"Пока ты можешь использовать {settings.FREE_NEWS_JACKS_LIMIT} демо-поиска."
                )
            elif join_res["status"] == "already_member":
                await message.answer(f"Ты уже участник организации <b>{join_res['org_name']}</b>.")
            elif join_res["status"] == "not_found":
                await message.answer("⚠ Организация по ссылке не найдена.")

        # Check if already onboarded (if bio exists)
        if existing_user and existing_user.bio:
            await message.answer(
                f"С возвращением, {user.full_name}! 👋\n"
                "Я готов работать. Просто пиши или отправляй голосовые."
            )
            return
            
    except Exception:
        logger.exception("Registration error")
        await message.answer("⚠ Ошибка старта.")
        return

    # Start Onboarding
    
    # Determine subscription status message
    sub_text = ""
    is_pro = await user_service.is_pro(user.id)
    
    if not existing_user:
        sub_text = f"🎁 <b>Тебе доступен Pro-режим на {settings.TRIAL_DAYS} дня (тест-драйв).</b>"
    else:
        # Check if actually Pro (could be old pro, or expired)
        if is_pro:
            sub_text = "✨ <b>Твой Pro-режим активен.</b>"
        else:
            sub_text = "📉 <b>Ты сейчас на Free-тарифе.</b>"

    text = (
        f"Йо, {user.full_name}! Я <b>NetWho</b>. 👋\n\n"
        "Я твоя вторая память: помогаю не проебать важные знакомства "
        "и сам нахожу поводы написать людям.\n\n"
        f"{sub_text}\n\n"
        "Давай настроимся за 30 секунд?"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Погнали 🚀", callback_data="start_onboarding")
    
    await message.answer(text, reply_markup=builder.as_markup())
    await state.clear()

@router.callback_query(F.data == "start_onboarding")
async def start_onboarding_flow(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Кнопки-подсказки (Reply Keyboard для удобства)
    builder = ReplyKeyboardBuilder()
    builder.button(text="👨‍💻 Основатель стартапа")
    builder.button(text="💰 Инвестор")
    builder.button(text="🎤 Нетворкер")
    builder.button(text="🛠 Разработчик")
    builder.adjust(2)

    await callback.message.edit_reply_markup(reply_markup=None) # remove inline button
    await callback.message.answer(
        "<b>Шаг 1 из 2: Кто ты?</b>\n\n"
        "Напиши пару слов о себе и кого ищешь.\n"
        "<i>(Например: 'Я продакт, ищу инвестиции' или выбери вариант ниже)</i>",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
    )
    
    await state.set_state(OnboardingStates.waiting_for_bio)

@router.message(OnboardingStates.waiting_for_bio)
async def process_bio_step(message: types.Message, state: FSMContext):
    # Проверка состояния (дополнительная защита)
    current_state = await state.get_state()
    if current_state != OnboardingStates.waiting_for_bio:
        await message.answer("⚠️ Обнаружен сброс состояния. Начните заново: /start")
        await state.clear()
        return
    
    text = message.text
    if message.voice:
        text = await process_voice_input(message)
    
    if not text:
        await message.answer("Я не понял. Напиши текстом или скажи голосом.")
        return

    await message.answer("⏳ Анализирую...", reply_markup=types.ReplyKeyboardRemove())
    
    # Extract clean bio
    clean_bio = await ai_service.extract_user_bio(text)
    
    # Save to DB
    await user_service.update_bio(message.from_user.id, clean_bio)
    
    await message.answer(
        f"✅ Принято.\n\n"
        f"<i>{clean_bio}</i>\n\n"
        "<b>Шаг 2 из 2: Магия ✨</b>\n"
        "Вспомни <b>одного</b> полезного человека, с которым ты давно не общался.\n\n"
        "Просто запиши голосовое (или текст):\n"
        "1. Кто он?\n"
        "2. Откуда знаете друг друга?\n"
        "3. Чем он крут?"
    )
    
    await state.set_state(OnboardingStates.waiting_for_first_contact)

@router.message(OnboardingStates.waiting_for_first_contact)
async def process_first_contact_step(message: types.Message, state: FSMContext):
    # Проверка состояния (дополнительная защита)
    current_state = await state.get_state()
    if current_state != OnboardingStates.waiting_for_first_contact:
        await message.answer("⚠️ Обнаружен сброс состояния. Начните заново: /start")
        await state.clear()
        return
    
    user_id = message.from_user.id
    text = message.text
    if message.voice:
        text = await process_voice_input(message)
        
    if not text:
        await message.answer("Нужен текст или голосовое о контакте.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # 1. Extract Contact
    try:
        extracted = await ai_service.extract_contact_info(text)
        
        # Check if it's a command/ignore
        if extracted.action == "ignore":
            await message.answer(
                "🤔 <b>Это похоже на команду, а не на контакт.</b>\n\n"
                "Мы сейчас в режиме настройки. Просто напиши <i>описание человека</i>.\n"
                "Например: <i>'Олег, дизайнер, делает сайты'</i>.\n\n"
                "Попробуй еще раз:"
            )
            return

        # 2. Save Contact (Force New)
        full_text = f"{extracted.name} {extracted.summary} {extracted.meta}"
        embedding = await ai_service.get_embedding(full_text)
        
        contact_create = ContactCreate(
            user_id=user_id,
            name=extracted.name,
            summary=extracted.summary,
            raw_text=text,
            meta=extracted.meta.model_dump(),
            embedding=embedding
        )
        
        created_contact = await search_service.create_contact(contact_create)
        
        await message.answer(f"💾 Записал: <b>{created_contact.name}</b>")
        
        # 3. MAGIC MOMENT: Generate Recall
        async with KeepTyping(message.bot, message.chat.id):
            # Explicit refresh: перечитываем пользователя из БД после обновления подписки
            # чтобы получить актуальный статус (fix cache invalidation problem)
            user = await user_service.get_user(user_id)
            
            # Генерируем сообщение именно для ЭТОГО контакта
            recall_msg = await recall_service.generate_recall_message(
                [created_contact.model_dump()], # Передаем как dict, а не Pydantic model
                bio=user.bio, 
                focus="Восстановление связи (Onboarding)"
            )
        
        # ОТПРАВЛЯЕМ ВСЁ В ОДНОМ СООБЩЕНИИ, ЧТОБЫ ИЗБЕЖАТЬ СПАМА И ДУБЛЕЙ
        
        final_text = (
            f"🔥 <b>Магия:</b>\n"
            "Я нашел идеальный повод написать ему прямо сейчас.\n\n"
            f"{recall_msg}\n\n"
            "🎉 <b>Настройка завершена!</b>\n"
            "Теперь просто скидывай мне всё подряд — контакты, мысли, ссылки.\n"
            "Я сам буду напоминать о важных людях (раз в неделю).\n\n"
            "👇 Меню управления:"
        )

        # Final Onboarding Message with Buttons
        builder = InlineKeyboardBuilder()
        builder.button(text="⚙️ Настройки", callback_data="open_settings")
        builder.button(text="🎲 Вспомнить кого-то", callback_data="recall_manual")
        builder.adjust(2) # 2 кнопки в ряду

        await message.answer(final_text, reply_markup=builder.as_markup())
        
        await state.clear()
        
    except Exception:
        logger.exception("Onboarding contact error")
        await message.answer("⚠ Что-то пошло не так. Но мы почти закончили. Попробуй /start еще раз.")
        await state.clear()
