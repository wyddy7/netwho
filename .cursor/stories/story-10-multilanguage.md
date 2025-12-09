# Epic 10: Multi-language Support 🌍

## 🎯 Goal
Implement language selection (Russian 🇷🇺, English 🇺🇸, Spanish 🇪🇸) to expand the user base and improve UX for non-Russian speakers.

## 📋 Deliverables

### 1. Database Schema Update
- [ ] Add `language_code` to `users` table or `settings` JSONB.
- [ ] Default value: `ru` (or detect from Telegram `user.language_code`).

### 2. Settings Menu UI
- [ ] Add "🌐 Language / Язык" button in `/settings`.
- [ ] Sub-menu with flags:
    - 🇷🇺 Русский
    - 🇺🇸 English
    - 🇪🇸 Español
- [ ] Save selection to DB.

### 3. Middleware & Context
- [ ] Update `Middleware` to fetch user language.
- [ ] Pass `language` context to AI prompts (Router, Extractor).
- [ ] "You are a generic assistant" -> "You are a Russian assistant" (dynamic system prompt injection).

### 4. Localization (i18n)
- [ ] Extract hardcoded strings from handlers (`text.py`, `onboarding.py`, etc.).
- [ ] Create a lightweight translation system (dictionary-based or `fluent`).
    - `messages_ru.py`
    - `messages_en.py`
    - `messages_es.py`

### 5. AI Prompt Adaptation
- [ ] Update `prompts.yaml` to accept a `{{language}}` variable.
- [ ] Instruct AI to reply strictly in the selected language.

## 🛠 Technical Implementation Draft

### SQL
```sql
ALTER TABLE users ADD COLUMN language_code VARCHAR(5) DEFAULT 'ru';
```

### Python (Settings)
```python
# app/schemas.py
class UserSettings(BaseModel):
    language: str = "ru" # ru, en, es
```

### Best Practices
- **Detection:** On `/start`, check `message.from_user.language_code`. If `ru`, set `ru`. Else `en`.
- **Consistency:** If user switches to English, ALL system messages (buttons, errors) AND AI responses must switch.

