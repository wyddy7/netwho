# Story 26: Simple Deduplication (Canonical MVP)

**Epic:** Epic 2 - Search Intelligence (Умный Поиск)
**Parent:** .cursor/tz/epic 2 search ai.md
**Branch:** `feature/epic2-simple-deduplication`
**Prerequisites:** Story 20 (Schema & Access Control)

## Context
Предотвращаем дублирование людей внутри одной организации через уникальность Telegram Username. Это легкая версия "canonical persons" — без глобальной таблицы, но с защитой от дублей внутри орги.

## Technical Tasks

### 1. Database Migration
- [ ] Обновить `migrations/migration_epic2_search.sql` (или создать отдельную):
  - Добавить поле `telegram_username TEXT` в таблицу `contacts`.
  - Добавить два уникальных индекса для дедупликации:
    1. **Для организаций:** `CREATE UNIQUE INDEX idx_contacts_org_username ON contacts(org_id, telegram_username) WHERE org_id IS NOT NULL AND telegram_username IS NOT NULL`
    2. **Для личного:** `CREATE UNIQUE INDEX idx_contacts_personal_username ON contacts(user_id, telegram_username) WHERE org_id IS NULL AND telegram_username IS NOT NULL`
  - Это обеспечит "один username = один человек" как внутри сообщества, так и внутри личного профиля.

### 2. AI Service Extractor Update
- [ ] Обновить `app/services/ai_service.py`:
  - В методе `extract_contact_info()` обновить промпт (через `prompts.yaml`):
    - Добавить инструкцию: "Извлекай Telegram username (@username) из текста, если он упоминается"
  - В схеме `ContactExtracted` добавить поле `telegram_username: str | None`
  - Обновить `app/schemas.py` соответственно

### 3. Contact Creation Flow
- [ ] Обновить `app/services/search_service.py`:
  - В методе `create_contact()`:
    - Если `telegram_username` указан и `org_id` указан:
      - Проверять существование контакта с таким `(org_id, telegram_username)`
      - Если найден → возвращать `ContactUpdateAsk` вместо создания нового
    - Обрабатывать `IntegrityError` (unique constraint violation):
      - Ловить исключение при вставке
      - Искать существующий контакт
      - Возвращать `ContactUpdateAsk` с данными существующего контакта

### 4. UX Flow
- [ ] При обнаружении дубликата:
  - Бот показывает: "Такой контакт уже есть в базе: [Имя] — [Summary]"
  - Предлагает: "Обновить его? (Да/Нет)"
  - Если "Да" → вызывать `update_contact()` вместо `create_contact()`

## Acceptance Criteria
- [ ] В таблицу `contacts` добавлено поле `telegram_username` (text, nullable)
- [ ] Добавлен уникальный индекс `UNIQUE (org_id, telegram_username)` (только для org-контактов)
- [ ] При создании контакта бот пытается извлечь `@username` из текста (через LLM extractor)
- [ ] Если при вставке возникает ошибка уникальности — бот предлагает пользователю: "Такой контакт уже есть. Обновить его?"

## Files to Change
- `migrations/migration_epic2_search.sql` (alter table)
- `app/services/ai_service.py` (обновить промпт экстрактора)
- `app/schemas.py` (добавить поле в `ContactExtracted` и `ContactCreate`)
- `app/services/search_service.py` (обработка ошибки IntegrityError и возврат `ContactUpdateAsk`)

## Definition of Done
- [ ] Миграция применена, индекс создан
- [ ] Тест: Попытка создать контакт с тем же `@username` в той же орге → предложение обновить
- [ ] Тест: Личные контакты (`org_id = NULL`) могут иметь дубликаты по username
- [ ] LLM корректно извлекает `@username` из текста

**Estimated:** 2 часа
