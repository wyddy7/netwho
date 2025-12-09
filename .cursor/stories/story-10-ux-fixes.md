# Story 10: UX Fixes (Command Priority & Subscription Awareness)

## 🎯 Goal
Fix frustration points where the bot gets stuck in specific states (like "Waiting for Focus") and ignores global commands (like `/settings` or `/cancel`), and enable the AI to answer questions about subscription status.

## 📦 Deliverables

### 1. FSM (State Machine) Fixes
- [ ] **Global Command Override**: Ensure commands like `/settings`, `/start`, `/cancel` ALWAYS execute, even if the user is in a state (e.g., `SettingsStates.waiting_for_focus`).
- [ ] **State Handler Filters**: Add filters to state handlers (e.g., `waiting_for_focus`) to IGNORE text starting with `/`, allowing it to fall through to command handlers.

### 2. AI Capabilities
- [ ] **Subscription Tool**: Add `check_subscription_status` tool to `AIService` / `Router Agent`.
- [ ] **System Prompt Update**: Ensure the agent knows it can check subscription status.

### 3. Voice/Admin UX (Refinement)
- [ ] **Admin via Voice**: Explain to the user (via AI response) that sensitive admin actions (like granting Pro) require specific slash commands for security, rather than just saying "I won't do it".

## 🛠 Technical Implementation

### A. Update `app/handlers/settings.py`
- Modify `@router.message(SettingsStates.waiting_for_focus)` to include `& ~F.text.startswith("/")`.
- Modify `@router.message(SettingsStates.waiting_for_time)` similarly.

### B. Update `app/services/ai_service.py`
- Add `get_subscription_info(user_id)` tool definition.
- Implement the tool execution in `run_router_agent`.

## 📝 Success Criteria
1.  User enters "Set Focus" -> Bot asks "Topic?" -> User types `/settings` -> Bot **immediately** opens settings menu (not sets focus to "/settings").
2.  User asks "Do I have a subscription?" -> Bot answers "Yes, until [date]" or "No, buy it here".

