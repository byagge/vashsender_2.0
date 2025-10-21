#!/bin/bash

# Скрипт для запуска Celery воркера в фоновом режиме

echo "Запуск Celery воркера в фоновом режиме..."

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

# Создаем директорию для логов
mkdir -p /var/log/celery

# Запускаем Celery воркер в фоновом режиме
nohup celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4 > /var/log/celery/worker.log 2>&1 &

# Сохраняем PID
echo $! > /var/run/celery_worker.pid

echo "Celery воркер запущен в фоновом режиме"
echo "PID: $(cat /var/run/celery_worker.pid)"
echo "Логи: /var/log/celery/worker.log"
echo ""
echo "Для остановки: kill \$(cat /var/run/celery_worker.pid)"
echo "Для просмотра логов: tail -f /var/log/celery/worker.log"
