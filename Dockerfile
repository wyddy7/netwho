FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей (ffmpeg для голосовых)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаем папку для временных файлов (аудио)
RUN mkdir -p temp_voice

# Запуск
CMD ["python", "app/main.py"]

