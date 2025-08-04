# Архитектура Celery в VashSender

## Обзор

VashSender использует Celery для асинхронной обработки задач. Все задачи автоматически обнаруживаются из всех Django приложений и распределяются по соответствующим очередям.

## Структура очередей

### 1. Очередь `import` (Приоритет: 5)
**Назначение**: Импорт и валидация контактов
**Приложение**: `apps.mailer`
**Задачи**:
- `import_contacts_async` - асинхронный импорт с валидацией
- `validate_contact_batch` - валидация батча контактов

**Характеристики**:
- Медленные задачи (2-6 сек на email)
- Требует много ресурсов (DNS, SMTP проверки)
- Рекомендуемый concurrency: 2-4

### 2. Очередь `email` (Приоритет: 10)
**Назначение**: Отправка email писем
**Приложение**: `apps.campaigns`
**Задачи**:
- `send_email_batch` - отправка батча писем
- `send_single_email` - отправка одного письма

**Характеристики**:
- Средние задачи (1-5 сек на письмо)
- Требует SMTP соединения
- Рекомендуемый concurrency: 4-8

### 3. Очередь `campaigns` (Приоритет: 10)
**Назначение**: Управление кампаниями
**Приложение**: `apps.campaigns`
**Задачи**:
- `send_campaign` - запуск кампании
- `test_celery` - тестовая задача

**Характеристики**:
- Быстрые задачи (координация)
- Управляет другими задачами
- Рекомендуемый concurrency: 2-4

### 4. Очередь `default` (Приоритет: 0)
**Назначение**: Общие задачи
**Характеристики**:
- Задачи без явного указания очереди
- Рекомендуемый concurrency: 1-2

## Периодические задачи (Celery Beat)

### Мониторинг и обслуживание
- `monitor_campaign_progress` - каждые 5 минут
- `cleanup_stuck_campaigns` - каждые 10 минут  
- `cleanup_smtp_connections` - каждые 10 минут

## Конфигурация

### Настройки в `core/celery.py`
```python
# Таймауты задач
task_time_limit=30 * 60,      # 30 минут максимум
task_soft_time_limit=25 * 60, # 25 минут мягкий лимит

# Настройки воркера
worker_prefetch_multiplier=1,
worker_max_tasks_per_child=1000,
```

### Роутинг задач
```python
app.conf.task_routes = {
    'apps.campaigns.tasks.send_campaign': {'queue': 'campaigns'},
    'apps.campaigns.tasks.send_email_batch': {'queue': 'email'},
    'apps.campaigns.tasks.send_single_email': {'queue': 'email'},
    'apps.mailer.tasks.import_contacts_async': {'queue': 'import'},
    'apps.mailer.tasks.validate_contact_batch': {'queue': 'import'},
}
```

## Сценарии запуска

### 1. Разработка (один воркер)
```bash
# Запуск всех очередей в одном воркере
celery -A core worker -Q default,email,campaigns,import -l info --concurrency=4
```

### 2. Продакшн (разделенные воркеры)
```bash
# Воркер для импорта
celery -A core worker -Q import -l info --concurrency=2

# Воркер для email
celery -A core worker -Q email -l info --concurrency=4

# Воркер для кампаний
celery -A core worker -Q campaigns -l info --concurrency=2
```

### 3. Автоматический запуск
```bash
# Используйте скрипты
./start_all_workers.sh
# или
./start_celery_workers.sh
```

## Мониторинг

### Проверка статуса
```bash
# Активные задачи
celery -A core inspect active

# Статистика воркеров
celery -A core inspect stats

# Очереди
celery -A core inspect active_queues
```

### Логирование
```bash
# Просмотр логов в реальном времени
tail -f celery.log

# Фильтрация по очереди
grep "import" celery.log
```

## Оптимизация производительности

### 1. Настройка concurrency
- **import**: 2-4 процесса (медленные задачи)
- **email**: 4-8 процессов (средние задачи)
- **campaigns**: 2-4 процесса (быстрые задачи)

### 2. Мониторинг ресурсов
```bash
# Проверка использования памяти
ps aux | grep celery

# Проверка нагрузки
htop
```

### 3. Масштабирование
- Увеличивайте concurrency для email очереди
- Добавляйте отдельные серверы для разных очередей
- Используйте Redis Cluster для больших нагрузок

## Устранение неполадок

### Проблема: Задачи не выполняются
```bash
# Проверьте статус воркеров
celery -A core inspect ping

# Проверьте подключение к брокеру
celery -A core inspect active_queues
```

### Проблема: Медленная обработка
```bash
# Увеличьте concurrency
celery -A core worker -Q email -l info --concurrency=8

# Проверьте нагрузку на CPU/память
top
```

### Проблема: Зависшие задачи
```bash
# Очистка зависших кампаний
python manage.py shell
>>> from apps.campaigns.tasks import cleanup_stuck_campaigns
>>> cleanup_stuck_campaigns.delay()
```

## Безопасность

### 1. Изоляция задач
- Каждая очередь обрабатывается отдельно
- Задачи не могут влиять друг на друга

### 2. Таймауты
- Все задачи имеют жесткие таймауты
- Автоматическая очистка зависших задач

### 3. Логирование
- Все действия логируются
- Отслеживание ошибок и повторных попыток

## Будущие улучшения

1. **Горизонтальное масштабирование** - несколько серверов
2. **Приоритизация задач** - важные задачи обрабатываются первыми
3. **Мониторинг в реальном времени** - веб-интерфейс для отслеживания
4. **Автоматическое масштабирование** - динамическое изменение concurrency
5. **Географическое распределение** - воркеры в разных регионах 