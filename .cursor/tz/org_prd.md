PRD: NetWho 2.0 (B2B Multi-Tenant Core) — Final & Secure
1. Executive Summary
Превращение NetWho из Personal CRM в B2B-платформу.
Суть: Переход на Shared Database. Пользователь видит личные контакты (org_id=NULL) и контакты организаций (org_id=UUID), в которых он состоит.

2. Architecture & Security Model
Database: Используем существующую схему БД (см. скриншот). RLS — резервная защита.

App Logic (Repository Pattern): Вся работа с БД идет через репозитории.

Security Principle: "Never Trust Input". Если юзер (или UI) просит сохранить в организацию, бэкенд обязан проверить, имеет ли юзер на это право, прежде чем писать в базу.

3. Database Schema (Source of Truth)
Базируется на твоем скриншоте.

SQL Init (Выполнить в Supabase SQL Editor)
Это нужно выполнить один раз, чтобы гарантировать работу поиска и индексов.

sql
-- 1. Гарантируем индексы (Критично для скорости)
CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(org_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id);

-- 2. Функция Гибридного Поиска (RPC)
-- Используем org_id (как на скриншоте)
CREATE OR REPLACE FUNCTION search_hybrid(
  p_user_id BIGINT, 
  p_query TEXT
) 
RETURNS TABLE (
    id UUID,
    name TEXT,
    summary TEXT,
    meta JSONB,
    org_id UUID,
    org_name TEXT
) 
LANGUAGE sql 
AS $$
  SELECT 
    c.id, c.name, c.summary, c.meta, c.org_id, o.name as org_name
  FROM contacts c
  LEFT JOIN organization_members om ON c.org_id = om.org_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      -- Личное: (Мой ID + Нет Организации)
      (c.user_id = p_user_id AND c.org_id IS NULL)
      OR
      -- Общее: (Я есть в таблице участников этой орги)
      (om.user_id = p_user_id)
    )
    AND 
    -- Поиск по тексту
    (c.name ILIKE '%' || p_query || '%' OR c.summary ILIKE '%' || p_query || '%')
  LIMIT 20;
$$;
4. Implementation Roadmap (Stories)
Story 1: Foundation (Hygiene)
Ветка: feature/fix-foundation
Статус: 🛑 БЛОКЕР. Не начинай Story 2, пока не сделаешь это.

Fix Encoding: Открой prompts.yaml, schema.sql и все .py файлы. Пересохрани в UTF-8.

Критерий успеха: Бот запускается локально без ошибок cp1251.

DB Check: Выполни SQL код из Раздела 3 в Supabase.

Story 2: Repository Layer (Secure Core)
Ветка: feature/repo-layer
Цель: Реализовать "умный" доступ к данным с валидацией прав.

Создай app/repositories/contact_repo.py.

Реализуй метод create строго по этому образцу:

python
# app/repositories/contact_repo.py
from loguru import logger

class ContactRepository:
    def __init__(self, supabase):
        self.db = supabase

    async def create(self, user_id: int, contact_data: dict, org_id: str = None):
        """
        Создает контакт. Если передан org_id, ПРОВЕРЯЕТ права доступа.
        """
        # --- SECURITY CHECK START ---
        if org_id:
            # 1. Проверяем, реально ли юзер состоит в этой организации
            # Таблица называется organization_members, поля user_id и org_id
            response = self.db.table('organization_members')\
                .select('user_id')\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            
            is_member = len(response.data) > 0
            
            if not is_member:
                # Юзер пытается хакнуть или баг в UI — сбрасываем на личный
                logger.warning(f"SECURITY ALERT: User {user_id} tried to write to forbidden org {org_id}. Fallback to personal.")
                org_id = None 
        # --- SECURITY CHECK END ---
                
        # Форсируем данные (не доверяем входному словарю целиком)
        contact_data['org_id'] = org_id
        contact_data['user_id'] = user_id 
        
        return self.db.table('contacts').insert(contact_data).execute()

    async def get_user_orgs(self, user_id: int):
        res = self.db.table('organization_members').select('org_id').eq('user_id', user_id).execute()
        return [row['org_id'] for row in res.data]
Обнови сервисы (text.py и др.), заменив supabase.table на repo.create.

Story 3: Hybrid Search Implementation
Ветка: feature/hybrid-search

В ContactRepository добавь метод:

python
async def search(self, user_id: int, query: str):
    return self.db.rpc('search_hybrid', {'p_user_id': user_id, 'p_query': query}).execute()
Обнови search_service.py.

Story 4: UI & Scope Selection
Ветка: feature/ui-scope

Logic:

orgs = repo.get_user_orgs(user_id)

if not orgs: Молча сохраняем (Personal).

if orgs: Показываем Inline-кнопки [🔒 Личное], [📢 Python Heroes].

Action: При нажатии кнопки вызываем repo.create(..., org_id=callback_data).

Story 5: Admin Tools
Ветка: feature/admin-tools

Команда /create_org "Name" для создания сообществ (через SQL insert или Repo).

5. Definition of Done
 UTF-8: Все файлы сохранены в UTF-8.

 Security: Попытка сохранить контакт в чужую организацию (через подмену кода) приводит к сохранению в личные и варнингу в логах.

 Search: Поиск находит контакты и из NULL (личные), и из UUID (общие).

 Git: Ветки вливаются в master последовательно. dev ветка уничтожена.