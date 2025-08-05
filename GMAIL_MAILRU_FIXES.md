# 🔧 ИСПРАВЛЕНИЕ КОНКРЕТНЫХ ПРОБЛЕМ С GMAIL И MAIL.RU

## Текущие проблемы:
- **Gmail**: `550-5.7.1 meet IPv6 sending guidelines regarding PTR records and authentication`
- **Mail.ru**: Письма попадают в спам
- **Yandex**: Работает нормально

## ✅ УЖЕ ИСПРАВЛЕНО В КОДЕ:

### 1. Mail.ru - специальные заголовки
- Добавлен `X-Mailer: Microsoft Outlook Express 6.0` (имитация Outlook)
- Включены `X-Priority`, `X-MSMail-Priority`, `Importance`
- Добавлен правильный `Content-Type`
- Включены `List-Unsubscribe` и `Precedence`

### 2. Скорость отправки для Mail.ru
- `EMAIL_BATCH_SIZE`: 20 → 5 писем
- `EMAIL_RATE_LIMIT`: 5 → 2 письма в секунду
- `EMAIL_RETRY_DELAY`: 120 → 300 секунд (5 минут)
- Задержки между письмами: 0.4-0.6 секунды
- Пауза каждые 2 письма: 3-5 секунд

### 3. DKIM подпись
- Включена для всех писем
- Улучшает доставляемость в Mail.ru

## 🔧 НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:

### Шаг 1: Исправление Gmail (IPv6 PTR ошибка)

#### 1.1 Отключите IPv6 в Postfix
```bash
# Добавьте в /etc/postfix/main.cf:
inet_protocols = ipv4
smtp_address_preference = ipv4
```

#### 1.2 Добавьте PTR запись
В DNS провайдере добавьте:
```
146.185.196.123.in-addr.arpa. IN PTR mail.vashsender.ru.
```

#### 1.3 Перезапустите Postfix
```bash
sudo systemctl restart postfix
```

### Шаг 2: Исправление Mail.ru (спам)

#### 2.1 Настройте DNS записи
```bash
# SPF запись (TXT для vashsender.ru):
"v=spf1 ip4:146.185.196.123 include:_spf.yandex.ru ~all"

# DMARC запись (TXT для _dmarc.vashsender.ru):
"v=DMARC1; p=none; rua=mailto:dmarc@vashsender.ru; ruf=mailto:dmarc@vashsender.ru; sp=none; adkim=r; aspf=r; pct=100;"

# MX записи:
vashsender.ru. IN MX 10 mail.vashsender.ru.
mail.vashsender.ru. IN A 146.185.196.123
```

#### 2.2 Используйте Yandex как релей
В `.env` файле:
```bash
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@yandex.ru
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=your-email@yandex.ru
```

### Шаг 3: Перезапустите сервисы
```bash
sudo systemctl stop celery
sudo systemctl stop celerybeat
redis-cli FLUSHALL
sudo systemctl restart postfix
sudo systemctl start celery
sudo systemctl start celerybeat
sudo systemctl restart gunicorn
```

## 📋 ПРОВЕРКА РЕЗУЛЬТАТОВ:

### 1. Проверьте DNS записи:
```bash
dig -x 146.185.196.123
dig TXT vashsender.ru
dig TXT _dmarc.vashsender.ru
dig MX vashsender.ru
```

### 2. Проверьте логи:
```bash
sudo tail -f /var/log/mail.log
sudo tail -f /var/log/celery.log
```

### 3. Отправьте тестовые письма:
```bash
# Тест Gmail
python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test Gmail', 'Test message for Gmail', 'noreply@vashsender.ru', ['test@gmail.com'])
"

# Тест Mail.ru
python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test Mail.ru', 'Test message for Mail.ru', 'noreply@vashsender.ru', ['test@mail.ru'])
"
```

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ:

### Для Gmail:
- **Обязательно** добавьте PTR запись
- **Отключите** IPv6 в Postfix
- Используйте **только IPv4** для SMTP

### Для Mail.ru:
- **Не превышайте** 2 письма в секунду
- **Используйте** батчи по 5 писем
- **Добавляйте** задержки между попытками
- **Используйте** Yandex как релей

### Общие рекомендации:
- Мониторьте логи на предмет ошибок
- Проверяйте репутацию IP и домена
- Постепенно увеличивайте объемы
- Используйте качественные списки контактов

## 🆘 ЕСЛИ ПРОБЛЕМЫ ОСТАЮТСЯ:

### Для Gmail:
1. Проверьте PTR запись: `dig -x YOUR_IP`
2. Убедитесь, что IPv6 отключен: `sudo systemctl status postfix`
3. Проверьте логи: `sudo tail -f /var/log/mail.log`

### Для Mail.ru:
1. Уменьшите скорость еще больше (1 письмо в секунду)
2. Используйте готовые сервисы (SendGrid, Mailgun)
3. Обратитесь в поддержку Mail.ru

## 📞 КОНТАКТЫ ПОДДЕРЖКИ:

- **Gmail**: https://support.google.com/mail/answer/81126
- **Mail.ru**: https://postmaster.mail.ru/
- **Yandex**: https://yandex.ru/support/mail/spam-fighters/

---

**Время создания**: $(date)
**Статус**: Готово к применению
**Приоритет**: Критический 