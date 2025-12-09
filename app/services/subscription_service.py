from app.services.user_service import user_service
from app.services.search_service import search_service

FREE_CONTACTS_LIMIT = 10

async def check_limits(user_id: int) -> bool:
    """
    Check if user can add more contacts.
    Returns True if allowed, False if limit reached.
    """
    is_pro = await user_service.is_pro(user_id)
    if is_pro:
        return True
    
    count = await search_service.count_contacts(user_id)
    return count < FREE_CONTACTS_LIMIT

async def get_limit_message(user_id: int) -> str:
    """
    Return message explaining limits.
    """
    return (
        f"🚧 <b>Ого, ты записал уже {FREE_CONTACTS_LIMIT} человек!</b>\n\n"
        "Твоя сеть растет. Чтобы записать 11-го и получить безлимит, нужна Pro-подписка (всего 100 ⭐️).\n\n"
        "Нажми /buy_pro или кнопку ниже."
    )

