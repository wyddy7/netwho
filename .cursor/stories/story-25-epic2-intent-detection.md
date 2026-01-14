# Story 25: Intent Detection for Lists (List vs Search)

**Epic:** Epic 2 - Search Intelligence (Умный Поиск)
**Parent:** .cursor/tz/epic 2 search ai.md
**Branch:** `feature/epic2-intent-detection`
**Prerequisites:** Story 24 (Hard-Scoped Retrieval)

## Context
Отключаем векторный поиск и реранкер для запросов вида "кто в skop", "список участников". ИИ тут часто ошибается, нужен детерминированный список. Это исправляет баг, когда реранкер выкидывает валидные результаты из-за отсутствия явного упоминания "skop" в описании контакта.

## Technical Tasks

### 1. Intent Detection Logic
- [ ] Добавить в `app/services/search_service.py` метод `_detect_list_intent(query: str) -> bool`:
  - Паттерны для распознавания:
    - "кто в [org]", "список [org]", "покажи всех в [org]"
    - "участники", "члены", "люди в"
    - Запросы вида `org:skop` без дополнительных слов (только название орги)
  - Возвращает `True` если это запрос на список

### 2. Search Service Branching
- [ ] Обновить метод `search()` в `app/services/search_service.py`:
  - Если `_detect_list_intent(query)` → выполнять чистый SQL запрос:
    ```sql
    SELECT * FROM contacts 
    WHERE org_id = :org_id 
    AND is_archived = false
    ORDER BY created_at DESC
    LIMIT :limit
    ```
  - Если НЕ list intent → идти в обычный гибридный поиск (SQL + Vector)

### 3. AI Service Update (Skip Reranker)
- [ ] Обновить `app/services/ai_service.py`:
  - Метод `rerank_contacts()` проверяет флаг `is_list_query: bool`
  - Если `is_list_query = True` → возвращать кандидатов без фильтрации
  - Или вообще не вызывать реранкер для list-запросов

### 4. Router Agent Instructions
- [ ] Обновить промпт в `app/prompts_loader.py` (или в коде):
  - Добавить инструкцию: "Если пользователь просит показать список участников организации, используй формат `org:название` без дополнительных слов"

## Acceptance Criteria
- [ ] Router (в `ai_service` или `search_service`) распознает интенты "list_members" / "show_all"
- [ ] Для таких запросов выполняется чистый SQL `SELECT * FROM contacts WHERE org_id = X ORDER BY created_at DESC`
- [ ] Реранкер (LLM filtering) для таких запросов **отключен** или получает инструкцию "не фильтровать, показать всё"

## Files to Change
- `app/services/search_service.py` (логика ветвления search vs list)
- `app/services/ai_service.py` (инструкции для router agent или пропуск rerank)

## Definition of Done
- [ ] Тест: "кто в skop" возвращает всех участников без фильтрации реранкером
- [ ] Тест: "найди python dev в skop" идет в обычный гибридный поиск
- [ ] Тест: Реранкер не вызывается для list-запросов (логи)
- [ ] Результаты детерминированы (одинаковый запрос = одинаковый результат)

**Estimated:** 1.5 часа
