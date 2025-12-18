# Epic: Organization & Community SaaS (Lean Agentic SaaS)

## Context
Transitioning to a B2B/Community tool using **Agentic Design Patterns (US/EU 2025 Standard)**.
Approved Architecture: **Logic in LLM + Simple Infra (Shared Schema)**.
Goal: "Invisible Context" & "Ambient Intelligence".

## User Stories

### US-1: Organization Infrastructure (Shared Schema)
**As a System**, I use a simple `org_id` column to distinguish Personal vs. Shared data. This is the **"Shared Schema, Shared Database"** pattern approved for MVP agents to avoid over-engineering.

**Technical Tasks:**
- [ ] Create `organizations` table (UUID, name, owner_id, invite_code).
- [ ] Create `organization_members` table (user_id, org_id, role).
- [ ] Add `org_id` column to `contacts` table (nullable).
    - `org_id IS NULL` = Personal (Private).
    - `org_id IS NOT NULL` = Shared (Visible to Org).
- [ ] Create SQL Migration script.

### US-2: Smart Routing (Context Engineering)
**As a User**, I want to just speak. The Agent determines the destination based on my active context and content keywords.
*Pattern: "Forgiveness over Permission" + "Optimistic Execution"* — act first, provide "Undo" later.

**Logic:**
1.  **Context Analysis:** Check User's active organizations (e.g., "Python Community").
2.  **Keyword Heuristics:** If text contains "team", "chat", "community", "work", "colleague" -> **Auto-route to Org**.
3.  **Default:** If ambiguous, route to Personal.
4.  **Feedback:** Notify user "Saved to [OrgName]" with a tool to `move_contact` if mistaken.

**Technical Tasks:**
- [ ] Update `Router Agent` prompt:
    - Add instruction: *"Context: User is a member of [OrgName]. If text relates to [Keywords], route to Org."*
    - Add instruction: *"If user joined via 'PythonOrg', assume 'Ambiguous' contacts belong to 'PythonOrg' by default."*
- [ ] Implement `move_contact` tool (for "Undo/Fix" actions).
- [ ] **Remove** blocking In-line Keyboards.

### US-3: Agentic Onboarding & Deep Linking
**As a User**, I join an organization via a link, and the Agent immediately updates my "Context".

**Technical Tasks:**
- [ ] Implement Deep Link handling (`/start join_<code_org>`).
- [ ] Update `User Memory`: Store "Active Contexts" to inform the Router.

### US-4: Unified Search & Privacy Guard
**As a Member**, I want to search across Personal and Shared data simultaneously without data leakage.
*Pattern: "Retrieve-Then-Filter" with Structured Output.*

**Risk Mitigation:**
To prevent the LLM from accidentally mixing private contacts into a public summary, we MUST use **Structured Output** (JSON).

**Technical Tasks:**
- [ ] Update `match_contacts` to accept `allowed_org_ids` (SQL Filter).
- [ ] Update `Search Agent`:
    1.  Perform hybrid search (Personal + Org).
    2.  **CRITICAL:** Force LLM to output strictly structured data:
        ```json
        {
          "personal_matches": ["Mom", "Tinder Date"],
          "org_matches": ["Vitalik Python", "Kamil CEO"]
        }
        ```
    3.  Render response to user in distinct sections (e.g., "👤 Personal" vs "🏢 Community").

### US-5: Verification & Trust
**As a Viewer**, I want to know if a contact is "Real" (linked to Telegram ID).

**Technical Tasks:**
- [ ] Add `telegram_id` to `contacts` table.
- [ ] UI: Add ✅ for verified users in the text output.

## Database Migration Plan
```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id),
    invite_code TEXT UNIQUE DEFAULT substring(md5(random()::text) from 0 for 8),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE organization_members (
    user_id BIGINT REFERENCES users(id),
    org_id UUID REFERENCES organizations(id),
    role TEXT DEFAULT 'member', -- 'owner', 'admin', 'member'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, org_id)
);

ALTER TABLE contacts ADD COLUMN org_id UUID REFERENCES organizations(id);
CREATE INDEX idx_contacts_org_id ON contacts(org_id);
-- Add telegram_id for verification
ALTER TABLE contacts ADD COLUMN telegram_id BIGINT;
```

## Execution Order (Action Plan)
1.  **Database Migration (1h):** Apply SQL script.
2.  **Router Upgrade (2h):** Update System Prompt with "Context Engineering".
3.  **Search Logic (2h):** Implement `OR org_id = X` and **Structured Output** rendering.
4.  **Release:** Deploy and share link with Pilot User (Kamil).
