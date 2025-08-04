#!/bin/bash

# Скрипт для запуска Celery воркера для импорта контактов

echo "=== Запуск Celery воркера для импорта контактов ==="

# Проверяем, что мы в правильной директории
if [ ! -f "manage.py" ]; then
    echo "Ошибка: manage.py не найден. Запустите скрипт из корневой директории проекта."
    exit 1
fi

# Проверяем переменные окружения
if [ -z "$CELERY_BROKER_URL" ]; then
    echo "Предупреждение: CELERY_BROKER_URL не установлен. Используется значение по умолчанию."
fi

# Функция для остановки воркера
cleanup() {
    echo "Останавливаем воркер..."
    kill $CELERY_PID 2>/dev/null
    exit 0
}

# Устанавливаем обработчик сигналов
trap cleanup SIGINT SIGTERM

echo "Запускаем Celery воркер для очереди 'import'..."
echo "Для остановки нажмите Ctrl+C"

# Запускаем воркер
celery -A core worker -Q import -l info --concurrency=2 --max-tasks-per-child=1000 &
CELERY_PID=$!

echo "Воркер запущен с PID: $CELERY_PID"
echo "Логи:"

# Ждем завершения
wait $CELERY_PID 