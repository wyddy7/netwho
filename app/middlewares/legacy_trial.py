from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, Update
from loguru import logger

from app.services.user_service import user_service

class LegacyTrialMiddleware(BaseMiddleware):
    """
    Middleware that checks if an existing user (who has no pro_until date set)
    interacts with the bot. If so, it grants them a 3-day trial as a "Legacy Gift".
    """

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        # Поскольку мы регистрируем middleware через dp.message.middleware, 
        # event - это уже Message, а не Update.
        
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
            
        user_id = event.from_user.id
        
        # We need to be careful not to spam DB calls on every message.
        # But for this specific migration logic, we check user status.
        # To optimize, we could check a local cache, but Supabase is fast enough for MVP.
        
        # Check user in DB
        # Note: We rely on user_service.get_user returning None if not found, 
        # but middleware runs BEFORE onboarding handlers might create the user.
        # So this logic applies only if user ALREADY exists.
        
        try:
            user = await user_service.get_user(user_id)
            
            # If user exists AND has never had pro status set (pro_until is None)
            # This identifies "Old users" who were created before the migration.
            # New users created via Onboarding will have pro_until set immediately.
            # Users resurrected via UserCheckMiddleware will also have pro_until set immediately.
            if user and user.pro_until is None:
                logger.info(f"Legacy User {user_id} detected without Pro status. Granting Trial.")
                
                # Grant 3 days
                await user_service.update_subscription(user_id, 3)
                
                # Notify User
                try:
                    await event.bot.send_message(
                        user_id,
                        "🎁 <b>Подарок за верность!</b>\n\n"
                        "Мы обновили NetWho и добавили Pro-режим.\n"
                        "Как раннему пользователю, тебе начислено <b>3 дня Pro</b> бесплатно.\n\n"
                        "Тестируй новые фишки: безлимит контактов и умный Recall!"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send trial notification: {e}")
                    
        except Exception as e:
            # Don't block the main flow if this fails
            logger.error(f"Legacy middleware error: {e}")
            
        return await handler(event, data)
