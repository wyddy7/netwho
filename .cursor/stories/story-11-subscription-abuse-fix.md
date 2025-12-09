# User Story 11: Fix Subscription Abuse via Account Deletion

## Problem
Currently, when a user executes `/delete_me`, the system performs a hard delete of the user record from the database. This allows users to:
1. Register (get 3 days trial).
2. Use the service.
3. Delete account (`/delete_me`).
4. Register again immediately.
5. Get a NEW 3-day trial because the system treats them as a completely new user.

This loop allows indefinite use of the Pro subscription without paying ("abusing" the system).

## Solution
Change the account deletion logic to a "Soft Reset" or "Data Wipe" that preserves the user identity and subscription status.

### Requirements
1.  **Preserve Identity**: Do not delete the row from the `users` table. The `id`, `created_at`, and `pro_until` (subscription expiration) must be preserved.
2.  **Delete Personal Data**:
    *   Delete all contacts linked to the user.
    *   Delete all chat history.
    *   Clear `bio` (User profile description).
    *   Reset `settings` and `recall_settings` to defaults (optional, but good for "fresh start" feeling).
3.  **Onboarding Behavior**:
    *   When the user "starts" again (`/start`), the system should see they exist.
    *   Since they exist, it **MUST NOT** grant a new trial.
    *   Since their `bio` is empty, it **SHOULD** trigger the Onboarding flow (asking who they are).

## Implementation Plan
1.  Modify `UserService.delete_user_full` in `app/services/user_service.py`.
    *   Remove the `users.delete()` call.
    *   Add `users.update()` call to clear `bio`, reset settings.
    *   Keep `contacts.delete()` and `chat_history.delete()`.
2.  Verify `app/handlers/onboarding.py` logic handles "existing user with no bio" correctly (it should already do this).
3.  Verify `app/middlewares/user_check.py` handles "existing user" correctly (it should just proceed without resurrection/trial grant).

## Acceptance Criteria
*   [ ] User registers -> Gets Trial.
*   [ ] User deletes account -> Data is gone, but User ID exists in DB.
*   [ ] User sends `/start` -> No new trial granted (subscription date remains old).
*   [ ] User is prompted for Onboarding again.

