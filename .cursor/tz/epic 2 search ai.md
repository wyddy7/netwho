 Epic 2: Search Intelligence (Умный Поиск)
Цель: Поиск перестает врать и показывать пустоту там, где есть люди.
Story 2.1: Hard-Scoped Retrieval (Fix Critical Bug)
DB: Обновить RPC match_contacts: добавить параметр filter_org_id.
Code: Передать org_id прямо в SQL запрос WHERE, до векторного сравнения.
Story 2.2: Intent Detection (List vs Search)
Router: Если запрос "кто в skop", "список участников" -> НЕ идти в вектор/реранкер.
Logic: Выполнять чистый SQL SELECT * FROM contacts WHERE org_id=... (сортировка по новизне).
Story 2.3: Simple Deduplication (Canonical MVP)
DB: Добавить telegram_username в contacts.
Constraint: Добавить уникальный индекс UNIQUE(org_id, telegram_username).
UX: При попытке добавить дубль -> предлагать "Обновить существующий".