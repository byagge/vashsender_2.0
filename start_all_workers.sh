#!/bin/bash

# Быстрый запуск всех Celery воркеров VashSender

echo "=== Запуск всех Celery воркеров VashSender ==="

# Проверяем, что мы в правильной директории
if [ ! -f "manage.py" ]; then
    echo "Ошибка: manage.py не найден. Запустите скрипт из корневой директории проекта."
    exit 1
fi

# Функция для остановки всех воркеров
cleanup() {
    echo ""
    echo "Останавливаем все воркеры..."
    pkill -f "celery.*worker" 2>/dev/null
    pkill -f "celery.*beat" 2>/dev/null
    echo "Все воркеры остановлены"
    exit 0
}

# Устанавливаем обработчик сигналов
trap cleanup SIGINT SIGTERM

echo "Запускаем Celery Beat..."
celery -A core beat --loglevel=info --scheduler=django_celery_beat.schedulers:DatabaseScheduler &
BEAT_PID=$!
echo "Celery Beat запущен с PID: $BEAT_PID"

echo ""
echo "Запускаем воркеры для всех очередей..."

# Запускаем воркер для всех очередей одновременно
celery -A core worker \
    -Q import,email,campaigns,default \
    -n vashsender-worker@%h \
    --concurrency=8 \
    --loglevel=info \
    --max-tasks-per-child=1000 \
    --max-memory-per-child=200000 \
    --without-gossip \
    --without-mingle \
    --without-heartbeat

echo ""
echo "Все воркеры остановлены" 