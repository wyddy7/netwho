import sys
import os
sys.path.append(os.getcwd())

import asyncio
from app.infrastructure.supabase.client import get_supabase

async def check_raw_db():
    supabase = get_supabase()
    user_id = 6108932752
    
    # Read Raw
    response = supabase.table("users").select("recall_settings").eq("id", user_id).execute()
    print(f"RAW DB DATA: {response.data}")
    
    # Try Update Raw
    new_settings = {"enabled": True, "days": [1, 4], "time": "20:05", "focus": None, "last_sent_date": None}
    print(f"Writing RAW: {new_settings}")
    
    upd_response = supabase.table("users").update({"recall_settings": new_settings}).eq("id", user_id).execute()
    print(f"Update Result Data: {upd_response.data}")
    
    # Read Again
    response_after = supabase.table("users").select("recall_settings").eq("id", user_id).execute()
    print(f"RAW DB DATA AFTER: {response_after.data}")

if __name__ == "__main__":
    asyncio.run(check_raw_db())

