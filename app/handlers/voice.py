import os
from aiogram import Router, types, F
from loguru import logger

from app.services.audio_service import AudioService
from app.services.ai_service import ai_service
from app.services.search_service import search_service
from app.schemas import ContactCreate

router = Router()

@router.message(F.voice)
async def handle_voice(message: types.Message):
    """
    Основной пайплайн обработки голосовых сообщений.
    """
    user_id = message.from_user.id
    status_msg = await message.answer("🎧 Слушаю...")
    
    # Временные файлы
    ogg_path = f"voice_{user_id}_{message.message_id}.ogg"
    mp3_path = None
    
    try:
        # 1. Скачивание файла
        bot = message.bot
        file_info = await bot.get_file(message.voice.file_id)
        await bot.download_file(file_info.file_path, ogg_path)
        
        # 2. Конвертация (OGG -> MP3)
        await status_msg.edit_text("🔄 Обрабатываю аудио...")
        mp3_path = AudioService.convert_ogg_to_mp3(ogg_path)
        
        # 3. Транскрибация (STT)
        transcribed_text = await ai_service.transcribe_audio(mp3_path)
        
        if not transcribed_text:
            await status_msg.edit_text("🤔 Не удалось разобрать слова.")
            return

        # 4. Анализ и Экстракция (LLM)
        await status_msg.edit_text("🧠 Анализирую...")
        extracted_data = await ai_service.extract_contact_info(transcribed_text)
        
        # 5. Векторизация
        full_text_for_embedding = f"{extracted_data.name} {extracted_data.summary} {extracted_data.meta}"
        embedding = await ai_service.get_embedding(full_text_for_embedding)
        
        # 6. Сохранение в БД
        contact_create = ContactCreate(
            user_id=user_id,
            name=extracted_data.name,
            summary=extracted_data.summary,
            raw_text=transcribed_text,
            meta=extracted_data.meta.model_dump(),
            embedding=embedding
        )
        
        contact = await search_service.create_contact(contact_create)
        
        # 7. Финальный ответ
        response_text = (
            f"✅ <b>Записал:</b> {extracted_data.name}\n\n"
            f"📝 {extracted_data.summary}\n\n"
            f"<i>\"{transcribed_text}\"</i>"
        )
        
        # Удаляем сообщение о статусе и отправляем результат
        await status_msg.delete()
        await message.reply(response_text)
        
    except Exception as e:
        logger.error(f"Voice pipeline error: {e}")
        await status_msg.edit_text("❌ Ошибка при обработке. Попробуйте позже.")
    finally:
        # Чистка временных файлов
        AudioService.cleanup_file(ogg_path)
        if mp3_path:
            AudioService.cleanup_file(mp3_path)

