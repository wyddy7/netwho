# Epic 2: Модели данных и AI Сервисы

**Цель:** Реализовать бизнес-логику работы с данными и интеграцию с LLM/STT, изолированно от Telegram бота.

## Шаг 2.1: Pydantic схемы (Domain Layer)
- [ ] Создать `app/schemas.py`.
- [ ] Описать модели данных, соответствующие таблицам БД и API контрактам:
  - [ ] `UserCreate`, `UserUpdate`.
  - [ ] `ContactCreate` (с полями для AI экстракции: name, summary, meta).
  - [ ] `ContactResponse` (с ID и score для поиска).

## Шаг 2.2: Аудио-сервис (Audio Service)
- [ ] Создать `app/services/audio_service.py`.
- [ ] Реализовать функцию конвертации OGG -> MP3.
  - [ ] Использовать `pydub` (требует установленного `ffmpeg` в системе/докере).
  - [ ] Реализовать очистку временных файлов после конвертации.

## Шаг 2.3: STT Интеграция (Whisper)
- [ ] Добавить метод транскрибации в `app/services/ai_service.py` (или `stt_service.py`).
- [ ] Реализовать запрос к Groq (Whisper-large-v3) или OpenAI Whisper.
- [ ] Обработать ошибки API.

## Шаг 2.4: LLM Клиент и Экстракция (AI Core)
- [ ] Настроить `AsyncOpenAI` клиент для OpenRouter в `app/services/ai_service.py`.
- [ ] Реализовать функцию `extract_contact_info(text: str) -> dict`.
  - [ ] Системный промпт из ТЗ (Раздел 4.1).
  - [ ] Настройка JSON Mode или Function Calling для строгого формата ответа.
  - [ ] Добавить Retry-логику через `tenacity` (backoff при 5xx ошибках).

## Шаг 2.5: Векторизация (Embeddings)
- [ ] Реализовать функцию `get_embedding(text: str) -> list[float]`.
- [ ] Использовать модель `text-embedding-3-small`.
- [ ] Проверить размерность вектора (должна быть 1536).

**Критерий готовности:**
- Есть скрипт-тест, который берет тестовый аудиофайл, транскрибирует его, извлекает JSON с контактом и генерирует вектор.

