# Story 17: Admin Tools

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/admin-tools`

## Context
We need a way to create organizations to test the flow and onboard communities.

## Technical Tasks

### 1. Admin Command
- [ ] Implement handler for `/create_org "Name"`.
- [ ] Restrict to Bot Admins (check `app/config.py` or `admin_ids`).

### 2. Implementation
- [ ] Parse the name.
- [ ] Insert into `organizations` table:
    ```sql
    INSERT INTO organizations (name, owner_id) VALUES ('Name', admin_user_id) RETURNING id;
    ```
- [ ] **Auto-add Owner:** Insert admin into `organization_members` with role `owner`.
- [ ] Return the `invite_code` or `id` to the admin.

## Definition of Done
- [ ] Command `/create_org` works for admins.
- [ ] Creates row in `organizations`.
- [ ] Adds creator to `organization_members`.
