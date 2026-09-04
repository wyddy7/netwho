# NetWho Bot

**AI-ассистент для нетворкинга.** Умная записная книжка, напоминания (Recall system) и генерация интро.
📢 [Telegram Community](https://t.me/netwho) 

## 🛠 Стек
*   **Python 3.13+** (Docker uses `python:3.13-slim`)
*   **Aiogram 3.x** (Telegram Bot API)
*   **Supabase** (PostgreSQL + Auth)
*   **OpenRouter / OpenAI** (LLM inference)
*   **Groq** (Voice transcription)
*   **APScheduler** (Background tasks)
*   **uv** (Package manager)

## 🚀 Запуск

### Docker (Продакшен)

1.  **Создайте `.env`** (на основе `.env.example`):
    ```bash
    cp .env.example .env
    ```
 
2.  **Запустите контейнер**:
    ```bash
    docker compose up -d --build
    ```

3.  **Просмотр логов**:
    ```bash
    docker compose logs -f bot
    ```

### Локальный запуск (Разработка)

1.  **Установите `uv`** (если еще не установлен):
    ```bash
    # Windows (PowerShell)
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    
    # Linux/Mac
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Установите зависимости**:
    ```bash
    uv sync
    ```

3.  **Запустите бота**:
    ```bash
    uv run python -m app.main
    ```

## ⚙️ Конфигурация (.env)

Основные переменные для продакшена.

| Переменная | Обязательно | Описание |
| :--- | :---: | :--- |
| `BOT_TOKEN` | ✅ | Токен от [@BotFather](https://t.me/BotFather) |
| `SUPABASE_URL` | ✅ | URL проекта Supabase |
| `SUPABASE_KEY` | ⚠️ | Устаревший, используй `SUPABASE_SERVICE_ROLE_KEY` |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | **Service Role** ключ (обходит RLS, для доступа к БД) |
| `OPENROUTER_API_KEY` | ✅ | Ключ OpenRouter (или OpenAI) |
| `ADMIN_ID` | ✅ | Telegram ID владельца (для админ-команд) |
| `LOG_LEVEL` | ❌ | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR` (дефолт: `INFO`) |
| `GROQ_API_KEY` | ❌ | Для распознавания ГС (если не задан — войсы игнорируются) |
| `LLM_MODEL` | ❌ | Дефолт: `openai/gpt-4o-mini` |
| `PROXY_URL` | ❌ | Proxy for the LLM client; may contain credentials and is never logged |
| `HTTPS_PROXY` / `HTTP_PROXY` | ❌ | Proxy fallback used by the Telegram session |

## 📦 База данных и Миграции

Проект использует **Supabase** (PostgreSQL).
*   SQL-миграции находятся в папке `/migrations`.
*   **Применение**: Вручную через Supabase Dashboard (SQL Editor) или psql. Автоматического наката миграций при старте нет.

## 🔧 Администрирование

**Админ-команды** (доступны `ADMIN_ID`):
*   `/admin` — Список всех команд.
*   `/check_user <user_id>` — Проверить статус подписки, триала и лимитов пользователя.
*   `/give_pro <user_id> <days>` — Выдать Premium на N дней.
*   `/revoke_pro <user_id>` — Аннулировать подписку.
*   `/debug_user <user_id>` — Детальная отладочная информация о пользователе.

**Полезные скрипты** (в папке `/scripts`):
*   `uv run python scripts/check_db.py` — Проверка подключения к БД.
*   `uv run python scripts/test_db.py` — Прямой тест Supabase (проверка контактов, RLS).
*   `uv run python scripts/revoke_trial.py` — Массовый отзыв триалов (если нужно).
*   `uv run python scripts/test_ai.py` — Тест LLM коннектора.

## Active Recall scheduler

The scheduler runs every 15 minutes. It uses the subscription fields already
loaded by the batch user query, so it does not issue a per-user `is_pro()`
lookup. Scheduler policy, production verification, and the before/after DB-call
count are documented in [`docs/recall-scheduler.md`](docs/recall-scheduler.md).

## Status

📄 Production runtime and deployment details are maintained in the parent
monorepo's `auto-docs/projects/netwho/server.md`. The public repository keeps
runtime code, tests, and architecture-level behavior; secrets and host
coordinates are never stored here.
