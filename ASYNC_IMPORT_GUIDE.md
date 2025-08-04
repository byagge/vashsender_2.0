# Асинхронный импорт контактов с полной валидацией

## Обзор

Реализована новая система асинхронного импорта контактов, которая решает проблему таймаутов при загрузке больших файлов (5000+ контактов). Система использует Celery для фоновой обработки и обеспечивает полную валидацию каждого email адреса.

## Основные изменения

### 1. Асинхронная обработка
- Импорт теперь выполняется в фоновом режиме через Celery
- Нет ограничений по времени выполнения (ранее таймаут на ~300 контактах)
- Поддержка файлов любого размера

### 2. Полная валидация
- Каждый email проходит полную валидацию через `validate_email_production()`
- Проверка синтаксиса, MX записей, disposable доменов
- Корректная классификация: valid/invalid/blacklist

### 3. Отслеживание прогресса
- Реальное время обновления прогресса
- Детальная статистика по типам контактов
- API для проверки статуса задач

## Архитектура

### Модели
- `ImportTask` - отслеживание задач импорта
- `Contact` - контакты с валидированными статусами
- `ContactList` - списки контактов

### API Endpoints
- `POST /contactlists/{id}/import/` - асинхронный импорт с валидацией
- `POST /contactlists/{id}/import-fast/` - быстрый импорт без валидации
- `GET /contactlists/{id}/import-status/` - статус задач импорта
- `GET /contactlists/import-tasks/` - все задачи пользователя

### Celery Tasks
- `import_contacts_async` - основная задача импорта
- `validate_contact_batch` - валидация батча контактов

## Использование

### 1. Импорт с валидацией (рекомендуется)
```javascript
// Фронтенд автоматически выбирает асинхронный импорт
const formData = new FormData();
formData.append('file', file);

const response = await fetch('/lists/api/contactlists/1/import/', {
    method: 'POST',
    body: formData
});

// Получаем task_id для отслеживания
const result = await response.json();
console.log('Task ID:', result.task_id);
```

### 2. Быстрый импорт (без валидации)
```javascript
const response = await fetch('/lists/api/contactlists/1/import-fast/', {
    method: 'POST',
    body: formData
});
```

### 3. Отслеживание прогресса
```javascript
const statusResponse = await fetch('/lists/api/contactlists/1/import-status/');
const status = await statusResponse.json();

// Получаем последнюю задачу
const latestTask = status.tasks[0];
console.log('Progress:', latestTask.progress_percentage + '%');
console.log('Status:', latestTask.status);
```

## Настройка Celery

### 1. Быстрый запуск всех воркеров (рекомендуется)
```bash
# Делаем скрипт исполняемым
chmod +x start_all_workers.sh

# Запускаем все воркеры
./start_all_workers.sh
```

### 2. Интерактивный менеджер воркеров
```bash
# Делаем скрипт исполняемым
chmod +x start_celery_workers.sh

# Запускаем менеджер
./start_celery_workers.sh
```

### 3. Ручной запуск отдельных воркеров
```bash
# Запуск воркера для очереди импорта
celery -A core worker -Q import -l info

# Запуск воркера для email
celery -A core worker -Q email -l info

# Запуск воркера для кампаний
celery -A core worker -Q campaigns -l info

# Запуск всех очередей в одном воркере
celery -A core worker -Q default,email,campaigns,import -l info
```

### 2. Мониторинг задач
```bash
# Просмотр активных задач
celery -A core inspect active

# Просмотр статистики
celery -A core inspect stats
```

## Валидация email

### Алгоритм валидации
1. **Синтаксическая проверка** - соответствие RFC 5321/5322
2. **Проверка домена** - зарезервированные и disposable домены
3. **DNS проверка** - MX записи для приема почты
4. **SMTP проверка** - реальная проверка существования email адреса
5. **Классификация** - valid/invalid/blacklist

### Типы статусов
- `valid` - email прошел все проверки
- `invalid` - email не прошел валидацию
- `blacklist` - email в disposable домене

## Производительность

### Оптимизации
- Батчинг контактов (100 контактов за раз)
- Кэширование DNS запросов
- Быстрая проверка существующих email
- Обновление прогресса каждые 100 контактов

### Ожидаемая скорость
- ~20-50 email/сек с глубокой валидацией (включая SMTP)
- ~50-100 email/сек с полной валидацией (без SMTP)
- ~1000+ email/сек для быстрого импорта
- Поддержка файлов до 100,000+ контактов

## Мониторинг и отладка

### Логи
```python
# В tasks.py
print(f"Error in batch create: {e}")
print(f"Error processing email {email}: {e}")
```

### Проверка статуса
```python
from apps.mailer.models import ImportTask

# Получить все задачи пользователя
tasks = ImportTask.objects.filter(contact_list__owner=user)

# Получить статистику
for task in tasks:
    print(f"Task {task.id}: {task.status}")
    print(f"  Progress: {task.progress_percentage}%")
    print(f"  Imported: {task.imported_count}")
    print(f"  Invalid: {task.invalid_count}")
```

## Тестирование

### Запуск теста
```bash
python test_async_import.py
```

### Проверка результатов
```python
from apps.mailer.models import Contact, ContactList

# Получить контакты по статусам
contacts = Contact.objects.filter(contact_list=contact_list)
valid_count = contacts.filter(status='valid').count()
invalid_count = contacts.filter(status='invalid').count()
blacklist_count = contacts.filter(status='blacklist').count()
```

## Миграции

### Добавление поля celery_task_id
```bash
python manage.py makemigrations mailer
python manage.py migrate
```

## Безопасность

### Ограничения
- Проверка прав доступа к списку контактов
- Валидация размера файла
- Очистка временных файлов
- Защита от CSRF атак

### Рекомендации
- Используйте HTTPS в продакшене
- Настройте лимиты на размер файлов
- Мониторьте использование ресурсов
- Регулярно очищайте старые задачи

## Устранение неполадок

### Проблема: Задача не запускается
**Решение:**
1. Проверьте, что Celery воркер запущен
2. Проверьте подключение к брокеру (Redis/RabbitMQ)
3. Проверьте логи воркера

### Проблема: Задача зависает
**Решение:**
1. Проверьте таймауты в настройках Celery
2. Увеличьте `task_time_limit` если нужно
3. Проверьте доступность DNS серверов

### Проблема: Низкая скорость валидации
**Решение:**
1. Увеличьте количество воркеров
2. Настройте DNS кэширование
3. Используйте быстрый импорт для больших файлов

## Будущие улучшения

1. **Параллельная валидация** - несколько email одновременно
2. **Умная валидация** - пропуск известных доменов
3. **Вебхуки** - уведомления о завершении
4. **Отмена задач** - возможность остановить импорт
5. **Возобновление** - продолжение прерванного импорта 