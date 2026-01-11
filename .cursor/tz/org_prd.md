PRD: NetWho 2.0 (B2B Multi-Tenant Core)
1. Executive Summary
Превращение NetWho из Personal CRM в B2B-платформу для сообществ.
Ключевое изменение: Данные теперь живут в контексте "Организаций" (Organizations). Пользователь может владеть личными контактами и иметь доступ к общим контактам организаций, в которых он состоит.

2. Architecture & Security Model
Мы отказываемся от идеи "RLS через HTTP-заголовки" (слишком сложно для aiogram) в пользу Repository Pattern с принудительной фильтрацией.

Database: PostgreSQL (Supabase) — хранит данные, связи и RLS (как последний рубеж защиты).

Application (Bot): Использует SERVICE_ROLE_KEY для подключения, но ВСЯ работа с данными идет через строго типизированные репозитории, которые физически не могут сделать запрос без user_id.

3. Database Schema (Source of Truth)
Тебе нужно выполнить этот SQL в SQL Editor Supabase. Это фундамент.

sql
-- 1. Организации (Сообщества)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    invite_code TEXT UNIQUE, -- Код для вступления, например 'python-heroes-2025'
    created_at TIMESTAMPTZ DEFAULT now(),
    owner_id BIGINT REFERENCES users(id) -- Создатель сообщества
);

-- 2. Участники (Связь Many-to-Many)
CREATE TABLE organization_members (
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member', -- 'admin', 'member'
    joined_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (organization_id, user_id)
);

-- 3. Модификация Контактов (Добавляем владельца-организацию)
ALTER TABLE contacts 
ADD COLUMN organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL;

-- Индекс для скорости (иначе поиск по 50k будет тормозить)
CREATE INDEX idx_contacts_org ON contacts(organization_id);
CREATE INDEX idx_org_members_user ON organization_members(user_id);
4. Technical Implementation Steps (Пошагово)
Шаг 0: Санитария (Критично)
Fix Encoding: Открой prompts.yaml в VS Code, нажми внизу справа Windows-1251 -> Save with Encoding -> UTF-8. Сохрани. Без этого бот не взлетит.

Шаг 1: Слой Доступа к Данным (The Repository Pattern)
Мы перестаем писать supabase.table('contacts').select(...) прямо в хендлерах. Это путь к утечкам.
Создай файл app/repositories/contact_repo.py.

python
# Pseudo-code логики
class ContactRepository:
    def __init__(self, supabase):
        self.db = supabase

    async def get_user_scope(self, user_id: int):
        """Возвращает ID всех организаций, где юзер - участник"""
        response = self.db.table('organization_members')\
            .select('organization_id')\
            .eq('user_id', user_id).execute()
        return [row['organization_id'] for row in response.data]

    async def search(self, user_id: int, query: str):
        """
        БЕЗОПАСНЫЙ ПОИСК.
        Ищет ТОЛЬКО в:
        1. Личных контактах (organization_id IS NULL AND user_id = user_id)
        2. Организациях участника (organization_id IN user_orgs)
        """
        user_orgs = await self.get_user_scope(user_id)
        
        # Формируем фильтр: (личные) ИЛИ (общие)
        # В PostgREST синтаксисе это сложно, поэтому используем RPC или OR-фильтр
        # Проще всего: Фильтр OR
        or_filter = f"and(user_id.eq.{user_id},organization_id.is.null),organization_id.in.({','.join(user_orgs)})"
        
        return self.db.table('contacts').select('*').or_(or_filter).ilike('name', f'%{query}%').execute()
Шаг 2: Создание Организации (Admin Tool)
Ты не будешь пилить UI создания организации для всех. Сделай это для себя (Admin Only).
В handlers/admin.py:

python
@router.message(Command("create_org"))
async def create_org(message: Message):
    # /create_org "Python Heroes"
    name = message.text.split('"')[1]
    # INSERT into organizations...
    # INSERT into organization_members (me)...
    await message.reply(f"Org '{name}' created! Invite code: {uuid}")
Шаг 3: Миграция create_contact
Когда юзер создает контакт (Voice/Text):

Бот проверяет: repo.get_user_scope(user_id).

Если список пуст -> Сохраняем как личный (как раньше).

Если есть организации -> Показываем Inline-клавиатуру:

[🔒 Личное]

[📢 Python Heroes]

При нажатии сохраняем с нужным organization_id.

5. Best Practices Checklist (Как в Бауманке)
Data Integrity:

Всегда используй UUID для ID организаций.

Используй ON DELETE CASCADE для связей мемберов. Если удаляется организация — удаляются права доступа, но не юзеры.

Security Layer:

Никогда не доверяй organization_id, пришедшему от юзера в callback_data.

Перед сохранением в организацию X всегда проверяй: "А юзер вообще мембер этой организации X?". (Метод repo.is_member(user_id, org_id)).

Performance:

Поиск будет нагруженным. Создай SQL-функцию (RPC) search_contacts_hybrid в Supabase, чтобы сложная логика "OR" выполнялась внутри базы, а не генерировалась в Python. Это быстрее и безопаснее.

SQL RPC для Поиска (The Pro Move)
Выполни это в Supabase. Это заменит сложный Python-код поиска.

sql
CREATE OR REPLACE FUNCTION search_hybrid(
  p_user_id BIGINT, 
  p_query TEXT
) 
RETURNS SETOF contacts 
LANGUAGE sql 
AS $$
  SELECT c.*
  FROM contacts c
  LEFT JOIN organization_members om ON c.organization_id = om.organization_id
  WHERE 
    (
      -- Личные контакты
      (c.user_id = p_user_id AND c.organization_id IS NULL)
      OR
      -- Контакты организаций, где я участник
      (om.user_id = p_user_id)
    )
    AND 
    -- Сам поиск
    (c.name ILIKE '%' || p_query || '%' OR c.summary ILIKE '%' || p_query || '%')
  LIMIT 20;
$$;
Теперь в Python поиск выглядит так:

python
response = supabase.rpc('search_hybrid', {'p_user_id': 123, 'p_query': 'django'}).execute()
Это идеально. Безопасно, быстро, вся логика в базе.

Важный нюанс:
В SQL функции search_hybrid убедись, что ты правильно обрабатываешь дубликаты (один контакт может теоретически выпасть дважды, если логика кривая, но DISTINCT или правильный OR это решит). Тот код, что тебе дали — выглядит валидным.