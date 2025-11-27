#!/bin/bash

# Production конфигурация для Celery
# Этот файл содержит все настройки для production среды

# ==============================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ДЛЯ PRODUCTION
# ==============================================

# PostgreSQL настройки
export POSTGRES_DB=vashsender
export POSTGRES_USER=vashsender
export POSTGRES_PASSWORD='34t89O7i@'
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_CONN_MAX_AGE=600
export POSTGRES_SSLMODE=prefer

# Redis настройки
export REDIS_URL=redis://localhost:6379/0

# Django настройки
export DJANGO_SETTINGS_MODULE=core.settings.production

# Celery настройки
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/0

# ==============================================
# ПУТИ И ДИРЕКТОРИИ
# ==============================================

PROJECT_DIR="/var/www/vashsender"
VENV_PATH="$PROJECT_DIR/venv"
LOG_DIR="/var/log/celery"
PID_FILE="/var/run/celery_worker.pid"
LOG_FILE="$LOG_DIR/worker.log"

# ==============================================
# CELERY КОМАНДЫ
# ==============================================

# Основная команда для запуска воркера
CELERY_WORKER_CMD="celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4"

# Команда для запуска beat (планировщика)
CELERY_BEAT_CMD="celery -A core.celery.app beat -l info"

# ==============================================
# ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ
# ==============================================

setup_environment() {
    echo "Настройка окружения..."
    
    # Переходим в директорию проекта
    cd $PROJECT_DIR
    
    # Активируем виртуальное окружение
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source $VENV_PATH/bin/activate
        echo "Виртуальное окружение активировано"
    else
        echo "ОШИБКА: Виртуальное окружение не найдено в $VENV_PATH"
        exit 1
    fi
    
    # Создаем директории для логов
    mkdir -p $LOG_DIR
    
    # Проверяем доступность PostgreSQL
    if ! pg_isready -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER > /dev/null 2>&1; then
        echo "ПРЕДУПРЕЖДЕНИЕ: PostgreSQL недоступен на $POSTGRES_HOST:$POSTGRES_PORT"
    else
        echo "PostgreSQL доступен"
    fi
    
    # Проверяем доступность Redis
    if ! redis-cli -u $REDIS_URL ping > /dev/null 2>&1; then
        echo "ПРЕДУПРЕЖДЕНИЕ: Redis недоступен по адресу $REDIS_URL"
    else
        echo "Redis доступен"
    fi
}

check_worker_status() {
    if [ -f $PID_FILE ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null 2>&1; then
            echo "Celery воркер работает (PID: $PID)"
            return 0
        else
            echo "PID файл найден, но процесс не работает"
            rm -f $PID_FILE
            return 1
        fi
    else
        echo "Celery воркер не запущен"
        return 1
    fi
}

stop_worker() {
    echo "Остановка Celery воркера..."
    
    if [ -f $PID_FILE ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null 2>&1; then
            echo "Останавливаем воркер (PID: $PID)..."
            kill $PID
            
            # Ждем до 10 секунд для graceful shutdown
            for i in {1..10}; do
                if ! ps -p $PID > /dev/null 2>&1; then
                    echo "Воркер остановлен"
                    break
                fi
                sleep 1
            done
            
            # Если процесс все еще работает, принудительно завершаем
            if ps -p $PID > /dev/null 2>&1; then
                echo "Принудительная остановка..."
                kill -9 $PID
                sleep 1
            fi
        fi
        rm -f $PID_FILE
    fi
    
    # Дополнительная проверка и очистка всех celery процессов
    CELERY_PIDS=$(pgrep -f "celery.*worker")
    if [ -n "$CELERY_PIDS" ]; then
        echo "Найдены дополнительные celery процессы: $CELERY_PIDS"
        kill $CELERY_PIDS 2>/dev/null
        sleep 2
        
        # Принудительно завершаем если нужно
        CELERY_PIDS=$(pgrep -f "celery.*worker")
        if [ -n "$CELERY_PIDS" ]; then
            echo "Принудительно завершаем оставшиеся процессы..."
            kill -9 $CELERY_PIDS 2>/dev/null
        fi
    fi
    
    echo "Все Celery процессы остановлены"
}

start_worker() {
    echo "Запуск Celery воркера..."
    
    # Проверяем что воркер не запущен
    if check_worker_status > /dev/null 2>&1; then
        echo "Воркер уже запущен"
        return 1
    fi
    
    # Настраиваем окружение
    setup_environment
    
    # Запускаем воркер в фоновом режиме
    echo "Команда: $CELERY_WORKER_CMD"
    nohup $CELERY_WORKER_CMD > $LOG_FILE 2>&1 &
    
    # Сохраняем PID
    WORKER_PID=$!
    echo $WORKER_PID > $PID_FILE
    
    # Проверяем что процесс запустился
    sleep 2
    if ps -p $WORKER_PID > /dev/null 2>&1; then
        echo "Celery воркер успешно запущен (PID: $WORKER_PID)"
        echo "Логи: $LOG_FILE"
        echo "PID файл: $PID_FILE"
        return 0
    else
        echo "ОШИБКА: Не удалось запустить воркер"
        rm -f $PID_FILE
        return 1
    fi
}

restart_worker() {
    echo "Перезапуск Celery воркера..."
    stop_worker
    sleep 2
    start_worker
}

show_status() {
    echo "=== СТАТУС CELERY ВОРКЕРА ==="
    
    if check_worker_status; then
        PID=$(cat $PID_FILE)
        echo "Статус: РАБОТАЕТ"
        echo "PID: $PID"
        echo "Время запуска: $(ps -o lstart= -p $PID 2>/dev/null || echo 'неизвестно')"
        echo "Использование CPU: $(ps -o %cpu= -p $PID 2>/dev/null || echo 'неизвестно')%"
        echo "Использование памяти: $(ps -o %mem= -p $PID 2>/dev/null || echo 'неизвестно')%"
    else
        echo "Статус: НЕ РАБОТАЕТ"
    fi
    
    echo ""
    echo "=== АКТИВНЫЕ CELERY ПРОЦЕССЫ ==="
    ps aux | grep celery | grep -v grep || echo "Нет активных процессов"
    
    echo ""
    echo "=== ПОСЛЕДНИЕ ЛОГИ ==="
    if [ -f $LOG_FILE ]; then
        echo "Файл логов: $LOG_FILE"
        echo "Размер: $(du -h $LOG_FILE | cut -f1)"
        echo "Последние 5 строк:"
        tail -n 5 $LOG_FILE
    else
        echo "Файл логов не найден"
    fi
}

show_logs() {
    if [ -f $LOG_FILE ]; then
        echo "Показываем логи Celery воркера..."
        echo "Файл: $LOG_FILE"
        echo "Для выхода нажмите Ctrl+C"
        echo "=========================="
        tail -f $LOG_FILE
    else
        echo "Файл логов не найден: $LOG_FILE"
        return 1
    fi
}

# ==============================================
# ОСНОВНАЯ ЛОГИКА
# ==============================================

case "${1:-status}" in
    start)
        start_worker
        ;;
    stop)
        stop_worker
        ;;
    restart)
        restart_worker
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    setup)
        setup_environment
        echo "Окружение настроено"
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|setup}"
        echo ""
        echo "Команды:"
        echo "  start   - Запустить Celery воркер"
        echo "  stop    - Остановить Celery воркер"
        echo "  restart - Перезапустить Celery воркер"
        echo "  status  - Показать статус воркера"
        echo "  logs    - Показать логи в реальном времени"
        echo "  setup   - Настроить окружение"
        exit 1
        ;;
esac
