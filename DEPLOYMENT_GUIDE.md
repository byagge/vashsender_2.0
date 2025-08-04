# Руководство по развертыванию асинхронного импорта

## Быстрый старт

### 1. Применение миграций
```bash
python manage.py makemigrations mailer
python manage.py migrate
```

### 2. Запуск Celery воркера
```bash
# Вариант 1: Используя скрипт
chmod +x start_import_worker.sh
./start_import_worker.sh

# Вариант 2: Прямой запуск
celery -A core worker -Q import -l info --concurrency=2
```

### 3. Тестирование
```bash
python test_async_import.py
```

## Продакшн настройка

### 1. Системный сервис для Celery
Создайте файл `/etc/systemd/system/vashsender-import-worker.service`:

```ini
[Unit]
Description=VashSender Import Worker
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/vashsender
Environment=DJANGO_SETTINGS_MODULE=core.settings.production
ExecStart=/path/to/venv/bin/celery -A core worker -Q import -l info --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Запуск сервиса
```bash
sudo systemctl daemon-reload
sudo systemctl enable vashsender-import-worker
sudo systemctl start vashsender-import-worker
sudo systemctl status vashsender-import-worker
```

### 3. Мониторинг
```bash
# Просмотр логов
sudo journalctl -u vashsender-import-worker -f

# Проверка статуса
sudo systemctl status vashsender-import-worker
```

## Настройка Redis (рекомендуется)

### 1. Установка Redis
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server

# CentOS/RHEL
sudo yum install redis
```

### 2. Настройка Redis
```bash
# Редактируем конфигурацию
sudo nano /etc/redis/redis.conf

# Добавляем/изменяем:
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### 3. Запуск Redis
```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### 4. Настройка Django
В `settings/production.py`:
```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

## Мониторинг и логирование

### 1. Логи Celery
```bash
# Просмотр активных задач
celery -A core inspect active

# Статистика воркера
celery -A core inspect stats

# Мониторинг очередей
celery -A core inspect stats -d celery@hostname
```

### 2. Логи Django
В `settings/production.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/vashsender/import.log',
        },
    },
    'loggers': {
        'apps.mailer.tasks': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### 3. Мониторинг задач импорта
```python
# Скрипт для мониторинга
from apps.mailer.models import ImportTask
from django.utils import timezone
from datetime import timedelta

# Задачи за последний час
recent_tasks = ImportTask.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=1)
)

# Неудачные задачи
failed_tasks = ImportTask.objects.filter(status='failed')

# Долгие задачи (>30 минут)
long_tasks = ImportTask.objects.filter(
    status='processing',
    started_at__lte=timezone.now() - timedelta(minutes=30)
)
```

## Оптимизация производительности

### 1. Настройка воркера
```bash
# Больше процессов для параллельной обработки
celery -A core worker -Q import -l info --concurrency=8

# Ограничение памяти
celery -A core worker -Q import -l info --concurrency=4 --max-memory-per-child=200000
```

### 2. Настройка батчинга
В `apps/mailer/tasks.py`:
```python
# Увеличиваем размер батча для больших файлов
batch_size = 500  # Вместо 100

# Уменьшаем частоту обновления прогресса
if processed % 500 == 0:  # Вместо 100
```

### 3. DNS кэширование
```python
# В settings/production.py
import socket
socket.setdefaulttimeout(10)  # Таймаут DNS запросов
```

## Безопасность

### 1. Ограничения файлов
```python
# В views.py
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = ['.txt', '.csv', '.json']

def validate_file(file_obj):
    if file_obj.size > MAX_FILE_SIZE:
        raise ValidationError('File too large')
    
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError('Invalid file type')
```

### 2. Очистка старых задач
```python
# Management command для очистки
from django.core.management.base import BaseCommand
from apps.mailer.models import ImportTask
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Clean old import tasks'
    
    def handle(self, *args, **options):
        # Удаляем задачи старше 30 дней
        old_tasks = ImportTask.objects.filter(
            created_at__lte=timezone.now() - timedelta(days=30)
        )
        count = old_tasks.count()
        old_tasks.delete()
        self.stdout.write(f'Deleted {count} old tasks')
```

### 3. Запуск очистки
```bash
# Добавить в cron
0 2 * * * /path/to/venv/bin/python /path/to/manage.py clean_import_tasks
```

## Устранение неполадок

### Проблема: Воркер не запускается
```bash
# Проверка зависимостей
pip install celery[redis]

# Проверка настроек
python manage.py shell
>>> from django.conf import settings
>>> print(settings.CELERY_BROKER_URL)
```

### Проблема: Задачи не выполняются
```bash
# Проверка подключения к брокеру
celery -A core inspect ping

# Проверка очередей
celery -A core inspect active_queues
```

### Проблема: Медленная валидация
```bash
# Увеличиваем количество воркеров
celery -A core worker -Q import -l info --concurrency=8

# Проверяем DNS
nslookup gmail.com
dig MX gmail.com
```

## Тестирование в продакшене

### 1. Тест производительности
```bash
# Создаем большой тестовый файл
python -c "
emails = [f'test{i}@example.com' for i in range(10000)]
with open('large_test.txt', 'w') as f:
    f.write('\n'.join(emails))
"
```

### 2. Мониторинг ресурсов
```bash
# Мониторинг CPU и памяти
htop

# Мониторинг диска
df -h

# Мониторинг сети
iftop
```

### 3. Логирование ошибок
```bash
# Просмотр ошибок в реальном времени
tail -f /var/log/vashsender/import.log | grep ERROR
```

## Резервное копирование

### 1. База данных
```bash
# Экспорт задач импорта
python manage.py dumpdata apps.mailer.ImportTask --indent=2 > import_tasks_backup.json

# Восстановление
python manage.py loaddata import_tasks_backup.json
```

### 2. Конфигурация
```bash
# Резервное копирование настроек
cp core/settings/production.py production_backup.py
cp start_import_worker.sh worker_backup.sh
``` 