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
        "• <code>/debug_user &lt;user_id&gt;</code> - Raw DB info\n"
        "• <code>/create_org &lt;name&gt;</code> - Create Organization\n"
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
        
        # Check if user exists
        user = await user_service.get_user(target_id)
        if not user:
            await message.reply("❌ User not found.")
            return
        
        # Revoke subscription using centralized method
        success = await user_service.revoke_subscription(target_id)
        
        if success:
            await message.reply(f"✅ Pro subscription revoked for user {target_id}.")
        else:
            await message.reply("❌ Failed to revoke subscription. Check server logs.")
            
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
            
        bio_preview = user.bio[:50] + "..." if user.bio and len(user.bio) > 50 else (user.bio or "None")
        text = (
            f"👤 <b>User Info:</b>\n"
            f"ID: <code>{user.id}</code>\n"
            f"Name: {user.full_name}\n"
            f"Bio: {bio_preview}\n"
            f"is_premium: {user.is_premium}\n"
            f"Pro Until: {user.pro_until}\n"
            f"Created: {user.created_at}"
        )
        await message.reply(text)
        
    except ValueError:
        await message.reply("❌ Invalid format. Use numbers.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@router.message(Command("debug_user"))
async def cmd_debug_user(message: types.Message):
    """
    Shows RAW JSON data from Supabase for a user to debug field issues.
    """
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply("Usage: /debug_user <user_id>")
            return
            
        target_id = int(args[1])
        
        # Direct raw select
        response = user_service.supabase.table("users").select("*").eq("id", target_id).execute()
        
        if not response.data:
            await message.reply("❌ User not found in DB.")
            return
            
        user_data = response.data[0]
        
        # Format important fields
        # Escape HTML chars in raw output just in case
        import html
        
        raw_dump = html.escape(str(user_data)[:3000])
        type_info = html.escape(str(type(user_data.get('is_premium'))))
        
        debug_text = (
            f"🐛 <b>DEBUG INFO for {target_id}</b>\n\n"
            f"<b>is_premium:</b> <code>{user_data.get('is_premium')}</code> ({type_info})\n"
            f"<b>pro_until:</b> <code>{user_data.get('pro_until')}</code>\n"
            f"<b>Raw Data:</b>\n<pre>{raw_dump}</pre>" 
        )
        
        await message.reply(debug_text)
        
    except Exception as e:
        logger.error(f"Debug user error: {e}")
        await message.reply(f"❌ Error: {e}")

@router.message(Command("create_org"))
async def cmd_create_org(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    # Parse name: /create_org "My Org"
    # Or just /create_org My Org
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Usage: /create_org <name>")
        return
        
    org_name = args[1].strip('"').strip("'")
    
    # We need Repo. 
    # Use get_supabase() and ContactRepository(supabase)
    from app.infrastructure.supabase.client import get_supabase
    from app.repositories.contact_repo import ContactRepository
    
    repo = ContactRepository(get_supabase())
    
    try:
        result = await repo.create_org(org_name, message.from_user.id)
        # result = {'id': uuid, 'invite_code': code}
        
        await message.reply(
            f"✅ <b>Organization Created!</b>\n\n"
            f"Name: {org_name}\n"
            f"ID: <code>{result['id']}</code>\n"
            f"Invite Code: <code>{result['invite_code']}</code>"
        )
    except Exception as e:
        logger.error(f"Create org error: {e}")
        await message.reply(f"❌ Error: {e}")
