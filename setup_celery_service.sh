#!/bin/bash

# Скрипт для настройки Celery как системного сервиса

echo "Настройка Celery Worker как системного сервиса..."

# Создаем директории для логов и PID файлов
sudo mkdir -p /var/log/celery
sudo mkdir -p /var/run/celery
sudo chown www-data:www-data /var/log/celery
sudo chown www-data:www-data /var/run/celery

# Копируем unit файл в systemd
sudo cp vashsender-celery-worker.service /etc/systemd/system/

# Перезагружаем systemd и включаем сервис
sudo systemctl daemon-reload
sudo systemctl enable vashsender-celery-worker.service

echo "Сервис настроен. Запускаем..."
sudo systemctl start vashsender-celery-worker.service

# Проверяем статус
echo "Проверяем статус сервиса:"
sudo systemctl status vashsender-celery-worker.service

echo ""
echo "Команды для управления сервисом:"
echo "sudo systemctl start vashsender-celery-worker.service   # Запустить"
echo "sudo systemctl stop vashsender-celery-worker.service    # Остановить"
echo "sudo systemctl restart vashsender-celery-worker.service # Перезапустить"
echo "sudo systemctl status vashsender-celery-worker.service  # Статус"
echo "sudo journalctl -u vashsender-celery-worker.service -f  # Логи в реальном времени"
