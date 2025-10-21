#!/bin/bash

# Скрипт для остановки Celery воркера

echo "Остановка Celery воркера..."

# Проверяем есть ли PID файл
if [ -f /var/run/celery_worker.pid ]; then
    PID=$(cat /var/run/celery_worker.pid)
    echo "Найден PID: $PID"
    
    # Проверяем что процесс существует
    if ps -p $PID > /dev/null; then
        echo "Останавливаем процесс $PID..."
        kill $PID
        
        # Ждем завершения
        sleep 2
        
        # Проверяем что процесс остановлен
        if ps -p $PID > /dev/null; then
            echo "Принудительно завершаем процесс..."
            kill -9 $PID
        fi
        
        echo "Celery воркер остановлен"
    else
        echo "Процесс с PID $PID не найден"
    fi
    
    # Удаляем PID файл
    rm -f /var/run/celery_worker.pid
else
    echo "PID файл не найден, ищем процессы celery..."
    
    # Ищем процессы celery
    PIDS=$(pgrep -f "celery.*worker")
    
    if [ -n "$PIDS" ]; then
        echo "Найдены процессы celery: $PIDS"
        echo "Останавливаем..."
        kill $PIDS
        sleep 2
        
        # Принудительно завершаем если нужно
        PIDS=$(pgrep -f "celery.*worker")
        if [ -n "$PIDS" ]; then
            echo "Принудительно завершаем..."
            kill -9 $PIDS
        fi
        
        echo "Все процессы celery остановлены"
    else
        echo "Процессы celery не найдены"
    fi
fi
