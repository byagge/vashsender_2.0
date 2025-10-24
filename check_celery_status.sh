#!/bin/bash

# Скрипт для проверки статуса Celery воркера

echo "=== Статус Celery воркера ==="

# Проверяем PID файл
if [ -f /var/run/celery_worker.pid ]; then
    PID=$(cat /var/run/celery_worker.pid)
    echo "PID файл: /var/run/celery_worker.pid (PID: $PID)"
    
    # Проверяем что процесс существует
    if ps -p $PID > /dev/null 2>&1; then
        echo "✓ Воркер запущен (PID: $PID)"
        
        # Показываем информацию о процессе
        echo ""
        echo "Информация о процессе:"
        ps -p $PID -o pid,ppid,cmd,etime,pcpu,pmem
        
        # Показываем последние логи
        echo ""
        echo "Последние 10 строк логов:"
        echo "---"
        tail -10 /var/log/celery/worker.log 2>/dev/null || echo "Логи не найдены"
        echo "---"
        
    else
        echo "✗ Воркер не запущен (PID файл есть, но процесс не найден)"
        echo "Удаляем устаревший PID файл..."
        rm -f /var/run/celery_worker.pid
    fi
else
    echo "✗ PID файл не найден: /var/run/celery_worker.pid"
fi

echo ""

# Ищем все процессы celery
echo "Все процессы celery:"
CELERY_PIDS=$(pgrep -f "celery.*worker")
if [ -n "$CELERY_PIDS" ]; then
    # Исправляем синтаксис ps для нескольких PID
    ps -p $CELERY_PIDS -o pid,ppid,cmd,etime,pcpu,pmem 2>/dev/null || ps aux | grep celery | grep -v grep
else
    echo "Процессы celery не найдены"
fi

echo ""

# Проверяем очереди Redis
echo "Проверка очередей Redis:"
if command -v redis-cli > /dev/null 2>&1; then
    echo "Очередь default: $(redis-cli -n 0 LLEN celery)"
    echo "Очередь campaigns: $(redis-cli -n 0 LLEN campaigns)"
    echo "Очередь email: $(redis-cli -n 0 LLEN email)"
else
    echo "redis-cli не найден"
fi

echo ""
echo "=== Конец проверки ==="
