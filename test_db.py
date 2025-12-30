# test_db.py
import os
import sys
from supabase import create_client
from dotenv import load_dotenv

# Исправление кодировки для Windows
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

print(f"Connecting to: {url}")
# Не печатай весь ключ в консоль, только начало, чтобы проверить
print(f"Regular key starts with: {key[:10] if key else 'None'}...") 
print(f"Service key available: {bool(service_key)}")
if service_key:
    print(f"Service key starts with: {service_key[:10]}...")

# Используем SERVICE_ROLE_KEY как основной (как в боте)
api_key = service_key or key
if service_key:
    print("[OK] Using SERVICE_ROLE_KEY (bypasses RLS)")
else:
    print("[WARN] Using regular key (RLS may block operations)")

supabase = create_client(url, api_key)
# Для сравнения - обычный ключ
supabase_regular = create_client(url, key) if key else None

USER_ID = 6108932752

print(f"\n=== Test 1: Find user's contacts (NOT archived) - using SERVICE_ROLE_KEY ===")
all_contacts = supabase.table("contacts").select("id, name, user_id, created_at, is_archived").eq("user_id", USER_ID).eq("is_archived", False).order("created_at", desc=True).limit(10).execute()
print(f"User {USER_ID} has {len(all_contacts.data)} non-archived contacts")
for c in all_contacts.data:
    print(f"  - ID: {c.get('id')}, Name: {c.get('name')}, Created: {c.get('created_at')}, Archived: {c.get('is_archived')}")

print(f"\n=== Test 1b: Find user's contacts (INCLUDING archived) ===")
all_contacts_archived = supabase.table("contacts").select("id, name, user_id, created_at, is_archived").eq("user_id", USER_ID).order("created_at", desc=True).limit(10).execute()
print(f"User {USER_ID} has {len(all_contacts_archived.data)} total contacts (including archived)")
for c in all_contacts_archived.data:
    print(f"  - ID: {c.get('id')}, Name: {c.get('name')}, Archived: {c.get('is_archived')}")

print(f"\n=== Test 1c: ALL contacts in table (any user) - проверка что RLS обойден ===")
all_any = supabase.table("contacts").select("id, name, user_id, is_archived").limit(5).execute()
print(f"Table has {len(all_any.data)} contacts (showing first 5)")
for c in all_any.data:
    print(f"  - ID: {c.get('id')}, Name: {c.get('name')}, User: {c.get('user_id')}, Archived: {c.get('is_archived')}")

if not all_contacts.data and not all_contacts_archived.data:
    print(f"\n=== No contacts found. Creating test contact (using SERVICE_ROLE_KEY) ===")
    try:
        test_contact = supabase.table("contacts").insert({
            "user_id": USER_ID,
            "name": "Test Contact for Deletion",
            "summary": "This is a test contact that will be deleted",
            "meta": {},
            "is_archived": False
        }).execute()
        if test_contact.data:
            CONTACT_ID = test_contact.data[0].get('id')
            print(f"[OK] Created test contact with ID: {CONTACT_ID}")
        else:
            print("[FAIL] Failed to create test contact (no data returned)")
            CONTACT_ID = None
    except Exception as e:
        print(f"[FAIL] Failed to create test contact: {e}")
        CONTACT_ID = None
elif all_contacts.data:
    CONTACT_ID = all_contacts.data[0].get('id')
    print(f"\n=== Using first non-archived contact ID: {CONTACT_ID} ===")
elif all_contacts_archived.data:
    CONTACT_ID = all_contacts_archived.data[0].get('id')
    print(f"\n=== Using first archived contact ID: {CONTACT_ID} ===")
else:
    CONTACT_ID = None

if CONTACT_ID:
    print(f"\n=== Test 2: Direct search by ID (using SERVICE_ROLE_KEY - как в боте) ===")
    print(f"Searching for ID: {CONTACT_ID}")
    response = supabase.table("contacts").select("*").eq("id", CONTACT_ID).execute()
    print(f"Result count: {len(response.data)}")
    if response.data:
        contact = response.data[0]
        print(f"[OK] Contact found: {contact.get('name')}, Owner: {contact.get('user_id')}")
        print(f"   Match check: {str(contact.get('user_id')) == str(USER_ID)}")
    else:
        print("[FAIL] Contact NOT found!")
    
    # Для сравнения - проверка через обычный ключ (если есть)
    if supabase_regular:
        print(f"\n=== Test 2b: Direct search by ID (using REGULAR key - для сравнения) ===")
        response_regular = supabase_regular.table("contacts").select("*").eq("id", CONTACT_ID).execute()
        print(f"Result count: {len(response_regular.data)}")
        if response_regular.data:
            print(f"[OK] Contact found with regular key too")
        else:
            print("[WARN] Contact NOT found with regular key (RLS blocking)")

print(f"\n=== Test 3: RPC get_recent_contacts (OLD METHOD - BUGGY) ===")
try:
    rpc_result = supabase.rpc("get_recent_contacts", {
        "match_user_id": USER_ID,
        "match_count": 10
    }).execute()
    print(f"RPC returned {len(rpc_result.data)} contacts")
    for c in rpc_result.data:
        print(f"  - ID: {c.get('id')}, Name: {c.get('name')}")
        # Проверяем, существует ли этот ID в таблице
        check = supabase.table("contacts").select("id").eq("id", c.get('id')).execute()
        if not check.data:
            print(f"    WARNING: This ID does NOT exist in contacts table!")
except Exception as e:
    print(f"RPC failed: {e}")

print(f"\n=== Test 4: Direct query (NEW METHOD - как в исправленном коде) ===")
direct_result = supabase.table("contacts")\
    .select("id, name, summary, meta")\
    .eq("user_id", USER_ID)\
    .eq("is_archived", False)\
    .order("created_at", desc=True)\
    .limit(10)\
    .execute()
print(f"[OK] Direct query returned {len(direct_result.data) if direct_result.data else 0} contacts")
if direct_result.data:
    for c in direct_result.data:
        print(f"  - ID: {c.get('id')}, Name: {c.get('name')}")
        # Проверяем, что этот ID реально существует
        check = supabase.table("contacts").select("id").eq("id", c.get('id')).execute()
        if check.data:
            print(f"    [OK] ID exists in table")
        else:
            print(f"    [ERROR] ID does NOT exist!")
else:
    print("  [INFO] No contacts found (this is correct if user has no contacts)")

if CONTACT_ID:
    print(f"\n=== Test 5: Test deletion (using SERVICE_ROLE_KEY - как в боте) ===")
    # Проверяем через service key (обходит RLS)
    check_before = supabase.table("contacts").select("*").eq("id", CONTACT_ID).execute()
    if check_before.data:
        contact = check_before.data[0]
        print(f"Contact before delete: ID={contact.get('id')}, Name={contact.get('name')}, Owner={contact.get('user_id')}")
        print(f"Request user: {USER_ID}")
        print(f"Match: {str(contact.get('user_id')) == str(USER_ID)}")
        
        # Пробуем удалить через service key (как в боте)
        delete_result = supabase.table("contacts")\
            .delete()\
            .eq("id", CONTACT_ID)\
            .execute()
        
        print(f"Delete result: {len(delete_result.data) if delete_result.data else 0} rows deleted")
        
        # Проверяем, что контакт удален
        check_after = supabase.table("contacts").select("id").eq("id", CONTACT_ID).execute()
        if not check_after.data:
            print(f"[OK] SUCCESS: Contact deleted!")
        else:
            print(f"[FAIL] FAILED: Contact still exists!")
    else:
        print(f"[FAIL] Contact {CONTACT_ID} not found, cannot test deletion")

