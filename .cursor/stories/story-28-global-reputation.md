# Story 28: Global Reputation & Perks (User Profile System)

**Epic:** Epic 3 - Social Intelligence (Gamification)
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/global-reputation`
**Prerequisites:** Story 23 (Give-to-Get), Story 27 (Unified Response)

## Context
Current "Give-to-Get" logic (Story 23) is organization-specific (local scope). To encourage long-term engagement and quality contributions, we need a **Global Profile System**. Users should be rewarded for their total activity across all communities.

**Goal:** Transform the bot from a utility tool into a "Social RPG" where adding value unlocks perks.

## Conceptual Model

### 1. Global Metrics (Table: `users`)
- `total_contacts_added`: Count of unique contacts added (across personal & orgs).
- `reputation_score`: Dynamic score based on quality (e.g., contacts with full bio +10, contacts deleted by others -5).
- `joined_orgs_count`: Number of active memberships.

### 2. Perks System (What you get)
- **Level 1 (Newbie):** 3 org searches/day limit.
- **Level 2 (Contributor):** >10 contacts added. Unlimited searches. Custom "Bio" extraction.
- **Level 3 (Connector):** >50 contacts added. Auto-approve in open communities. "Top Voice" badge.

## Technical Tasks

### 1. Database Migration
- [ ] Create `migrations/migration_epic3_reputation.sql`:
    - Add columns to `users`:
        - `total_contacts_added` (INT, default 0)
        - `reputation_score` (INT, default 0)
        - `level` (TEXT, enum: 'newbie', 'contributor', 'connector')

### 2. Event Handlers (User Service)
- [ ] Implement `on_contact_created(user_id)` hook:
    - Increment `total_contacts_added`.
    - Recalculate Level:
        - If `total_contacts_added` >= 10 -> Upgrade to 'contributor'.
        - If `total_contacts_added` >= 50 -> Upgrade to 'connector'.
    - Send "Level Up" notification to user via bot.

### 3. Profile UI Update (`/profile`)
- [ ] Update `app/handlers/profile.py`:
    - Display current Level and Stats.
    - Show progress bar to next level: "Add 3 more contacts to reach Contributor status".

### 4. Integration with Access Control (Story 23 update)
- [ ] Update `check_search_limit` in `UserService`:
    - If `user.level` >= 'contributor', bypass the "3 searches" limit even if `status=pending`.
    - *Rationale:* Trusted users don't need to prove themselves every time.

## Acceptance Criteria
- [ ] Adding a contact increments the global counter in `users` table.
- [ ] Crossing the threshold (e.g., 10 contacts) triggers a notification "You are now a Contributor!".
- [ ] `/profile` shows the new badge/level.
- [ ] 'Contributor' level users bypass the "Give-to-Get" search block in new orgs.

## Definition of Done
- [ ] Migration applied.
- [ ] Logic for incrementing stats implemented.
- [ ] Level-up system works.
- [ ] UI reflects global status.
