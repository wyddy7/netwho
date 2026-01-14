# Story 20: Schema & Access Control

**Epic:** Epic 1 - The Gate (Вход и Контроль)
**Parent:** .cursor/tz/epic 1 The Gate.md
**Branch:** `feature/epic1-schema-access`
**Prerequisites:** None (Foundation story)

## Context
Создаем фундамент для управления доступом: статусы участников в организациях и счетчик бесплатных действий для "Give-to-Get" модели. На уровне middleware запрещаем `pending` пользователям писать в базу.

## Technical Tasks

### 1. Database Migration
- [ ] Создать `migrations/migration_epic1_gate.sql`
- [ ] Добавить поле `status` в таблицу `organization_members`:
  - Тип: `TEXT` с CHECK constraint (`'pending'`, `'approved'`, `'banned'`)
  - Default: `'pending'`
  - Индекс для быстрого поиска по статусу
- [ ] Добавить поле `free_searches_used` в таблицу `organization_members`:
  - Тип: `INTEGER`
  - Default: `0`
- [ ] Обновить существующие записи: установить `status = 'approved'` для всех текущих участников

### 2. Repository Layer
- [ ] Обновить `app/repositories/contact_repo.py`:
  - Метод `create()` проверяет статус пользователя через `organization_members`
  - Если `status = 'pending'` и `org_id` указан → выбрасывать `AccessDenied` или возвращать ошибку

### 3. Service Layer
- [ ] Обновить `app/services/search_service.py`:
  - Метод `create_contact()` проверяет статус перед записью
  - Если статус `pending` → возвращать понятную ошибку пользователю

## Acceptance Criteria
- [ ] В таблице `organization_members` есть поле `status` (enum: 'pending', 'approved', 'banned', default: 'pending')
- [ ] В таблице `organization_members` есть поле `free_searches_used` (int, default: 0)
- [ ] Миграция успешно накатывается на существующую базу
- [ ] Middleware (или декоратор) проверяет статус пользователя перед выполнением `create_contact` / `update_contact`
- [ ] Если статус `pending` и пользователь пытается создать контакт — бот отвечает "Дождитесь подтверждения участия"

## Files to Change
- `migrations/migration_epic1_gate.sql` (создать новую)
- `app/repositories/contact_repo.py` (учет статуса при проверке прав)
- `app/services/search_service.py` (проверка статуса перед записью)

## Definition of Done
- [x] Миграция применена в dev окружении
- [x] Тест: `pending` пользователь не может создать контакт в орге
- [x] Тест: `approved` пользователь может создавать контакты
- [x] Логи показывают корректную проверку статуса

**Completed:** 2026-01-15
