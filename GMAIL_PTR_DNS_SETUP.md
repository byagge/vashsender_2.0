# 🔧 НАСТРОЙКА PTR ЗАПИСИ ДЛЯ GMAIL

## Проблема
Gmail возвращает ошибку:
```
550-5.7.1 meet IPv6 sending guidelines regarding PTR records and authentication
```

## Решение

### 1. Отключение IPv6 в Postfix

#### Автоматически:
```bash
chmod +x fix_gmail_ipv6_ptr.sh
sudo ./fix_gmail_ipv6_ptr.sh
```

#### Вручную:
```bash
# Добавьте в /etc/postfix/main.cf:
inet_protocols = ipv4
smtp_address_preference = ipv4

# Перезапустите Postfix:
sudo systemctl restart postfix
```

### 2. Настройка PTR записи (Reverse DNS)

#### 2.1 Определите ваш IP адрес:
```bash
curl ifconfig.me
# или
dig +short myip.opendns.com @resolver1.opendns.com
```

#### 2.2 Добавьте PTR запись в DNS провайдере:

**Для IP 146.185.196.123:**
```
146.185.196.123.in-addr.arpa. IN PTR mail.vashsender.ru.
```

**Для любого другого IP (замените YOUR_IP):**
```
YOUR_IP.in-addr.arpa. IN PTR mail.vashsender.ru.
```

#### 2.3 Примеры для разных DNS провайдеров:

**Cloudflare:**
1. Зайдите в панель Cloudflare
2. Выберите домен vashsender.ru
3. Перейдите в DNS → Records
4. Добавьте запись:
   - Type: PTR
   - Name: 146.185.196.123.in-addr.arpa
   - Content: mail.vashsender.ru
   - TTL: Auto

**Namecheap:**
1. Зайдите в панель Namecheap
2. Выберите домен vashsender.ru
3. Перейдите в Advanced DNS
4. Добавьте запись:
   - Type: PTR Record
   - Host: 146.185.196.123.in-addr.arpa
   - Value: mail.vashsender.ru

**GoDaddy:**
1. Зайдите в панель GoDaddy
2. Выберите домен vashsender.ru
3. Перейдите в DNS → Manage Zones
4. Добавьте запись:
   - Type: PTR
   - Name: 146.185.196.123.in-addr.arpa
   - Points to: mail.vashsender.ru

### 3. Проверка настроек

#### 3.1 Проверьте PTR запись:
```bash
dig -x 146.185.196.123
# Должно вернуть: mail.vashsender.ru.
```

#### 3.2 Проверьте настройки Postfix:
```bash
postconf -n | grep inet_protocols
# Должно вернуть: inet_protocols = ipv4
```

#### 3.3 Проверьте статус Postfix:
```bash
systemctl status postfix
# Должен быть активен
```

### 4. Тестирование

#### 4.1 Отправьте тестовое письмо:
```bash
python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test Gmail PTR', 'Testing PTR record fix', 'noreply@vashsender.ru', ['test@gmail.com'])
"
```

#### 4.2 Проверьте логи:
```bash
sudo tail -f /var/log/mail.log
```

### 5. Дополнительные DNS записи

Для полного решения добавьте также:

#### SPF запись:
```
vashsender.ru. IN TXT "v=spf1 ip4:146.185.196.123 ~all"
```

#### DMARC запись:
```
_dmarc.vashsender.ru. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc@vashsender.ru; sp=none; adkim=r; aspf=r;"
```

#### MX запись:
```
vashsender.ru. IN MX 10 mail.vashsender.ru.
mail.vashsender.ru. IN A 146.185.196.123
```

### 6. Проверка всех записей

```bash
# Проверка PTR
dig -x 146.185.196.123

# Проверка SPF
dig TXT vashsender.ru

# Проверка DMARC
dig TXT _dmarc.vashsender.ru

# Проверка MX
dig MX vashsender.ru

# Проверка A записи
dig A mail.vashsender.ru
```

### 7. Время распространения

- **PTR записи**: 10-30 минут
- **SPF записи**: 10-30 минут
- **DMARC записи**: 10-30 минут
- **MX записи**: 10-30 минут

### 8. Мониторинг

#### Проверьте репутацию IP:
- https://mxtoolbox.com/blacklists.aspx
- https://whatismyipaddress.com/blacklist-check

#### Проверьте доставляемость:
- Отправьте тестовое письмо в Gmail
- Проверьте папку "Входящие" и "Спам"
- Проверьте логи на ошибки

### 9. Если проблема остается

#### 9.1 Проверьте провайдера:
Некоторые провайдеры не позволяют настраивать PTR записи. В этом случае:
1. Обратитесь к провайдеру
2. Попросите настроить PTR запись
3. Рассмотрите смену провайдера

#### 9.2 Используйте внешний SMTP:
```bash
# В .env файле:
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@yandex.ru
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=your-email@yandex.ru
```

### 10. Контакты поддержки

- **Gmail**: https://support.google.com/mail/answer/81126
- **Ваш DNS провайдер**: Обратитесь в поддержку для настройки PTR

---

**Статус**: ✅ Готово к применению
**Приоритет**: 🚨 Критический
**Время создания**: $(date) 