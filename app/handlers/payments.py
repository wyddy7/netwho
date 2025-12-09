from aiogram import Router, F, types
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, ContentType
from aiogram.filters import Command
from loguru import logger

from app.services.user_service import user_service
from app.services.subscription_service import run_amnesty_logic
from app.config import settings

router = Router()

# --- Payment Handlers ---

@router.callback_query(F.data == "buy_pro_callback")
async def buy_pro_callback(callback: types.CallbackQuery):
    """
    Callback wrapper for buying pro.
    """
    await buy_pro(callback.message)
    await callback.answer()

@router.message(Command("buy_pro"))
@router.message(F.text == "💎 Купить Pro")
async def buy_pro(message: Message):
    """
    Отправляет инвойс на оплату Pro-подписки (Telegram Stars).
    """
    # 1. Marketing Message (Sandwich method)
    await message.answer(
        f"🚀 <b>Early Bird Offer</b>\n\n"
        f"<s>{settings.PRICE_ANCHOR_STARS} ⭐️</s> → <b>{settings.PRICE_MONTH_STARS} ⭐️</b>\n"
        "<i>(Цена для первых пользователей до релиза v1.0)</i>"
    )

    # 2. Invoice
    await message.answer_invoice(
        title="NetWho Pro (1 Month)",
        description=(
            "Безлимитные контакты, Умный Recall и чтение новостей.\n"
            "Инвестиция в твой социальный капитал."
        ),
        payload="netwho_pro_month",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label="Pro Month (Early Bird)", amount=settings.PRICE_MONTH_STARS)], 
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

@router.message(Command("revoke_pro"))
async def revoke_pro_command(message: Message):
    """
    Забрать Pro у пользователя (Admin only).
    Usage: /revoke_pro <user_id>
    """
    if message.from_user.id != settings.ADMIN_ID:
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Usage: /revoke_pro &lt;user_id&gt;")
            return

        target_user_id = int(args[1])
        
        # Use service method to clear BOTH pro_until and trial_ends_at
        success = await user_service.revoke_subscription(target_user_id)
        
        if success:
            await message.answer(f"✅ Pro подписка (и Trial) отозвана у юзера {target_user_id}.")
        else:
            await message.answer("❌ Ошибка при обновлении (пользователь не найден?).")
            
    except ValueError:
        await message.answer("ID должен быть числом.")
    except Exception as e:
        logger.error(f"Error revoking pro: {e}")
        await message.answer(f"Error: {e}")

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

@router.message(Command("broadcast_amnesty"))
async def broadcast_amnesty_command(message: Message):
    """
    Рассылка амнистии (триал 3 дня) всем пользователям.
    Admin only.
    """
    if message.from_user.id != settings.ADMIN_ID:
        return
        
    await message.answer("🚀 Запускаю процесс амнистии (рассылка всем)...")
    
    # Run in background to not block handler? 
    # Or just await it since it is admin command.
    # Logic inside logic function processes all users.
    try:
        await run_amnesty_logic(message.bot)
        await message.answer("✅ Амнистия завершена.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


