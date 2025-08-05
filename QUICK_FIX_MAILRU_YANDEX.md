# 🚨 БЫСТРОЕ ИСПРАВЛЕНИЕ ПРОБЛЕМ С ДОСТАВЛЯЕМОСТЬЮ В MAIL.RU И YANDEX

## Проблема
Письма перестали доставляться в Mail.ru и Yandex из-за:
- Локального SMTP сервера без аутентификации
- Отсутствия SPF/DMARC записей в DNS
- Проблемных заголовков писем
- Высокой скорости отправки
- Отключенной DKIM подписи

## ✅ УЖЕ ИСПРАВЛЕНО В КОДЕ

### 1. Удалены проблемные заголовки писем
- Убраны `X-Mailer`, `X-Priority`, `X-MSMail-Priority`
- Убраны `Importance`, `List-Unsubscribe`, `Precedence`
- Оставлены только необходимые заголовки

### 2. Включена DKIM подпись
- Раскомментирована строка 835 в `apps/campaigns/tasks.py`
- DKIM подпись теперь добавляется ко всем письмам

### 3. Уменьшена скорость отправки
- `EMAIL_BATCH_SIZE`: 100 → 20 писем
- `EMAIL_RATE_LIMIT`: 50 → 5 писем в секунду
- `EMAIL_RETRY_DELAY`: 60 → 120 секунд

### 4. Улучшены задержки
- Между батчами: 0.8-1.2с → 1.5-2.5с
- Между письмами: 0.08-0.12с → 0.15-0.25с

## 🔧 НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ

### Шаг 1: Запустите диагностику
```bash
cd /var/www/vashsender
python fix_mailru_yandex_deliverability.py
```

### Шаг 2: Выберите внешний SMTP

#### Вариант A: Yandex SMTP (рекомендуется)
1. Создайте аккаунт на Yandex
2. Включите SMTP в настройках
3. Добавьте в `.env`:
```bash
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@yandex.ru
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=your-email@yandex.ru
```

#### Вариант B: Mail.ru SMTP
1. Создайте аккаунт на Mail.ru
2. Включите SMTP в настройках
3. Добавьте в `.env`:
```bash
EMAIL_HOST=smtp.mail.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@mail.ru
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=your-email@mail.ru
```

### Шаг 3: Настройте DNS записи

#### SPF запись (TXT для vashsender.ru):
```
"v=spf1 ip4:146.185.196.123 ~all"
```

#### DMARC запись (TXT для _dmarc.vashsender.ru):
```
"v=DMARC1; p=none; rua=mailto:dmarc@vashsender.ru; sp=none; adkim=r; aspf=r;"
```

#### MX запись:
```
vashsender.ru. IN MX 10 mail.vashsender.ru.
mail.vashsender.ru. IN A 146.185.196.123
```

### Шаг 4: Перезапустите сервисы
```bash
sudo systemctl stop celery
sudo systemctl stop celerybeat
redis-cli FLUSHALL
sudo systemctl restart postfix
sudo systemctl start celery
sudo systemctl start celerybeat
sudo systemctl restart gunicorn
```

### Шаг 5: Протестируйте
```bash
python test_mailru_yandex_delivery.py
```

## 📋 ПРОВЕРКА РЕЗУЛЬТАТОВ

### 1. Проверьте DNS записи:
```bash
dig TXT vashsender.ru
dig TXT _dmarc.vashsender.ru
dig MX vashsender.ru
```

### 2. Проверьте логи:
```bash
sudo tail -f /var/log/mail.log
sudo tail -f /var/log/celery.log
```

### 3. Отправьте тестовое письмо:
```bash
python manage.py shell -c "
from apps.campaigns.tasks import send_campaign
from apps.campaigns.models import Campaign
campaign = Campaign.objects.filter(name='Test Delivery Campaign').first()
if campaign:
    send_campaign(campaign.id)
"
```

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

### Скорость отправки
- **НЕ превышайте 5 писем в секунду**
- **Используйте батчи по 20 писем**
- **Добавляйте задержки между попытками**

### Качество списков
- Убедитесь, что списки контактов качественные
- Удалите несуществующие адреса
- Избегайте спам-ловушек

### Содержимое писем
- Избегайте спам-слов
- Используйте правильное соотношение текста и изображений
- Добавляйте ссылку для отписки

### Мониторинг
- Отслеживайте статистику доставляемости
- Проверяйте репутацию IP и домена
- Мониторьте жалобы на спам

## 🆘 ЕСЛИ ПРОБЛЕМЫ ОСТАЮТСЯ

### 1. Используйте готовые сервисы:
- **SendGrid** (рекомендуется)
- **Mailgun**
- **Amazon SES**

### 2. Настройте DKIM ключи:
```bash
python setup_dkim_for_deliverability.py
```

### 3. Проверьте репутацию:
- https://mxtoolbox.com/blacklists.aspx
- https://senderbase.org/
- https://www.senderscore.org/

### 4. Обратитесь в поддержку:
- **Mail.ru**: https://postmaster.mail.ru/
- **Яндекс**: https://yandex.ru/support/mail/spam-fighters/

## 📞 КОНТАКТЫ ДЛЯ ЭКСТРЕННОЙ ПОМОЩИ

Если ничего не помогает:
1. Создайте issue в GitHub
2. Обратитесь к администратору сервера
3. Рассмотрите возможность смены SMTP провайдера

---

**Время создания**: $(date)
**Статус**: Готово к применению
**Приоритет**: Критический 