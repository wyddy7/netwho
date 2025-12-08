# Epic 7: User Settings & Polish

## Goal
Implement user settings to control bot behavior (Safe Mode vs Rage Mode) and polish the UX for contact management.

## User Stories
1. **Settings Menu**: As a user, I want to type `/settings` and see a menu to configure the bot.
2. **Approvals (Rage Mode)**: As a user, I want to toggle "Confirm Add" and "Confirm Delete" options.
   - **Safe Mode (Default)**: Bot asks for confirmation before saving or deleting.
   - **Rage Mode**: Bot acts immediately without questions.
3. **Contact Editing**: As a user, I want to edit contact details (Description/Name). (Pending next)
4. **Recent Contacts**: As a user, I want to see "Who do I have?" efficiently. (Done)

## Implementation Plan

### 1. Database & Schema
- [x] Add `settings` JSONB column to `users` table.
- [x] Create `get_recent_contacts` RPC function.
- [x] Update `User` and `Contact` schemas.

### 2. Services
- [x] Update `UserService` to handle `settings`.
- [x] Update `SearchService` to support `get_recent_contacts`.
- [x] Update `AIService` (Router) to respect `settings.confirm_add` and `settings.confirm_delete`.

### 3. Handlers
- [x] Create `/settings` handler with Inline Buttons.
- [x] Update `TextHandler` to support `ContactDraft` (confirmation flow).
- [x] Update `TextHandler` to support `ContactCreate` (auto-save flow).

### 4. Next Steps
- [ ] Implement `update_contact` tool for editing.
- [ ] Add `edit` button to contact card.
