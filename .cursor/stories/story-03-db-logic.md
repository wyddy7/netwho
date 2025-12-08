# Epic 3: Сервис поиска и управления контактами

**Цель:** Связать Python-код с Supabase для CRUD операций и векторного поиска.

## Шаг 3.1: CRUD Контактов
- [ ] Создать `app/services/search_service.py`.
- [ ] Реализовать метод `create_contact(user_id, data: ContactCreate, embedding)`.
  - [ ] Insert в таблицу `contacts`.
- [ ] Реализовать метод `get_contact_by_id(contact_id, user_id)`.
- [ ] Реализовать метод `delete_contact(contact_id, user_id)`.
  - [ ] Проверка `user_id` (защита от удаления чужих данных, хотя RLS это тоже держит).

## Шаг 3.2: Векторный поиск
- [ ] В `app/services/search_service.py` реализовать метод `search(query: str, user_id: int)`.
  - [ ] Генерация эмбеддинга запроса.
  - [ ] Вызов RPC функции `match_contacts`.
  - [ ] Фильтрация по порогу схожести (threshold 0.4 - вынести в конфиг или дефолт).

## Шаг 3.3: Управление пользователями
- [ ] Создать `app/services/user_service.py`.
- [ ] Реализовать `upsert_user(telegram_user)`.
- [ ] Реализовать `delete_user_data(user_id)` (для GDPR/Delete Me).

**Критерий готовности:**
- Можно программно создать контакт, найти его через векторный поиск ("найди рыбаков") и удалить по ID.

