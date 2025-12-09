from aiogram import Router, F, types
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, ContentType
from aiogram.filters import Command
from loguru import logger

from app.services.user_service import user_service
from app.config import settings

router = Router()

# --- Payment Handlers ---

@router.message(Command("buy_pro"))
@router.message(F.text == "💎 Купить Pro")
async def buy_pro(message: Message):
    """
    Отправляет инвойс на оплату Pro-подписки (Telegram Stars).
    """
    await message.answer_invoice(
        title="NetWho Pro (1 Month)",
        description="Безлимитные контакты, Умный Recall и чтение новостей.",
        payload="netwho_pro_month",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label="Pro Month", amount=100)], # 100 Stars
        provider_token="" # Empty for Stars
    )

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """
    Подтверждение готовности принять оплату.
    """
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def success_payment(message: Message):
    """
    Обработка успешной оплаты.
    """
    payment_info = message.successful_payment
    
    # Можно добавить проверку payload, если будут разные товары
    # if payment_info.invoice_payload == "netwho_pro_month": ...
    
    # Обновляем подписку на 30 дней
    await user_service.update_subscription(message.from_user.id, days=30)
    
    logger.info(f"User {message.from_user.id} bought Pro! Payload: {payment_info.invoice_payload}")
    
    await message.answer(
        "🎉 <b>Поздравляем! Ты теперь Pro.</b>\n\n"
        "Лимиты сняты. Магия включена на полную.\n"
        "Попробуй добавить всех своих друзей!",
        message_effect_id="5104841245755180586" # Festive effect (optional, check if valid id or remove)
    )

# --- Admin Handlers ---

@router.message(Command("give_pro"))
async def give_pro_command(message: Message):
    """
    Выдача Pro пользователю (Admin only).
    Usage: /give_pro <user_id> <days>
    """
    if message.from_user.id != settings.ADMIN_ID:
        return

    try:
        args = message.text.split()
        if len(args) < 3:
            # Escape symbols to avoid HTML parse error
            await message.answer("Usage: /give_pro &lt;user_id&gt; &lt;days&gt;")
            return

        target_user_id = int(args[1])
        days = int(args[2])

        success = await user_service.update_subscription(target_user_id, days)
        
        if success:
            await message.answer(f"✅ Выдал Pro юзеру {target_user_id} на {days} дней.")
            
            # Попытаться уведомить пользователя (может не сработать, если нет чата)
            try:
                await message.bot.send_message(
                    target_user_id,
                    f"🎁 <b>Вам подарена Pro-подписка на {days} дней!</b>\nНаслаждайтесь безлимитом."
                )
            except:
                pass
        else:
            await message.answer("❌ Ошибка при обновлении (пользователь не найден?).")
            
    except ValueError:
        await message.answer("ID и дни должны быть числами.")
    except Exception as e:
        logger.error(f"Error giving pro: {e}")
        await message.answer(f"Error: {e}")

