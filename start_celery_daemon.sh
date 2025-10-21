#!/bin/bash

# Скрипт для запуска Celery воркера как демона (в фоновом режиме)

echo "Запуск Celery воркера как демона..."

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

# Останавливаем предыдущий воркер если есть
if [ -f /var/run/celery_worker.pid ]; then
    OLD_PID=$(cat /var/run/celery_worker.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        echo "Останавливаем предыдущий воркер (PID: $OLD_PID)..."
        kill $OLD_PID
        sleep 2
    fi
    rm -f /var/run/celery_worker.pid
fi

# Запускаем Celery воркер в фоновом режиме с nohup
echo "Запускаем новый воркер..."
nohup celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4 > /var/log/celery/worker.log 2>&1 &

# Сохраняем PID
WORKER_PID=$!
echo $WORKER_PID > /var/run/celery_worker.pid

echo "Celery воркер запущен как демон"
echo "PID: $WORKER_PID"
echo "Логи: /var/log/celery/worker.log"
echo "PID файл: /var/run/celery_worker.pid"
echo ""
echo "Команды для управления:"
echo "  Просмотр логов: tail -f /var/log/celery/worker.log"
echo "  Остановка: kill $WORKER_PID"
echo "  Или: ./stop_celery_worker.sh"
echo "  Перезапуск: ./start_celery_daemon.sh"
