FROM python:3.11-slim

WORKDIR /app

# Сначала зависимости — так Docker кэширует слой и не переустанавливает их на каждый коммит
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Потом остальной код
COPY . .

EXPOSE 8000

# Применяем миграции при старте, затем запускаем сервер
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
