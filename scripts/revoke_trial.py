import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app.services.user_service import user_service
from app.infrastructure.supabase.client import get_supabase

async def revoke_access(user_id: int):
    logger.info(f"Revoking access for user {user_id}...")
    
    supabase = get_supabase()
    
    try:
        # Clear both pro_until and trial_ends_at
        response = supabase.table("users").update({
            "pro_until": None,
            "trial_ends_at": None,
            "is_premium": False
        }).eq("id", user_id).execute()
        
        if response.data:
            logger.info(f"✅ Success! User {user_id} is now on Free Plan.")
        else:
            logger.error("❌ Failed to update user (User not found?).")
            
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/revoke_trial.py <user_id>")
        sys.exit(1)
        
    try:
        uid = int(sys.argv[1])
        asyncio.run(revoke_access(uid))
    except ValueError:
        print("User ID must be an integer.")

