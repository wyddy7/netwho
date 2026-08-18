import os
from aiogram import Router, types, F
from loguru import logger

from app.services.audio_service import AudioService
from app.services.ai_service import ai_service
from app.handlers.text import handle_agent_response
from app.services.user_service import user_service
from app.utils.chat_action import KeepTyping
from app.config import settings

router = Router()

@router.message(F.voice)
async def handle_voice(message: types.Message):
    """
    Унифицированный обработчик голосовых.
    Voice -> STT -> Router Agent -> Action
    """
    user_id = message.from_user.id

    # --- Limit Check ---
    is_pro = await user_service.is_pro(user_id)
    duration = message.voice.duration
    if not is_pro and duration > 30:
        await message.reply(
            f"⏳ <b>Голосовое слишком длинное (лимит 30 сек).</b>\n\n"
            "В Pro-версии можно записывать целые лекции.\n"
            f"Нажми /buy_pro ({settings.PRICE_MONTH_STARS} ⭐️)."
        )
        return
    # -------------------

    status_msg = await message.answer("🎧 Слушаю...")
    
    # Создаем папку если нет (локально)
    os.makedirs("temp_voice", exist_ok=True)
    
    ogg_path = os.path.join("temp_voice", f"voice_{user_id}_{message.message_id}.ogg")
    mp3_path = None
    
    try:
        # 1. Скачивание
        bot = message.bot
        file_info = await bot.get_file(message.voice.file_id)
        await bot.download_file(file_info.file_path, ogg_path)
        
        # 2. Конвертация
        mp3_path = AudioService.convert_ogg_to_mp3(ogg_path)
        
        # 3. Транскрибация (STT)
        transcribed_text = await ai_service.transcribe_audio(mp3_path)
        
        if not transcribed_text:
            await status_msg.edit_text("🤔 Тишина...")
            return

        # Показываем юзеру, что мы услышали (и удаляем "Слушаю...")
        await status_msg.edit_text(f"🗣 <i>\"{transcribed_text}\"</i>")
        
        # 4. Отправляем текст в Единый Мозг (Router Agent)
        async with KeepTyping(message.bot, message.chat.id):
            response = await ai_service.run_router_agent(transcribed_text, user_id)
            
            # 5. Обрабатываем ответ агента (через общую функцию из text.py)
            await handle_agent_response(message, response)
        
    except Exception:
        logger.exception("Voice pipeline error")
        await status_msg.edit_text("❌ Ошибка обработки.")
    finally:
        AudioService.cleanup_file(ogg_path)
        if mp3_path:
            AudioService.cleanup_file(mp3_path)
