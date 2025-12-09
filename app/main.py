import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.config import settings
from app.handlers import base, voice, text, settings as settings_handler, profile, onboarding
from app.services.user_service import user_service
from app.services.recall_service import recall_service

# Твой ID для уведомлений (можно вынести в .env, но пока так)
ADMIN_ID = 6108932752

async def on_startup(bot: Bot):
    logger.info("Bot started! Polling...")
    try:
        # Уведомляем админа
        await bot.send_message(
            ADMIN_ID, 
            "🔄 <b>Бот был перезапущен.</b>\nИстория диалога сброшена (в памяти агента).",
            parse_mode="HTML"
        )
        # Очищаем историю чата для админа в БД, чтобы начать с чистого листа
        # (Это жесткий сброс, но для тестов идеально)
        await user_service.clear_history(ADMIN_ID)
        logger.info(f"History cleared for user {ADMIN_ID}")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")

async def main():
    logger.info("Starting NetWho Bot...")
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher()
    
    # Регистрация роутеров (Порядок важен!)
    dp.include_router(onboarding.router) # Onboarding (Start + States) - First priority
    dp.include_router(base.router)
    dp.include_router(settings_handler.router)
    dp.include_router(profile.router)
    dp.include_router(voice.router)
    
    from app.handlers import payments
    dp.include_router(payments.router)
    
    dp.include_router(text.router) # Text handler (Generic) - Last priority
    
    # Хук на старт
    dp.startup.register(on_startup)
    
    # Scheduler Setup
    scheduler = AsyncIOScheduler()
    # Запускаем каждую минуту, чтобы попадать в пользовательские таймслоты
    scheduler.add_job(recall_service.process_recalls, "cron", minute='*', args=[bot])
    
    scheduler.start()
    logger.info("Scheduler started")
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
