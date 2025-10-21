#!/bin/bash

# Скрипт для удаления Celery systemd сервиса

echo "Удаляем Celery systemd сервис..."

# Останавливаем и отключаем сервис
sudo systemctl stop vashsender-celery-worker.service
sudo systemctl disable vashsender-celery-worker.service

# Удаляем unit файл
sudo rm -f /etc/systemd/system/vashsender-celery-worker.service

# Перезагружаем systemd
sudo systemctl daemon-reload

echo "Celery systemd сервис удален."
echo ""
echo "Теперь запускайте воркер вручную:"
echo "cd /var/www/vashsender"
echo "source venv/bin/activate"
echo "export POSTGRES_DB=vashsender"
echo "export POSTGRES_USER=vashsender"
echo "export POSTGRES_PASSWORD='34t89O7i@'"
echo "export POSTGRES_HOST=127.0.0.1"
echo "export POSTGRES_PORT=5432"
echo "export POSTGRES_CONN_MAX_AGE=600"
echo "export POSTGRES_SSLMODE=prefer"
echo "export REDIS_URL=redis://localhost:6379/0"
echo "celery -A core.celery.app worker -l info -Q campaigns,email,default --concurrency=4"
