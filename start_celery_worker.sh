#!/bin/bash

# Скрипт для запуска Celery воркера с нужными переменными окружения

echo "Запуск Celery воркера..."

# Переходим в директорию проекта
cd /var/www/vashsender

# Активируем виртуальное окружение
source venv/bin/activate

# Экспортируем переменные окружения
export POSTGRES_DB=vashsender
export POSTGRES_USER=vashsender
export POSTGRES_PASSWORD='34t89O7i@'
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_CONN_MAX_AGE=600
export POSTGRES_SSLMODE=prefer
export REDIS_URL=redis://localhost:6379/0

echo "Переменные окружения установлены:"
echo "POSTGRES_DB: $POSTGRES_DB"
echo "POSTGRES_USER: $POSTGRES_USER"
echo "POSTGRES_HOST: $POSTGRES_HOST"
echo "POSTGRES_PORT: $POSTGRES_PORT"
echo "REDIS_URL: $REDIS_URL"
echo ""

# Запускаем Celery воркер
echo "Запускаем Celery воркер..."
celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4
