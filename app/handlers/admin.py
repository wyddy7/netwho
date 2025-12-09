from aiogram import Router, types
from aiogram.filters import Command
from loguru import logger
from app.services.user_service import user_service
from app.config import settings

router = Router()

def is_admin(user_id: int) -> bool:
    # Check if user_id matches the configured ADMIN_ID
    # For now, we support single admin ID from config. 
    # Can be extended to list if needed.
    return user_id == settings.ADMIN_ID

@router.message(Command("admin"))
async def cmd_admin_help(message: types.Message):
    if not is_admin(message.from_user.id):
        return # Silent ignore for non-admins
        
    text = (
        "👮‍♂️ <b>Admin Panel</b>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/give_pro &lt;user_id&gt; &lt;days&gt;</code> - Give Pro subscription\n"
        "• <code>/revoke_pro &lt;user_id&gt;</code> - Remove Pro subscription\n"
        "• <code>/check_user &lt;user_id&gt;</code> - Check user info\n"
    )
    await message.answer(text)

@router.message(Command("give_pro"))
async def cmd_give_pro(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            await message.reply("Usage: /give_pro <user_id> <days>")
            return
            
        target_id = int(args[1])
        days = int(args[2])
        
        success = await user_service.update_subscription(target_id, days)
        if success:
            await message.reply(f"✅ Granted {days} days of Pro to user {target_id}.")
            try:
                await message.bot.send_message(
                    target_id,
                    f"🎁 <b>Вам начислена Pro-подписка на {days} дн.</b>\n"
                    "Администратор выдал вам доступ."
                )
            except Exception as e:
                await message.reply(f"⚠️ Failed to notify user: {e}")
        else:
            await message.reply("❌ Failed to update subscription. User not found?")
            
    except ValueError:
        await message.reply("❌ Invalid format. Use numbers.")
    except Exception as e:
        logger.error(f"Give pro error: {e}")
        await message.reply(f"❌ Error: {e}")

@router.message(Command("revoke_pro"))
async def cmd_revoke_pro(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply("Usage: /revoke_pro <user_id>")
            return
            
        target_id = int(args[1])
        
        # Set subscription to 0 days (effectively expire)
        # Or better: set pro_until to past.
        # Reuse update_subscription with negative days? 
        # No, update_subscription logic is: current + days OR now + days.
        # If we pass negative days to 'now + days', it works.
        
        # Hack: Pass -1 days.
        # Wait, if user has active sub till 2025, adding -1 day just reduces it.
        # We want to KILL it.
        
        # Let's implement force expire in user_service or just direct update here?
        # Direct update is cleaner for admin tool.
        
        from datetime import datetime
        
        # Set to yesterday
        await user_service.update_user_field(target_id, "pro_until", datetime(2000, 1, 1).isoformat())
        
        await message.reply(f"✅ Pro subscription revoked for user {target_id}.")
            
    except ValueError:
        await message.reply("❌ Invalid format. Use numbers.")
    except Exception as e:
        logger.error(f"Revoke pro error: {e}")
        await message.reply(f"❌ Error: {e}")

@router.message(Command("check_user"))
async def cmd_check_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply("Usage: /check_user <user_id>")
            return
            
        target_id = int(args[1])
        user = await user_service.get_user(target_id)
        
        if not user:
            await message.reply("❌ User not found.")
            return
            
        text = (
            f"👤 <b>User Info:</b>\n"
            f"ID: <code>{user.id}</code>\n"
            f"Name: {user.full_name}\n"
            f"Bio: {user.bio[:50]}...\n"
            f"Pro Until: {user.pro_until}\n"
            f"Created: {user.created_at}"
        )
        await message.reply(text)
        
    except ValueError:
        await message.reply("❌ Invalid format. Use numbers.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

