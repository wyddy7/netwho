# Story 23: "Give-to-Get" Limit Logic

**Epic:** Epic 1 - The Gate (Вход и Контроль)
**Parent:** .cursor/tz/epic 1 The Gate.md
**Branch:** `feature/epic1-give-to-get`
**Prerequisites:** Story 20 (Schema & Access Control), Story 21 (Deep Link)

## Context
Реализуем экономику: даем 3 поиска бесплатно, потом требуем вклад (или апрув). Это защита от паразитизма и стимул для участия в сообществе.

## Technical Tasks

### 1. Search Service Update
- [ ] Обновить `app/services/search_service.py`:
  - В методе `search()` перед выполнением поиска проверять:
    - Если запрос в контексте орги (`org_id` указан)
    - И статус пользователя = `pending`
    - И `free_searches_used >= 3`
    - → Блокировать поиск, возвращать сообщение с CTA

### 2. Counter Increment
- [ ] При каждом успешном поиске в контексте орги:
  - Инкрементировать счетчик ТОЛЬКО если `status = 'pending'` и поиск привязан к конкретной `org_id`.
  - Обновить через `UPDATE organization_members SET free_searches_used = free_searches_used + 1 WHERE user_id = :user_id AND org_id = :org_id AND status = 'pending'`

### 3. User Service Helper
- [ ] Добавить в `app/services/user_service.py`:
  - `increment_free_searches(user_id: int, org_id: str) -> int`:
    - Инкрементирует счетчик
    - Возвращает новое значение
  - `check_search_limit(user_id: int, org_id: str) -> tuple[bool, str]`:
    - Проверяет лимит
    - Возвращает `(allowed: bool, message: str)`

### 4. UX Message
- [ ] Сообщение при блокировке:
  - "Лимит демо-поисков исчерпан (3/3)."
  - "Чтобы продолжить, администратор должен подтвердить твою заявку."
  - "Или добавь свой контакт в базу, чтобы ускорить процесс."

## Acceptance Criteria
- [ ] При каждом поиске в контексте орги увеличивается счетчик `free_searches_used`
- [ ] Если `status=pending` и `free_searches_used >= 3`: поиск блокируется
- [ ] Бот выдает сообщение: "Лимит демо-поисков исчерпан. Чтобы продолжить, админ должен подтвердить твою заявку (или добавь свой контакт, чтобы ускорить процесс)"
- [ ] Для `approved` пользователей лимит не действует

## Files to Change
- `app/services/search_service.py` (проверка лимитов перед поиском)
- `app/services/user_service.py` (методы для работы со счетчиком)
- `app/repositories/contact_repo.py` (обновление счетчика в БД)

## Definition of Done
- [ ] Тест: Первые 3 поиска работают для `pending` пользователя
- [ ] Тест: 4-й поиск блокируется с правильным сообщением
- [ ] Тест: `approved` пользователь не ограничен лимитом
- [ ] Счетчик корректно инкрементируется в БД

**Estimated:** 1.5 часа
