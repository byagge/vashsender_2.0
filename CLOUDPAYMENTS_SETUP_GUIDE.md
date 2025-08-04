# Руководство по настройке CloudPayments

## Обзор

CloudPayments - это платежная система, интегрированная в vashsender для обработки подписок на тарифы. Система поддерживает как тестовый, так и продакшн режимы.

## Структура настроек

Настройки CloudPayments хранятся в модели `BillingSettings`:

- `cloudpayments_public_id` - Public ID для виджета
- `cloudpayments_api_secret` - API Secret для серверной части
- `cloudpayments_test_mode` - Режим работы (тест/продакшн)

## Способы настройки

### 1. Через Django Admin (Рекомендуется)

1. Войдите в Django Admin: `/admin/`
2. Перейдите в раздел "Billing" → "Настройки биллинга"
3. Заполните поля:
   - **Public ID CloudPayments**: Ваш Public ID из личного кабинета CloudPayments
   - **API Secret CloudPayments**: Ваш API Secret из личного кабинета CloudPayments
   - **Тестовый режим CloudPayments**: Включите для тестирования, отключите для продакшна

### 2. Через командную строку

#### Инициализация настроек:
```bash
# Создание настроек с Public ID
python manage.py init_cloudpayments_settings --public-id YOUR_PUBLIC_ID

# Установка API Secret
python manage.py init_cloudpayments_settings --api-secret YOUR_API_SECRET

# Переключение в продакшн режим
python manage.py init_cloudpayments_settings --production-mode

# Просмотр текущих настроек
python manage.py init_cloudpayments_settings
```

#### Пример полной настройки:
```bash
# Тестовый режим
python manage.py init_cloudpayments_settings \
    --public-id test_api_00000000000000000000002 \
    --api-secret your_test_api_secret \
    --test-mode

# Продакшн режим
python manage.py init_cloudpayments_settings \
    --public-id your_production_public_id \
    --api-secret your_production_api_secret \
    --production-mode
```

### 3. Программно через Django Shell

```python
from apps.billing.models import BillingSettings

# Получаем настройки
settings = BillingSettings.get_settings()

# Устанавливаем значения
settings.cloudpayments_public_id = 'your_public_id'
settings.cloudpayments_api_secret = 'your_api_secret'
settings.cloudpayments_test_mode = False  # False для продакшна
settings.save()
```

## Получение ключей CloudPayments

### 1. Регистрация в CloudPayments

1. Зарегистрируйтесь на [cloudpayments.ru](https://cloudpayments.ru)
2. Подтвердите email и заполните данные организации
3. Дождитесь модерации аккаунта

### 2. Получение ключей

1. Войдите в личный кабинет CloudPayments
2. Перейдите в раздел "Настройки" → "API"
3. Скопируйте:
   - **Public ID** - для виджета на фронтенде
   - **API Secret** - для серверной части

### 3. Тестовые ключи

Для разработки можно использовать тестовые ключи:
- **Public ID**: `test_api_00000000000000000000002`
- **API Secret**: `test_api_secret_key`

## Интеграция в шаблоны

### В purchase_confirmation.html

Настройки автоматически передаются в контекст:

```html
<!-- Public ID передается в JavaScript -->
<script>
payments.pay("charge", {
    publicId: '{{ cloudpayments_public_id }}',
    // ... остальные параметры
});
</script>

<!-- Индикатор тестового режима -->
{% if cloudpayments_test_mode %}
<div class="text-orange-600 font-semibold">ТЕСТОВЫЙ РЕЖИМ</div>
{% endif %}
```

### В других шаблонах

Для использования в других шаблонах добавьте в view:

```python
from apps.billing.models import BillingSettings

def your_view(request):
    billing_settings = BillingSettings.get_settings()
    context = {
        'cloudpayments_public_id': billing_settings.cloudpayments_public_id,
        'cloudpayments_test_mode': billing_settings.cloudpayments_test_mode,
    }
    return render(request, 'your_template.html', context)
```

## Безопасность

### 1. Хранение ключей

- **API Secret** никогда не должен передаваться на фронтенд
- Используйте переменные окружения для продакшна
- Регулярно обновляйте ключи

### 2. Проверка подписи

Все webhook'и от CloudPayments проверяются на подлинность:

```python
from apps.billing.cloudpayments import CloudPaymentsService

service = CloudPaymentsService()
is_valid = service.verify_signature(data, signature)
```

### 3. CSP настройки

В `settings.py` добавьте домен CloudPayments:

```python
CSP_DEFAULT_SRC = ("'self'", "https://widget.cloudpayments.ru")
CSP_SCRIPT_SRC = ("'self'", "https://widget.cloudpayments.ru")
```

## Тестирование

### 1. Тестовые карты

- **Успешная оплата**: `4111 1111 1111 1111`
- **Неуспешная оплата**: `4444 4444 4444 4444`
- **Любая будущая дата** (например, `12/25`)
- **Любой CVC** (например, `123`)

### 2. Тестовый файл

Используйте `test_cloudpayments.html` для изолированного тестирования:

```bash
# Откройте в браузере
open test_cloudpayments.html
```

### 3. Логирование

Включите логирование для отладки:

```python
import logging
logger = logging.getLogger('cloudpayments')
logger.setLevel(logging.DEBUG)
```

## Переход в продакшн

### 1. Подготовка

1. Получите продакшн ключи в CloudPayments
2. Настройте webhook URL в личном кабинете
3. Протестируйте на тестовых данных

### 2. Переключение

```bash
# Переключение в продакшн режим
python manage.py init_cloudpayments_settings \
    --public-id your_production_public_id \
    --api-secret your_production_api_secret \
    --production-mode
```

### 3. Проверка

1. Убедитесь, что тестовый режим отключен
2. Проверьте работу с реальными картами
3. Мониторьте логи транзакций

## Устранение неполадок

### 1. "Public ID не установлен"

```bash
python manage.py init_cloudpayments_settings --public-id YOUR_PUBLIC_ID
```

### 2. "API Secret не установлен"

```bash
python manage.py init_cloudpayments_settings --api-secret YOUR_API_SECRET
```

### 3. Ошибки виджета

- Проверьте загрузку скрипта CloudPayments
- Убедитесь в правильности Public ID
- Проверьте CSP настройки

### 4. Ошибки webhook'ов

- Проверьте правильность API Secret
- Убедитесь в корректности URL webhook'а
- Проверьте логи сервера

## Полезные команды

```bash
# Просмотр текущих настроек
python manage.py init_cloudpayments_settings

# Сброс к тестовым настройкам
python manage.py init_cloudpayments_settings \
    --public-id test_api_00000000000000000000002 \
    --test-mode

# Проверка миграций
python manage.py showmigrations billing

# Создание резервной копии настроек
python manage.py dumpdata billing.BillingSettings --indent=2 > billing_settings_backup.json
``` 