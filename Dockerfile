FROM python:3.11-slim

# 1. Получаем бинарник uv из официального образа
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 2. Установка системных зависимостей (ffmpeg для голосовых)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 3. Сначала копируем только файлы зависимостей!
# Это позволяет Docker'у закэшировать слой с установленными пакетами.
# Если ты поменяешь код бота, но не зависимости, этот шаг (и скачивание пакетов) пропустится.
COPY pyproject.toml uv.lock ./

# 4. Устанавливаем зависимости
# --frozen: строго следовать uv.lock (не обновлять версии самовольно)
RUN uv sync --frozen

# 5. Теперь копируем весь остальной код
COPY . .

# 6. Создаем папку для временных файлов
RUN mkdir -p temp_voice

# 7. Запускаем через uv run
# Он сам подхватит виртуальное окружение, которое создал uv sync
CMD ["uv", "run", "app/main.py"]
