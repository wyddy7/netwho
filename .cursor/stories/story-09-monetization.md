# Story 09: Monetization & Telegram Stars (NetWho Pro)

## 🎯 Goal
Implement a native monetization flow using **Telegram Stars (XTR)**. Transition from a purely free tool to a **Freemium model** that offers core value for free while unlocking advanced features for power users, all without external payment gateways.

## 💰 Monetization Model (Freemium)

### Free Plan (Default)
- **Contacts Limit:** 10-15 contacts (Soft Paywall - enough to see value).
- **Recall Limit:** 1 random recall / week.
- **Voice Limit:** 30 seconds max per note.
- **News-Jacking:** Disabled or limited.

### Pro Plan (100 Stars / ~2$)
- **Unlimited Contacts.**
- **Smart Recall:** Intelligent selection based on profile.
- **Long Voice Notes:** No duration limits.
- **News-Jacking:** Full access to reading links and matching contacts.

## 📦 Deliverables

### 1. Database Schema
- [ ] Add `pro_until` (Timestamp with time zone, nullable) to `users` table.
- [ ] Add helper methods in `DBService`: `is_pro(user_id)`, `update_subscription(user_id, days)`.

### 2. Access Control (The "Soft" Wall)
- [ ] **Limits Checker (`check_limits`)**:
    - Centralized logic to check if a user can perform an action based on their status (Free/Pro) and current usage.
    - Soft limit message: *"🚧 Whoa, you've added 10 contacts! To add the 11th and unlock unlimited power, you need Pro (just 100 ⭐️)."*
- [ ] **Trial Mode**:
    - Give new users (and existing ones during migration) **3 days of Pro** to demonstrate value.
- [ ] **Integration Points**:
    - `add_contact` (Limit count).
    - `voice_handler` (Limit duration).
    - `recall_job` (Limit frequency/logic).

### 3. Payment Flow (Telegram Stars)
- [ ] **Invoice Handler**:
    - Command/Button `💎 Buy Pro`.
    - Send Invoice with currency `XTR` and payload `netwho_pro_month`.
- [ ] **Pre-Checkout Query**:
    - Auto-approve transaction.
- [ ] **Success Handler**:
    - Handle `successful_payment` content type.
    - Update DB: extend `pro_until`.
    - Notify user: *"🎉 You are now Pro!"*

### 4. Admin Tools
- [ ] **God Mode Command**: `/give_pro <user_id> <days>` to manually grant subscriptions (for friends/beta testers).

## 🛠 Technical Implementation

### A. Database Migration
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_until TIMESTAMPTZ;
```

### B. Payment Handlers (`app/handlers/payments.py`)
- Implement `buy_pro` command.
- Implement `pre_checkout_query` handler.
- Implement `success_payment` handler.

### C. Logic & Middleware
- Create `services/subscription_service.py` or methods in `UserService` to handle logic:
    - `check_can_add_contact(user_id)`
    - `check_can_use_voice(user_id, duration)`
- Integrate checks into `handlers/contacts.py` and `handlers/voice.py`.

## 📝 Success Criteria
1.  Admin can grant Pro status manually.
2.  User sees "Buy Pro" invoice when hitting limits.
3.  Payment with Stars works successfully (test environment).
4.  Pro users bypass all limits.
5.  New users get automatic 3-day trial.

