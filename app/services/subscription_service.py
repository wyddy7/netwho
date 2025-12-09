import asyncio
from datetime import datetime, timedelta, timezone
from loguru import logger
from aiogram import Bot

from app.services.user_service import user_service
from app.services.search_service import search_service
from app.infrastructure.supabase.client import get_supabase
from app.config import settings

async def check_limits(user_id: int) -> bool:
    """
    Check if user can add more contacts.
    Returns True if allowed, False if limit reached.
    """
    is_pro = await user_service.is_pro(user_id)
    if is_pro:
        return True
    
    count = await search_service.count_contacts(user_id)
    return count < settings.FREE_CONTACTS_LIMIT

async def get_limit_message(user_id: int) -> str:
    """
    Return message explaining limits.
    """
    return (
        f"🚧 <b>Ого, ты записал уже {settings.FREE_CONTACTS_LIMIT} человек!</b>\n\n"
        f"Твоя сеть растет. Чтобы записать 11-го и получить безлимит, нужна Pro-подписка (всего {settings.PRICE_MONTH_STARS} ⭐️).\n\n"
        "Нажми /buy_pro или кнопку ниже."
    )

async def run_amnesty_logic(bot: Bot):
    """
    Grants trial to all existing Free users and notifies them.
    """
    logger.info("Starting Amnesty Broadcast...")
    
    supabase = get_supabase()
    
    try:
        # 1. Get all users
        response = supabase.table("users").select("*").execute()
        users = response.data
        
        if not users:
            logger.info("No users found.")
            return

        logger.info(f"Found {len(users)} users. Processing...")
        
        updated_count = 0
        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=settings.TRIAL_DAYS)
        
        for user in users:
            user_id = user['id']
            pro_until_str = user.get('pro_until')
            
            # Check if already Pro
            is_pro = False
            if pro_until_str:
                pro_until = datetime.fromisoformat(pro_until_str)
                if pro_until > now:
                    is_pro = True
            
            if is_pro:
                logger.debug(f"User {user_id} is already Pro. Skipping.")
                continue
                
            # Grant Trial
            try:
                # We can use user_service.grant_trial logic here or direct update
                supabase.table("users").update({
                    "trial_ends_at": trial_end.isoformat()
                }).eq("id", user_id).execute()
                
                updated_count += 1
                
                # Send Message
                msg_text = (
                    "🎉 <b>Global Update: Freemium 2.0</b>\n\n"
                    "Мы обновили NetWho! Теперь бот работает еще круче.\n"
                    "В честь обновления я выдал тебе <b>3 дня Pro-режима бесплатно</b>.\n\n"
                    "Что нового:\n"
                    "1. <b>News Jacking</b>: кидай ссылки, я найду кому они полезны.\n"
                    "2. <b>Smart Recall</b>: теперь напоминания еще умнее.\n"
                    "3. <b>Unlimited Voice</b>: в Pro можно болтать хоть часами.\n\n"
                    "Тестируй прямо сейчас! 👇"
                )
                
                try:
                    await bot.send_message(chat_id=user_id, text=msg_text)
                    logger.info(f"Updated and notified user {user_id}")
                except Exception as e:
                    logger.warning(f"Updated user {user_id} but failed to send message: {e}")
                    
                await asyncio.sleep(0.1) # Throttling
                
            except Exception as e:
                logger.error(f"Failed to process user {user_id}: {e}")
                
        logger.info(f"Amnesty finished. Updated {updated_count} users.")
        
    except Exception as e:
        logger.error(f"Global error: {e}")
