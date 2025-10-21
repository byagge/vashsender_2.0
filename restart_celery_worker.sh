#!/bin/bash

# Скрипт для перезапуска Celery воркера

echo "Перезапуск Celery воркера..."

# Останавливаем текущий воркер
if [ -f ./stop_celery_worker.sh ]; then
    ./stop_celery_worker.sh
else
    echo "Останавливаем воркер вручную..."
    
    # Ищем процессы celery
    CELERY_PIDS=$(pgrep -f "celery.*worker")
    if [ -n "$CELERY_PIDS" ]; then
        echo "Найдены процессы celery: $CELERY_PIDS"
        kill $CELERY_PIDS
        sleep 3
        
        # Принудительно завершаем если нужно
        CELERY_PIDS=$(pgrep -f "celery.*worker")
        if [ -n "$CELERY_PIDS" ]; then
            echo "Принудительно завершаем..."
            kill -9 $CELERY_PIDS
        fi
    fi
    
    # Удаляем PID файл
    rm -f /var/run/celery_worker.pid
fi

echo "Ждем 2 секунды..."
sleep 2

# Запускаем новый воркер
if [ -f ./start_celery_daemon.sh ]; then
    ./start_celery_daemon.sh
else
    echo "Запускаем воркер вручную..."
    
    cd /var/www/vashsender
    source venv/bin/activate
    
    export POSTGRES_DB=vashsender
    export POSTGRES_USER=vashsender
    export POSTGRES_PASSWORD='34t89O7i@'
    export POSTGRES_HOST=127.0.0.1
    export POSTGRES_PORT=5432
    export POSTGRES_CONN_MAX_AGE=600
    export POSTGRES_SSLMODE=prefer
    export REDIS_URL=redis://localhost:6379/0
    
    mkdir -p /var/log/celery
    
    nohup celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4 > /var/log/celery/worker.log 2>&1 &
    
    WORKER_PID=$!
    echo $WORKER_PID > /var/run/celery_worker.pid
    
    echo "Воркер перезапущен (PID: $WORKER_PID)"
fi

echo "Проверяем статус..."
sleep 2

if [ -f ./check_celery_status.sh ]; then
    ./check_celery_status.sh
else
    echo "PID: $(cat /var/run/celery_worker.pid 2>/dev/null || echo 'не найден')"
    ps aux | grep celery | grep -v grep
fi
