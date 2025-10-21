#!/bin/bash

# Простой скрипт для запуска Celery воркера с нужными переменными окружения
# Используйте этот скрипт для запуска воркера в фоновом режиме

export POSTGRES_DB=vashsender
export POSTGRES_USER=vashsender
export POSTGRES_PASSWORD='34t89O7i@'
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_CONN_MAX_AGE=600
export POSTGRES_SSLMODE=prefer
export REDIS_URL=redis://localhost:6379/0

cd /var/www/vashsender

# Запуск воркера в фоновом режиме с nohup
nohup /var/www/vashsender/venv/bin/celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4 > /var/log/celery/worker.log 2>&1 &

echo "Celery worker запущен в фоновом режиме"
echo "PID процесса: $!"
echo "Логи: /var/log/celery/worker.log"
echo "Для остановки: kill $!"
