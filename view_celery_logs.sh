#!/bin/bash

# Скрипт для просмотра логов Celery воркера

echo "=== Просмотр логов Celery ==="
echo ""

# Проверяем есть ли файл логов
if [ -f /var/log/celery/worker.log ]; then
    echo "Логи из файла: /var/log/celery/worker.log"
    echo ""
    echo "Выберите действие:"
    echo "1) Последние 50 строк"
    echo "2) Последние 100 строк"
    echo "3) Последние 500 строк"
    echo "4) Следить за логами в реальном времени (tail -f)"
    echo "5) Поиск по тексту"
    echo ""
    read -p "Выберите опцию (1-5): " option
    
    case $option in
        1)
            tail -50 /var/log/celery/worker.log
            ;;
        2)
            tail -100 /var/log/celery/worker.log
            ;;
        3)
            tail -500 /var/log/celery/worker.log
            ;;
        4)
            echo "Следим за логами... (Ctrl+C для выхода)"
            tail -f /var/log/celery/worker.log
            ;;
        5)
            read -p "Введите текст для поиска: " search_text
            grep -i "$search_text" /var/log/celery/worker.log | tail -100
            ;;
        *)
            echo "Неверная опция"
            ;;
    esac
else
    echo "Файл логов не найден: /var/log/celery/worker.log"
    echo ""
    echo "Проверяем другие места:"
    
    # Проверяем systemd логи если используется сервис
    if systemctl is-active --quiet vashsender-celery-worker.service 2>/dev/null; then
        echo "Celery работает как systemd сервис"
        echo "Логи через journalctl:"
        echo "  sudo journalctl -u vashsender-celery-worker.service -f"
        echo ""
        echo "Последние 100 строк:"
        sudo journalctl -u vashsender-celery-worker.service -n 100
    else
        echo "Ищем процессы celery..."
        CELERY_PIDS=$(pgrep -f "celery.*worker")
        if [ -n "$CELERY_PIDS" ]; then
            echo "Найдены процессы celery: $CELERY_PIDS"
            echo "Проверьте логи вручную или через journalctl если celery запущен в другом месте"
        else
            echo "Процессы celery не найдены"
        fi
    fi
fi

