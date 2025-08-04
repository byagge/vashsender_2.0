# Настройка доставляемости писем

## Проблема
Письма начали попадать в спам в Mail.ru и перестали доставляться в Яндекс.

## Решения

### 1. Настройка SPF записи
Добавьте в DNS запись типа TXT для домена vashsender.ru:

```
v=spf1 ip4:YOUR_SERVER_IP ~all
```

Если используете несколько серверов:
```
v=spf1 ip4:YOUR_SERVER_IP1 ip4:YOUR_SERVER_IP2 ~all
```

### 2. Настройка DKIM
Создайте DKIM ключи и добавьте публичный ключ в DNS:

```
# Генерация ключей
openssl genrsa -out private.key 2048
openssl rsa -in private.key -pubout -out public.key

# DNS запись (TXT для default._domainkey.vashsender.ru)
v=DKIM1; k=rsa; p=PUBLIC_KEY_CONTENT
```

### 3. Настройка DMARC
Добавьте DMARC запись в DNS:

```
# TXT запись для _dmarc.vashsender.ru
v=DMARC1; p=quarantine; rua=mailto:dmarc@vashsender.ru; ruf=mailto:dmarc@vashsender.ru; sp=quarantine; adkim=r; aspf=r;
```

### 4. Настройка PTR записи (Reverse DNS)
Убедитесь, что IP адрес сервера имеет правильную PTR запись:

```
# Проверка
nslookup YOUR_SERVER_IP
# Должен вернуть vashsender.ru или mail.vashsender.ru
```

### 5. Настройка MX записи
Добавьте MX запись для домена:

```
# MX запись
vashsender.ru. IN MX 10 mail.vashsender.ru.
```

### 6. Настройка сервера

#### Postfix конфигурация
Добавьте в `/etc/postfix/main.cf`:

```
# Основные настройки
myhostname = mail.vashsender.ru
mydomain = vashsender.ru
myorigin = $mydomain

# Настройки для доставляемости
smtp_helo_name = mail.vashsender.ru
smtp_host_lookup = dns, native
disable_dns_lookups = no

# Настройки для предотвращения спама
smtpd_helo_required = yes
smtpd_helo_restrictions = permit_mynetworks, reject_invalid_helo_hostname, reject_non_fqdn_helo_hostname

# Настройки для аутентификации
smtpd_sasl_auth_enable = yes
smtpd_sasl_security_options = noanonymous
smtpd_sasl_local_domain = $myhostname

# Настройки для TLS
smtpd_tls_cert_file = /etc/ssl/certs/vashsender.crt
smtpd_tls_key_file = /etc/ssl/private/vashsender.key
smtpd_tls_security_level = may
smtpd_tls_auth_only = no
smtpd_tls_received_header = yes
```

#### OpenDKIM конфигурация
Создайте `/etc/opendkim.conf`:

```
# Основные настройки
Domain                  vashsender.ru
KeyFile                 /etc/opendkim/keys/vashsender.ru/default.private
Selector                default
SignHeaders             From,To,Subject,Date,Message-ID
Canonicalization        relaxed/relaxed
Mode                    s
SubDomains             No
Socket                  inet:8891@localhost
PidFile                 /var/run/opendkim/opendkim.pid
```

### 7. Проверка настроек

#### Проверка SPF:
```bash
dig TXT vashsender.ru
```

#### Проверка DKIM:
```bash
dig TXT default._domainkey.vashsender.ru
```

#### Проверка DMARC:
```bash
dig TXT _dmarc.vashsender.ru
```

#### Проверка PTR:
```bash
nslookup YOUR_SERVER_IP
```

### 8. Мониторинг репутации

#### Проверка IP в черных списках:
- https://mxtoolbox.com/blacklists.aspx
- https://whatismyipaddress.com/blacklist-check

#### Проверка репутации домена:
- https://senderbase.org/
- https://www.senderscore.org/

### 9. Дополнительные рекомендации

1. **Постепенное увеличение объема**: Начинайте с малых объемов (50-100 писем в день) и постепенно увеличивайте.

2. **Качество списков**: Убедитесь, что списки контактов качественные и не содержат несуществующих адресов.

3. **Содержимое писем**: Избегайте спам-слов, используйте правильное соотношение текста и изображений.

4. **Отписка**: Всегда добавляйте ссылку для отписки.

5. **Мониторинг**: Отслеживайте статистику доставляемости, открытий и кликов.

### 10. Настройки в коде

В файле `core/settings/production.py` убедитесь, что:

```python
# Правильные настройки SMTP
EMAIL_HOST = 'mail.vashsender.ru'  # или IP сервера
EMAIL_PORT = 587  # или 25 для нешифрованного
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'noreply@vashsender.ru'
EMAIL_HOST_PASSWORD = 'your_password'
DEFAULT_FROM_EMAIL = 'noreply@vashsender.ru'

# Настройки для доставляемости
EMAIL_BATCH_SIZE = 50  # Уменьшить размер батча
EMAIL_RATE_LIMIT = 10  # Уменьшить скорость отправки
```

### 11. Проверка настроек

После внесения изменений проверьте:

1. Перезапустите Postfix: `sudo systemctl restart postfix`
2. Перезапустите OpenDKIM: `sudo systemctl restart opendkim`
3. Проверьте логи: `sudo tail -f /var/log/mail.log`
4. Отправьте тестовое письмо и проверьте заголовки

### 12. Контакты для решения проблем

- **Mail.ru**: https://postmaster.mail.ru/
- **Яндекс**: https://yandex.ru/support/mail/spam-fighters/
- **Gmail**: https://support.google.com/mail/answer/81126 