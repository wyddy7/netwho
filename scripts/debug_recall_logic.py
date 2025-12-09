import sys
import os
sys.path.append(os.getcwd())

import asyncio
import datetime
from app.services.user_service import user_service
from app.infrastructure.supabase.client import get_supabase
from app.services.recall_service import recall_service

async def debug_recall_process():
    user_id = 6108932752
    print(f"--- Debugging Recall for User {user_id} ---")
    
    # 1. Fetch User
    user = await user_service.get_user(user_id)
    if not user:
        print("User not found!")
        return

    # 2. Time Checks
    now = datetime.datetime.now()
    today_weekday = now.weekday()
    current_date_str = now.strftime("%Y-%m-%d")
    
    print(f"Now: {now}")
    print(f"Weekday: {today_weekday} (0=Mon, 1=Tue, ...)")
    print(f"Date: {current_date_str}")
    
    rs = user.recall_settings
    print(f"Settings: {rs}")
    
    # 3. Logic Steps
    if not rs.enabled:
        print("FAIL: Recall disabled")
        return

    days = rs.days
    if today_weekday not in days:
        print(f"FAIL: Day mismatch. Today {today_weekday} not in {days}")
        # Continue anyway for debug? No, that's a hard stop in code.
        # But let's verify if we fixed it.

    last_sent = rs.last_sent_date
    if last_sent == current_date_str:
        print(f"FAIL: Already sent today ({last_sent})")
        # Continue to check other logic
    else:
        print("PASS: Not sent today yet")

    # Time Window
    user_time_str = rs.time
    try:
        uh, um = map(int, user_time_str.split(':'))
        user_time = now.replace(hour=uh, minute=um, second=0, microsecond=0)
    except:
        print("Error parsing time")
        user_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
    
    diff_minutes = (now - user_time).total_seconds() / 60
    print(f"User Target Time: {user_time}")
    print(f"Diff Minutes: {diff_minutes}")
    
    if 0 <= diff_minutes < 60:
        print("PASS: Time window valid")
    else:
        print("FAIL: Time window invalid (must be 0 <= diff < 60)")

    # 4. Contacts Check
    print("Checking Contacts...")
    contacts = await recall_service.get_random_contacts_for_user(user_id, limit=4)
    print(f"Found {len(contacts)} contacts")
    if len(contacts) == 0:
        print("FAIL: No contacts found! This is likely the cause.")
        
        # Check raw contacts count
        supabase = get_supabase()
        res = supabase.table("contacts").select("count", count="exact").eq("user_id", user_id).execute()
        print(f"Total Raw Contacts in DB: {res.count}")
        
        res_active = supabase.table("contacts").select("count", count="exact").eq("user_id", user_id).eq("is_archived", False).execute()
        print(f"Active Contacts in DB: {res_active.count}")
    else:
        print("PASS: Contacts exist")
        for c in contacts:
            print(f" - {c.get('name')} (Last: {c.get('last_interaction')})")

if __name__ == "__main__":
    asyncio.run(debug_recall_process())

