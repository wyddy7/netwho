# Story 18: UX Polish (Org Visibility)

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/ux-polish`
**Prerequisites:** Story 16

## Context
Features from Stories 13-17 are technically working, but the UI is "blind". Users cannot distinguish between Personal and Org contacts in search results, and save confirmation messages are generic.

## Technical Tasks

### 1. Fix Save Confirmation (Text Handler)
- [ ] Modify `app/handlers/text.py`:
    -   In `on_scope_select`, avoid hardcoded "Организацию".
    -   Lookup the organization name to display explicitly: `✅ Записал в 📢 Python Heroes`.

### 2. Fix Search Rendering (UI)
- [ ] Modify `handle_agent_response` in `app/handlers/text.py`:
    -   Check if `res.org_name` is present.
    -   Format output: `👤 Name [📢 OrgName]` vs `👤 Name`.

### 3. Fix "Recent Contacts" Query
- [ ] Modify `app/services/search_service.py` -> `get_recent_contacts`.
- [ ] Update Supabase query to join organizations: `.select("*, organizations(name)")`.
- [ ] Map the result correctly to `SearchResult` so `org_name` is populated.

## Definition of Done
- [ ] Saving a contact to "Skop" replies "Saved to Skop".
- [ ] Searching "who do I have" shows `[📢 Skop]` next to shared contacts.
- [ ] Searching specifically (Hybrid) shows `[📢 Skop]` next to shared contacts.
