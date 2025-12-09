import sys
import os
sys.path.append(os.getcwd())

import asyncio
from app.services.user_service import user_service
from app.schemas import RecallSettings

async def fix_user_settings():
    user_id = 6108932752
    user = await user_service.get_user(user_id)
    if user:
        print(f"User found: {user.id}")
        rs = user.recall_settings
        print(f"Current Settings: {rs}")
        
        # Ensure correct day is set for testing (Today is Tuesday = 1)
        # If user has only [4], add 1
        if 1 not in rs.days:
            rs.days.append(1)
            rs.days.sort()
            print(f"Adding Tuesday (1) to days: {rs.days}")
            
        # Ensure time is something reasonable (e.g. now + 2 mins)?
        # No, leave time as is (20:05), it should work if we are within the hour.
        # But if it's already 20:20, 20:05 is valid (diff=15 min).
        
        success = await user_service.update_recall_settings(user_id, rs)
        print(f"Update success: {success}")
    else:
        print("User not found")

if __name__ == "__main__":
    asyncio.run(fix_user_settings())

