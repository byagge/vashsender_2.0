# Настройка Celery для VashSender

## Проблема
Кампании не отправляются автоматически, потому что Celery воркер не запущен как системный сервис.

## Решение

### 1. Создайте .env файл
```bash
nano /var/www/vashsender/.env
```

Содержимое:
```
POSTGRES_DB=vashsender
POSTGRES_USER=vashsender
POSTGRES_PASSWORD='34t89O7i@'
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=600
POSTGRES_SSLMODE=prefer
REDIS_URL=redis://localhost:6379/0
```

### 2. Настройте systemd сервис
```bash
# Создайте директории
sudo mkdir -p /var/log/celery /var/run/celery
sudo chown www-data:www-data /var/log/celery /var/run/celery

# Скопируйте unit файл
sudo cp vashsender-celery-worker.service /etc/systemd/system/

# Перезагрузите systemd и запустите сервис
sudo systemctl daemon-reload
sudo systemctl enable vashsender-celery-worker.service
sudo systemctl start vashsender-celery-worker.service
```

### 3. Проверьте статус
```bash
sudo systemctl status vashsender-celery-worker.service
sudo journalctl -u vashsender-celery-worker.service -f
```

### 4. Управление сервисом
```bash
# Запуск/остановка/перезапуск
sudo systemctl start vashsender-celery-worker.service
sudo systemctl stop vashsender-celery-worker.service
sudo systemctl restart vashsender-celery-worker.service

# Просмотр логов
sudo journalctl -u vashsender-celery-worker.service -f
```

### 5. Очистка зависших задач (если нужно)
```bash
cd /var/www/vashsender
python cleanup_celery_queue.py
```

## Что исправлено в коде

1. **Защита от удаления активных кампаний** - нельзя удалить кампанию во время отправки
2. **Метод отмены кампании** - можно отменить отправляющуюся кампанию
3. **Улучшенная обработка ошибок** - задача не падает если кампания удалена
4. **Системный сервис** - Celery воркер запускается автоматически

## Проверка работы

1. Создайте тестовую кампанию
2. Запустите отправку
3. Проверьте логи: `sudo journalctl -u vashsender-celery-worker.service -f`
4. Кампания должна перейти в статус "Отправляется" и затем "Отправлено"
