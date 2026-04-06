# NetWho Product Roadmap

## 🌟 Vision
NetWho — это не просто записная книжка, это **активный агент**, который управляет твоим социальным капиталом. Он помнит контекст, подсказывает поводы для общения и помогает формировать команды.

---

## 🚀 Completed
- **Epic 1-5 (Core):**
  - Telegram Bot Setup
  - Voice & Text Input
  - Vector Search & Semantic Memory
  - LLM Integration (OpenAI/Groq)
  - CRUD Operations (Add, Delete, Update)
  - User Settings & Confirmation Flow
 
--- 
 
## 🚧 Current Phase: Epic 6 (MVP Polish)
*Цель: Подготовить бота к реальному использованию и деплою.*

1.  **Deployment Pack:**
    - `Dockerfile` & `docker-compose.yml`.
    - Production configurations.
2.  **Privacy & Control:**
    - `/delete_me` — полное удаление данных пользователя (GDPR compliance).
3.  **Active Recall (V1):**
    - Еженедельный "случайный контакт".
    - Простая механика: "Ты давно не общался с X. Вот что мы о нем знаем."

---

## 🔮 Future Plans

### 🧠 Epic 7: Social Intelligence (The "Alive" Bot)
*Цель: Превратить бота из "архива" в "помощника".*

1.  **Smart Active Recall:**
    - Вместо рандома — приоритезация тех, с кем давно не было контакта (поле `last_interaction`).
    - Умные поводы: "Кажется, вы хотели обсудить проект в следующем месяце".
2.  **Birthday & Gift Detector:**
    - Фоновый процесс: LLM сканирует заметки на предмет дат (ДР, годовщины).
    - За неделю до события: "У Светы ДР. Ты писал, что она любит сноуборд. Подари скипасс."
3.  **Team Builder Mode:**
    - Специальный промпт для запросов типа "Собери команду под крипто-биржу".
    - Выдача: Структурированный список ролей (CEO, CTO, Investor) с кандидатами из базы.

### 🌐 Epic 8: Scaling & Multi-user
*Цель: Масштабирование сервиса.*

1.  **Web Dashboard:** (Optional) Админка для просмотра графа связей.
2.  **LinkedIn/Telegram Import:** Импорт контактов из экспортов.
3.  **Monetization:** Лимиты на количество контактов/запросов для Free tier.

### 🛠 Tech Debt & Improvements
- **Migrations:** Alembic setup (currently using raw SQL).
- **Tests:** Unit tests for services.
- **Observability:** Sentry integration.
