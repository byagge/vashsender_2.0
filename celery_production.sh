#!/bin/bash

# ==============================================
# PRODUCTION CELERY УПРАВЛЕНИЕ
# ==============================================
# Этот скрипт обеспечивает надежный запуск Celery в production
# с автоматической загрузкой переменных окружения

set -e  # Выходим при любой ошибке

# ==============================================
# КОНФИГУРАЦИЯ
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/var/www/vashsender"
ENV_FILE="$SCRIPT_DIR/production.env"
VENV_PATH="$PROJECT_DIR/venv"
LOG_DIR="/var/log/celery"
PID_FILE="/var/run/celery_worker.pid"
LOG_FILE="$LOG_DIR/worker.log"

# ==============================================
# ФУНКЦИИ
# ==============================================

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

load_environment() {
    log_message "Загрузка переменных окружения..."
    
    # Загружаем переменные из файла
    if [ -f "$ENV_FILE" ]; then
        log_message "Загружаем переменные из $ENV_FILE"
        set -a  # автоматически экспортируем переменные
        source "$ENV_FILE"
        set +a
    else
        log_message "ПРЕДУПРЕЖДЕНИЕ: Файл $ENV_FILE не найден, используем переменные по умолчанию"
        
        # Устанавливаем переменные по умолчанию
        export POSTGRES_DB=vashsender
        export POSTGRES_USER=vashsender
        export POSTGRES_PASSWORD='34t89O7i@'
        export POSTGRES_HOST=127.0.0.1
        export POSTGRES_PORT=5432
        export POSTGRES_CONN_MAX_AGE=600
        export POSTGRES_SSLMODE=prefer
        export REDIS_URL=redis://localhost:6379/0
        export DJANGO_SETTINGS_MODULE=core.settings.production
    fi
    
    log_message "Переменные окружения загружены"
}

setup_directories() {
    log_message "Создание необходимых директорий..."
    
    # Создаем директории для логов
    mkdir -p "$LOG_DIR"
    
    # Создаем директорию для PID файлов
    mkdir -p "$(dirname "$PID_FILE")"
    
    log_message "Директории созданы"
}

activate_venv() {
    log_message "Активация виртуального окружения..."
    
    if [ -f "$VENV_PATH/bin/activate" ]; then
        cd "$PROJECT_DIR"
        source "$VENV_PATH/bin/activate"
        log_message "Виртуальное окружение активировано: $VIRTUAL_ENV"
    else
        log_message "ОШИБКА: Виртуальное окружение не найдено в $VENV_PATH"
        exit 1
    fi
}

check_dependencies() {
    log_message "Проверка зависимостей..."
    
    # Проверяем PostgreSQL
    if command -v pg_isready >/dev/null 2>&1; then
        if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" >/dev/null 2>&1; then
            log_message "✓ PostgreSQL доступен"
        else
            log_message "⚠ ПРЕДУПРЕЖДЕНИЕ: PostgreSQL недоступен на $POSTGRES_HOST:$POSTGRES_PORT"
        fi
    else
        log_message "⚠ ПРЕДУПРЕЖДЕНИЕ: pg_isready не найден"
    fi
    
    # Проверяем Redis
    if command -v redis-cli >/dev/null 2>&1; then
        if redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
            log_message "✓ Redis доступен"
        else
            log_message "⚠ ПРЕДУПРЕЖДЕНИЕ: Redis недоступен по адресу $REDIS_URL"
        fi
    else
        log_message "⚠ ПРЕДУПРЕЖДЕНИЕ: redis-cli не найден"
    fi
    
    # Проверяем Django
    if python -c "import django; print('Django version:', django.get_version())" 2>/dev/null; then
        log_message "✓ Django доступен"
    else
        log_message "⚠ ПРЕДУПРЕЖДЕНИЕ: Django недоступен"
    fi
    
    # Проверяем Celery
    if python -c "import celery; print('Celery version:', celery.__version__)" 2>/dev/null; then
        log_message "✓ Celery доступен"
    else
        log_message "ОШИБКА: Celery недоступен"
        exit 1
    fi
}

is_worker_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" >/dev/null 2>&1; then
            return 0  # работает
        else
            rm -f "$PID_FILE"
            return 1  # не работает
        fi
    else
        return 1  # не работает
    fi
}

stop_worker() {
    log_message "Остановка Celery воркера..."
    
    if is_worker_running; then
        local pid=$(cat "$PID_FILE")
        log_message "Останавливаем воркер (PID: $pid)..."
        
        # Graceful shutdown
        kill "$pid"
        
        # Ждем до 15 секунд для graceful shutdown
        local count=0
        while [ $count -lt 15 ] && ps -p "$pid" >/dev/null 2>&1; do
            sleep 1
            count=$((count + 1))
        done
        
        # Если процесс все еще работает, принудительно завершаем
        if ps -p "$pid" >/dev/null 2>&1; then
            log_message "Принудительная остановка..."
            kill -9 "$pid"
            sleep 1
        fi
        
        rm -f "$PID_FILE"
        log_message "Воркер остановлен"
    else
        log_message "Воркер не запущен"
    fi
    
    # Дополнительная очистка всех celery процессов
    local celery_pids=$(pgrep -f "celery.*worker" 2>/dev/null || true)
    if [ -n "$celery_pids" ]; then
        log_message "Найдены дополнительные celery процессы: $celery_pids"
        kill $celery_pids 2>/dev/null || true
        sleep 2
        
        # Принудительно завершаем если нужно
        celery_pids=$(pgrep -f "celery.*worker" 2>/dev/null || true)
        if [ -n "$celery_pids" ]; then
            log_message "Принудительно завершаем оставшиеся процессы..."
            kill -9 $celery_pids 2>/dev/null || true
        fi
    fi
    
    log_message "Все Celery процессы остановлены"
}

