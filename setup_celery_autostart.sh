#!/bin/bash

# ==============================================
# НАСТРОЙКА АВТОЗАПУСКА CELERY
# ==============================================
# Этот скрипт настраивает автозапуск Celery через crontab

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CELERY_SCRIPT="$SCRIPT_DIR/celery_production.sh"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

setup_autostart() {
    log_message "Настройка автозапуска Celery..."
    
    # Проверяем что скрипт существует
    if [ ! -f "$CELERY_SCRIPT" ]; then
        log_message "ОШИБКА: Скрипт $CELERY_SCRIPT не найден"
        exit 1
    fi
    
    # Делаем скрипт исполняемым
    chmod +x "$CELERY_SCRIPT"
    log_message "Скрипт $CELERY_SCRIPT сделан исполняемым"
    
    # Создаем cron задачу для автозапуска при перезагрузке
    local cron_line="@reboot $CELERY_SCRIPT start"
    
    # Проверяем существует ли уже такая задача
    if crontab -l 2>/dev/null | grep -q "$CELERY_SCRIPT start"; then
        log_message "Задача автозапуска уже существует"
    else
        # Добавляем задачу в crontab
        (crontab -l 2>/dev/null; echo "$cron_line") | crontab -
        log_message "✓ Задача автозапуска добавлена в crontab"
    fi
    
    # Создаем дополнительную задачу для проверки каждые 5 минут
    local check_line="*/5 * * * * $CELERY_SCRIPT status >/dev/null 2>&1 || $CELERY_SCRIPT start"
    
    if crontab -l 2>/dev/null | grep -q "$CELERY_SCRIPT status"; then
        log_message "Задача мониторинга уже существует"
    else
        (crontab -l 2>/dev/null; echo "$check_line") | crontab -
        log_message "✓ Задача мониторинга добавлена в crontab"
    fi
    
    log_message "Текущие cron задачи:"
    crontab -l | grep "$CELERY_SCRIPT" || echo "Нет задач"
}

remove_autostart() {
    log_message "Удаление автозапуска Celery..."
    
    # Удаляем задачи из crontab
    if crontab -l 2>/dev/null | grep -v "$CELERY_SCRIPT" | crontab -; then
        log_message "✓ Задачи автозапуска удалены из crontab"
    else
        log_message "Задачи не найдены или ошибка при удалении"
    fi
}

show_autostart_status() {
    log_message "Статус автозапуска Celery:"
    
    echo ""
    echo "=== CRON ЗАДАЧИ ==="
    if crontab -l 2>/dev/null | grep "$CELERY_SCRIPT"; then
        echo "Найдены следующие задачи:"
        crontab -l | grep "$CELERY_SCRIPT"
    else
        echo "Задачи автозапуска не найдены"
    fi
    
    echo ""
    echo "=== СТАТУС СКРИПТА ==="
    if [ -f "$CELERY_SCRIPT" ]; then
        echo "Скрипт: ✓ $CELERY_SCRIPT"
        if [ -x "$CELERY_SCRIPT" ]; then
            echo "Права: ✓ исполняемый"
        else
            echo "Права: ✗ не исполняемый"
        fi
    else
        echo "Скрипт: ✗ не найден"
    fi
    
    echo ""
    echo "=== СТАТУС CELERY ==="
    if [ -x "$CELERY_SCRIPT" ]; then
        "$CELERY_SCRIPT" status
    else
        echo "Невозможно проверить статус - скрипт недоступен"
    fi
}

create_startup_script() {
    log_message "Создание скрипта запуска для systemd..."
    
    local service_file="/etc/systemd/system/vashsender-celery.service"
    
    cat > "$service_file" << EOF
[Unit]
Description=VashSender Celery Worker
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=forking
User=root
Group=root
WorkingDirectory=/var/www/vashsender
ExecStart=$CELERY_SCRIPT start
ExecStop=$CELERY_SCRIPT stop
ExecReload=$CELERY_SCRIPT restart
Restart=always
RestartSec=10
PIDFile=/var/run/celery_worker.pid

# Переменные окружения
Environment=DJANGO_SETTINGS_MODULE=core.settings.production
EnvironmentFile=$SCRIPT_DIR/production.env

[Install]
WantedBy=multi-user.target
EOF

    log_message "✓ Systemd сервис создан: $service_file"
    
    # Перезагружаем systemd
    systemctl daemon-reload
    log_message "✓ Systemd daemon перезагружен"
    
    # Включаем автозапуск
    systemctl enable vashsender-celery.service
    log_message "✓ Автозапуск включен"
    
    echo ""
    echo "Команды для управления сервисом:"
    echo "  systemctl start vashsender-celery    # Запустить"
    echo "  systemctl stop vashsender-celery     # Остановить"
    echo "  systemctl restart vashsender-celery  # Перезапустить"
    echo "  systemctl status vashsender-celery   # Статус"
    echo "  systemctl disable vashsender-celery  # Отключить автозапуск"
}

case "${1:-status}" in
    setup)
        setup_autostart
        ;;
    remove)
        remove_autostart
        ;;
    status)
        show_autostart_status
        ;;
    systemd)
        create_startup_script
        ;;
    *)
        echo "Использование: $0 {setup|remove|status|systemd}"
        echo ""
        echo "Команды:"
        echo "  setup   - Настроить автозапуск через cron"
        echo "  remove  - Удалить автозапуск"
        echo "  status  - Показать статус автозапуска"
        echo "  systemd - Создать systemd сервис (требует root)"
        echo ""
        echo "Рекомендуется использовать 'setup' для простой настройки"
        exit 1
        ;;
esac
