import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.config import settings
from app.handlers import base, voice, text, settings as settings_handler

async def main():
    logger.info("Starting NetWho Bot...")
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher()
    
    # Регистрация роутеров
    dp.include_router(base.router)
    dp.include_router(settings_handler.router) # Добавили настройки
    dp.include_router(voice.router)
    dp.include_router(text.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("Bot started! Polling...")
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