start_worker() {
    log_message "Запуск Celery воркера..."
    
    # Проверяем что воркер не запущен
    if is_worker_running; then
        log_message "Воркер уже запущен (PID: $(cat "$PID_FILE"))"
        return 0
    fi
    
    # Настраиваем окружение
    load_environment
    setup_directories
    activate_venv
    check_dependencies
    
    # Запускаем воркер
    local celery_cmd="celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4"
    
    log_message "Команда: $celery_cmd"
    log_message "Логи: $LOG_FILE"
    
    # Запускаем в фоновом режиме
    nohup $celery_cmd >"$LOG_FILE" 2>&1 &
    local worker_pid=$!
    
    # Сохраняем PID
    echo "$worker_pid" > "$PID_FILE"
    
    # Проверяем что процесс запустился
    sleep 3
    if ps -p "$worker_pid" >/dev/null 2>&1; then
        log_message "✓ Celery воркер успешно запущен (PID: $worker_pid)"
        return 0
    else
        log_message "✗ ОШИБКА: Не удалось запустить воркер"
        rm -f "$PID_FILE"
        
        # Показываем последние строки лога для диагностики
        if [ -f "$LOG_FILE" ]; then
            log_message "Последние строки лога:"
            tail -n 10 "$LOG_FILE"
        fi
        
        return 1
    fi
}

restart_worker() {
    log_message "Перезапуск Celery воркера..."
    stop_worker
    sleep 2
    start_worker
}

show_status() {
    echo "=== СТАТУС CELERY ВОРКЕРА ==="
    echo "Время проверки: $(date)"
    echo ""
    
    if is_worker_running; then
        local pid=$(cat "$PID_FILE")
        echo "Статус: ✓ РАБОТАЕТ"
        echo "PID: $pid"
        
        if command -v ps >/dev/null 2>&1; then
            echo "Время запуска: $(ps -o lstart= -p "$pid" 2>/dev/null || echo 'неизвестно')"
            echo "Использование CPU: $(ps -o %cpu= -p "$pid" 2>/dev/null || echo 'неизвестно')%"
            echo "Использование памяти: $(ps -o %mem= -p "$pid" 2>/dev/null || echo 'неизвестно')%"
        fi
    else
        echo "Статус: ✗ НЕ РАБОТАЕТ"
    fi
    
    echo ""
    echo "=== КОНФИГУРАЦИЯ ==="
    echo "Проект: $PROJECT_DIR"
    echo "Виртуальное окружение: $VENV_PATH"
    echo "Файл переменных: $ENV_FILE"
    echo "PID файл: $PID_FILE"
    echo "Лог файл: $LOG_FILE"
    
    echo ""
    echo "=== АКТИВНЫЕ CELERY ПРОЦЕССЫ ==="
    if command -v ps >/dev/null 2>&1; then
        ps aux | grep celery | grep -v grep || echo "Нет активных процессов"
    else
        echo "Команда ps недоступна"
    fi
    
    echo ""
    echo "=== ИНФОРМАЦИЯ О ЛОГАХ ==="
    if [ -f "$LOG_FILE" ]; then
        echo "Файл логов: $LOG_FILE"
        if command -v du >/dev/null 2>&1; then
            echo "Размер: $(du -h "$LOG_FILE" | cut -f1)"
        fi
        echo "Последние 5 строк:"
        tail -n 5 "$LOG_FILE" 2>/dev/null || echo "Не удалось прочитать лог"
    else
        echo "Файл логов не найден"
    fi
}

show_logs() {
    if [ -f "$LOG_FILE" ]; then
        log_message "Показываем логи Celery воркера..."
        echo "Файл: $LOG_FILE"
        echo "Для выхода нажмите Ctrl+C"
        echo "=========================="
        tail -f "$LOG_FILE"
    else
        log_message "Файл логов не найден: $LOG_FILE"
        return 1
    fi
}

test_setup() {
    log_message "Тестирование настроек..."
    
    load_environment
    activate_venv
    check_dependencies
    
    log_message "Тест Django настроек..."
    if python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')
import django
django.setup()
from django.conf import settings
print('✓ Django настройки загружены')
print('✓ База данных:', settings.DATABASES['default']['ENGINE'])
print('✓ Celery broker:', settings.CELERY_BROKER_URL)
" 2>/dev/null; then
        log_message "✓ Django настройки корректны"
    else
        log_message "✗ Ошибка в Django настройках"
        return 1
    fi
    
    log_message "Тест Celery настроек..."
    if python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')
import django
django.setup()
from core.celery import app
print('✓ Celery app создан')
print('✓ Broker URL:', app.conf.broker_url)
print('✓ Result backend:', app.conf.result_backend)
" 2>/dev/null; then
        log_message "✓ Celery настройки корректны"
    else
        log_message "✗ Ошибка в Celery настройках"
        return 1
    fi
    
    log_message "✓ Все тесты пройдены успешно"
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
    test)
        test_setup
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|test}"
        echo ""
        echo "Команды:"
        echo "  start   - Запустить Celery воркер"
        echo "  stop    - Остановить Celery воркер"  
        echo "  restart - Перезапустить Celery воркер"
        echo "  status  - Показать подробный статус"
        echo "  logs    - Показать логи в реальном времени"
        echo "  test    - Протестировать настройки"
        echo ""
        echo "Примеры:"
        echo "  $0 start    # Запустить воркер"
        echo "  $0 restart  # Перезапустить воркер"
        echo "  $0 logs     # Смотреть логи"
        exit 1
        ;;
esac
