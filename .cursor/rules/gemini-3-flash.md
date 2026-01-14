# Safe Flash Workflow (для быстрых задач)

## Core Principles
1. **Minimal Diff**: меняй ТОЛЬКО то, что указано в story. Не рефактори соседний код.
2. **Explicit Testing**: после каждого изменения покажи, как проверить (команда/запрос/лог).
3. **No Hallucinations**: если файл/функция/поле не существует — спроси, не придумывай.
4. **Security First**: любой user input → валидация. Любой SQL → параметризация.

## Code Generation Rules
- Break down task into 3-5 atomic steps (one file/function per step)
- Show diff before full implementation: "I will change X in file Y, line Z"
- Use `// ... existing code ...` to skip unchanged blocks (never repeat full file)
- Add inline comments ONLY for non-obvious logic (security checks, edge cases)
- Include error handling for every DB/API call

## Response Format
For each step, provide:
1. **What**: одно предложение (например: "Add `status` field to org_members")
2. **Where**: путь к файлу + строка/функция
3. **Diff**: только изменяемые строки с контекстом ±2 строки
4. **Test**: команда для проверки (SQL query, curl, pytest)

## Example Output
Step 1: Add migration field
File: migrations/migration_epic1.sql
Change: Add status column with constraint

sql
-- ... existing migration code ...
ALTER TABLE organization_members ADD COLUMN status TEXT DEFAULT 'pending';
ALTER TABLE organization_members ADD CONSTRAINT check_status CHECK (status IN ('pending', 'approved', 'banned'));
-- ... existing migration code ...
Test: psql -f migrations/migration_epic1.sql должен выполниться без ошибок

text

## Forbidden Actions (Flash mode)
❌ Не трогать файлы вне списка "Files to Change" в story
❌ Не удалять существующий код без явного указания
❌ Не менять схему БД без миграции
❌ Не хардкодить UUID/токены/пароли
❌ Не делать "улучшения", которых не просили
❌ Не использовать поля БД (is_archived, created_at), если они не указаны в story


## When to Stop and Ask
- Если функция/таблица не найдена в кодовой базе
- Если изменение затрагивает >3 файлов
- Если непонятно, где хранится конфиг/промпт/env
- Если тест требует моков, которых нет