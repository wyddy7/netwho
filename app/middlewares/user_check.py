from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message
from loguru import logger
from app.services.user_service import user_service
from app.schemas import UserCreate
from app.config import settings

class UserCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Only check for Messages with a user
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
            
        # Skip for /start command (handled by onboarding)
        if event.text and event.text.startswith("/start"):
            return await handler(event, data)
            
        user = event.from_user
        
        # Check if user exists in DB
        db_user = await user_service.get_user(user.id)
        
        if not db_user:
            logger.warning(f"User {user.id} not found in DB (interaction without /start). Resurrecting...")
            
            # Resurrect (Create user)
            user_data = UserCreate(
                id=user.id,
                username=user.username,
                full_name=user.full_name
            )
            await user_service.upsert_user(user_data)
            
            # Immediately grant trial here to avoid double messaging via LegacyTrialMiddleware
            await user_service.grant_trial(user.id, settings.TRIAL_DAYS)
            
            # Send Unified Welcome Back message
            try:
                await event.answer(
                    "👋 <b>С возвращением, Бро!</b>\n\n"
                    "Вижу, ты удалялся, но я тебя помню (ладно, профиль создал заново).\n\n"
                    "🎁 <b>Кстати, подгон:</b>\n"
                    f"Выдал тебе <b>{settings.TRIAL_DAYS} дня Pro</b> за счет заведения. Теперь я умею читать твои ссылки и давать умные советы.\n\n"
                    "👇 Давай сразу к делу: <b>напиши, кто ты сейчас и кого ищем?</b>\n"
                    "<i>(Или нажми /start, если хочешь по классике)</i>"
                )
            except Exception as e:
                logger.error(f"Failed to send welcome back message: {e}")
                
            # We updated the user and sent the message. 
            # We should continue to handler? 
            # If user sent "hi", handler will try to process "hi". 
            # Since user is resurrected, handler will work.
            # But "hi" might trigger AI agent which says "Hello". 
            # That's acceptable as a follow-up. 
            
        return await handler(event, data)
