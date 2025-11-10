import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

app = Celery('vashsender')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Configure Celery settings
# ВАЖНО: Настройки времени (task_time_limit, task_soft_time_limit) берутся из production.py
# чтобы не было конфликта. Там установлено 4 часа для больших рассылок.
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    task_track_started=True,
    # НЕ устанавливаем task_time_limit и task_soft_time_limit здесь - они берутся из production.py
    worker_prefetch_multiplier=1,  # Обрабатываем по одной задаче за раз
    worker_max_tasks_per_child=1000,
    broker_connection_retry_on_startup=True,
    result_expires=3600,  # 1 hour
    # Важно: worker_concurrency контролирует количество параллельных процессов
    # По умолчанию = количество CPU, но можно задать явно
    worker_concurrency=4,  # Добавляем больше воркеров для параллельной обработки
)

# Configure task routes
app.conf.task_routes = {
    'apps.campaigns.tasks.send_campaign': {'queue': 'campaigns'},
    'apps.campaigns.tasks.send_email_batch': {'queue': 'email'},
    'apps.campaigns.tasks.send_single_email': {'queue': 'email'},
    'apps.campaigns.tasks.test_celery': {'queue': 'campaigns'},
}

# Configure task queues
app.conf.task_default_queue = 'default'
app.conf.task_queues = {
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
    },
    'email': {
        'exchange': 'email',
        'routing_key': 'email',
        'queue_arguments': {'x-max-priority': 10},
    },
    'campaigns': {
        'exchange': 'campaigns',
        'routing_key': 'campaigns',
        'queue_arguments': {'x-max-priority': 10},
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 