# Story 24: Hard-Scoped Retrieval (Fix Critical Bug)

**Epic:** Epic 2 - Search Intelligence (Умный Поиск)
**Parent:** .cursor/tz/epic 2 search ai.md
**Branch:** `feature/epic2-hard-scoped-retrieval`
**Prerequisites:** Story 19 (True Hybrid Search)

## Context
Переносим фильтрацию по организации внутрь SQL-запроса (RPC), чтобы векторный поиск искал *среди своих*, а не *среди всех*. Это исправит проблему "пустой выдачи", когда нужные контакты не попадают в топ-K из-за глобального ранжирования.

## Technical Tasks

### 1. Database Migration
- [ ] Создать `migrations/migration_epic2_search.sql`
- [ ] Обновить RPC функцию `match_contacts`:
  - Добавить параметр `filter_org_ids UUID[] DEFAULT NULL`
  - В WHERE условии добавить логику Union Search:
    - `(contacts.org_id = ANY(filter_org_ids) OR (contacts.org_id IS NULL AND contacts.user_id = match_user_id))`
  - Это позволит искать одновременно в личных контактах и в выбранных организациях, не ломая обычный поиск.

### 2. Repository Layer
- [ ] Обновить `app/repositories/contact_repo.py` (или вызвать через `org_repo`):
  - Метод `search()` принимает список `org_ids: list[str] | None`
  - При вызове RPC `match_contacts` передавать массив UUID.

### 3. Search Service Update
- [ ] Обновить `app/services/search_service.py`:
  - В методе `search()` формировать список `filter_org_ids`:
    - Если в запросе `org:skop` → список из одного UUID этой орги.
    - Если обычный запрос → список из ВСЕХ UUID организаций пользователя.
  - Передавать этот список в RPC.

## Acceptance Criteria
- [ ] SQL-функция `match_contacts` (или `search_hybrid`) принимает параметр `filter_org_id` (UUID)
- [ ] Внутри SQL запроса условие `WHERE org_id = filter_org_id` применяется **до** сортировки по `embedding <=> query`
- [ ] Python-код вызывает обновленную RPC функцию, передавая туда ID текущей орги (если есть)
- [ ] Тест: поиск редкого слова, которое есть только в этой орге (но далеко по релевантности в глобальном скоупе), возвращает результат

## Files to Change
- `migrations/migration_epic2_search.sql` (обновление функции)
- `app/repositories/contact_repo.py` (вызов новой RPC)
- `app/services/search_service.py` (передача org_id в repo)

## Definition of Done
- [ ] Миграция применена, функция обновлена
- [ ] Тест: поиск "кто в skop" находит контакты из Skop орги, даже если они не в топ-10 глобально
- [ ] Тест: личный поиск (без org_id) работает как раньше
- [ ] Логи показывают, что фильтрация происходит в SQL, а не в Python

**Estimated:** 2 часа
