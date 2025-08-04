#!/bin/bash

# Универсальный скрипт для запуска всех Celery воркеров VashSender

echo "=== VashSender Celery Workers Manager ==="

# Проверяем, что мы в правильной директории
if [ ! -f "manage.py" ]; then
    echo "Ошибка: manage.py не найден. Запустите скрипт из корневой директории проекта."
    exit 1
fi

# Проверяем переменные окружения
if [ -z "$CELERY_BROKER_URL" ]; then
    echo "Предупреждение: CELERY_BROKER_URL не установлен. Используется значение по умолчанию."
fi

# Функция для остановки всех воркеров
cleanup() {
    echo "Останавливаем все воркеры..."
    pkill -f "celery.*worker" 2>/dev/null
    pkill -f "celery.*beat" 2>/dev/null
    exit 0
}

# Устанавливаем обработчик сигналов
trap cleanup SIGINT SIGTERM

# Функция для запуска воркера
start_worker() {
    local queue_name=$1
    local concurrency=$2
    local worker_name=$3
    
    echo "Запускаем воркер для очереди '$queue_name' (concurrency: $concurrency)..."
    
    celery -A core worker \
        -Q $queue_name \
        -n $worker_name@%h \
        --concurrency=$concurrency \
        --loglevel=info \
        --max-tasks-per-child=1000 \
        --max-memory-per-child=200000 \
        --without-gossip \
        --without-mingle \
        --without-heartbeat &
    
    echo "Воркер $worker_name запущен с PID: $!"
}

# Функция для запуска beat
start_beat() {
    echo "Запускаем Celery Beat для периодических задач..."
    
    celery -A core beat \
        --loglevel=info \
        --scheduler=django_celery_beat.schedulers:DatabaseScheduler \
        --max-interval=60 &
    
    echo "Celery Beat запущен с PID: $!"
}

# Основное меню
show_menu() {
    echo ""
    echo "Выберите режим запуска:"
    echo "1) Все воркеры (рекомендуется для продакшена)"
    echo "2) Только импорт (для тестирования импорта)"
    echo "3) Только email (для тестирования отправки)"
    echo "4) Только кампании (для тестирования кампаний)"
    echo "5) Beat только (только периодические задачи)"
    echo "6) Остановить все воркеры"
    echo "7) Статус воркеров"
    echo "0) Выход"
    echo ""
}

# Функция для проверки статуса
check_status() {
    echo "=== Статус Celery воркеров ==="
    
    # Проверяем запущенные процессы
    echo "Запущенные процессы:"
    ps aux | grep -E "celery.*worker|celery.*beat" | grep -v grep || echo "Нет запущенных воркеров"
    
    echo ""
    echo "Активные задачи:"
    celery -A core inspect active 2>/dev/null || echo "Не удалось получить информацию о задачах"
    
    echo ""
    echo "Статистика:"
    celery -A core inspect stats 2>/dev/null || echo "Не удалось получить статистику"
}

# Функция для остановки всех воркеров
stop_workers() {
    echo "Останавливаем все Celery процессы..."
    pkill -f "celery.*worker" 2>/dev/null
    pkill -f "celery.*beat" 2>/dev/null
    echo "Все воркеры остановлены"
}

# Основной цикл
while true; do
    show_menu
    read -p "Введите номер (0-7): " choice
    
    case $choice in
        1)
            echo "Запускаем все воркеры..."
            
            # Запускаем beat
            start_beat
            
            # Запускаем воркеры для разных очередей
            start_worker "import" 2 "import-worker"
            start_worker "email" 4 "email-worker" 
            start_worker "campaigns" 2 "campaigns-worker"
            start_worker "default" 1 "default-worker"
            
            echo "Все воркеры запущены!"
            echo "Для остановки нажмите Ctrl+C"
            
            # Ждем завершения
            wait
            ;;
            
        2)
            echo "Запускаем только воркер импорта..."
            start_worker "import" 2 "import-worker"
            echo "Воркер импорта запущен!"
            echo "Для остановки нажмите Ctrl+C"
            wait
            ;;
            
        3)
            echo "Запускаем только email воркер..."
            start_worker "email" 4 "email-worker"
            echo "Email воркер запущен!"
            echo "Для остановки нажмите Ctrl+C"
            wait
            ;;
            
        4)
            echo "Запускаем только воркер кампаний..."
            start_worker "campaigns" 2 "campaigns-worker"
            echo "Воркер кампаний запущен!"
            echo "Для остановки нажмите Ctrl+C"
            wait
            ;;
            
        5)
            echo "Запускаем только Celery Beat..."
            start_beat
            echo "Celery Beat запущен!"
            echo "Для остановки нажмите Ctrl+C"
            wait
            ;;
            
        6)
            stop_workers
            ;;
            
        7)
            check_status
            ;;
            
        0)
            echo "Выход..."
            exit 0
            ;;
            
        *)
            echo "Неверный выбор. Попробуйте снова."
            ;;
    esac
    
    echo ""
    read -p "Нажмите Enter для продолжения..."
done 