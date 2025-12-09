from aiogram import Router, F, types
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, ContentType
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from app.services.user_service import user_service
from app.services.subscription_service import run_amnesty_logic
from app.config import settings

router = Router()

# --- Payment Handlers ---

@router.message(Command("buy_pro"))
@router.message(F.text == "💎 Купить Pro")
@router.callback_query(F.data == "buy_pro_callback")
async def show_pro_offer(event: Message | types.CallbackQuery):
    """
    Показывает сравнение тарифов перед оплатой.
    """
    message = event.message if isinstance(event, types.CallbackQuery) else event
    
    text = (
        "💎 <b>NetWho Pro: Что ты получаешь?</b>\n\n"
        "<b>Free Plan:</b>\n"
        "• Только 15 контактов\n"
        "• Голосовые по 30 секунд\n"
        "• 3 анализа ссылок для твоего нетворка (всего)\n"
        "• Короткая память (3 сообщения)\n"
        "• 1 Recall в неделю\n"
        "• Ручной Recall: 1 раз в сутки\n\n"
        "<b>🚀 Pro Plan (250 ⭐️):</b>\n"
        "• Recall каждый день\n"
        "• Безлимит на ссылки\n"
        "• Глубокая память (10+ сообщений)\n"
        "• Безлимитный ручной Recall\n"
        "• Голосовые без ограничений\n\n"
        f"<i>Цена для ранних пташек: {settings.PRICE_MONTH_STARS} вместо {settings.PRICE_ANCHOR_STARS} ⭐️.</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🚀 Оформить за {settings.PRICE_MONTH_STARS} ⭐️", callback_data="proceed_to_payment")
    builder.adjust(1)
    
    if isinstance(event, types.CallbackQuery):
        # Если вызвано из меню, обновляем сообщение (или шлем новое, если старое было текстовым?)
        # Лучше слать новое, чтобы старое меню осталось? Или редактировать?
        # Обычно оффер лучше слать новым сообщением, так как там много текста.
        await message.answer(text, reply_markup=builder.as_markup())
        await event.answer()
    else:
        await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "proceed_to_payment")
async def send_invoice(callback: types.CallbackQuery):
    """
    Отправляет инвойс после подтверждения.
    """
    description = (
        "Безлимитные контакты, Умный Recall каждый день, Чтение новостей. "
        "Цена для первых пользователей."
    )
    
    await callback.message.answer_invoice(
        title="Early Bird Pro (1 Month)",
        description=description,
        payload="netwho_pro_month",
        currency="XTR",
        prices=[LabeledPrice(label="Pro Month", amount=settings.PRICE_MONTH_STARS)], 
        provider_token="" # Empty for Stars
    )
    await callback.answer()

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


