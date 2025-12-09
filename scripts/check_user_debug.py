import sys
import os
sys.path.append(os.getcwd())

import asyncio
from app.services.user_service import user_service
from app.schemas import RecallSettings

async def check_user_settings():
    user_id = 6108932752
    user = await user_service.get_user(user_id)
    if user:
        print(f"User found: {user.id}")
        print(f"Recall Settings BEFORE: {user.recall_settings}")
        
        # Try updating
        rs = user.recall_settings
        rs.time = "20:05"
        print("Attempting to update time to 20:05...")
        success = await user_service.update_recall_settings(user_id, rs)
        print(f"Update success: {success}")
        
        # Check again
        user_after = await user_service.get_user(user_id)
        print(f"Recall Settings AFTER: {user_after.recall_settings}")
    else:
        print("User not found")

if __name__ == "__main__":
    asyncio.run(check_user_settings())
