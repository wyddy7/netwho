# Story 16: UI & Scope Selection

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/ui-scope`
**Prerequisites:** Story 14

## Context
When a user adds a contact, they should choose whether it's "Personal" or for a specific "Organization" (if they belong to any).

## Technical Tasks

### 1. Logic Update in Handler
- [ ] In `app/handlers/text.py` (or where contacts are added):
    1.  Extract contact data (LLM).
    2.  Call `repo.get_user_orgs(user_id)`.
    3.  **Condition:**
        -   **If 0 orgs:** Save directly as Personal (`org_id=None`).
        -   **If >0 orgs:** Pause execution, show **Inline Keyboard**.

### 2. UI Implementation (Inline Keyboard)
- [ ] Create buttons:
    -   `[🔒 Личное]` (callback_data=`scope:personal`)
    -   `[📢 Org Name]` (callback_data=`scope:org:<uuid>`)
- [ ] Send message: "Куда сохранить контакт?"

### 3. Callback Handler
- [ ] Implement handler for `scope:*` callbacks.
- [ ] Parse data.
- [ ] Call `repo.create(..., org_id=selected_id)`.
- [ ] Edit message to show success: "✅ Сохранено в [Org Name/Личное]".

## Definition of Done
- [ ] Users without orgs experience no change (auto-save).
- [ ] Users with orgs see buttons.
- [ ] Clicking a button saves to the correct scope.
