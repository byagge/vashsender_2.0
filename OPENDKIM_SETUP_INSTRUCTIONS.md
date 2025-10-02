# Настройка автоматической подписи DKIM через OpenDKIM

## Быстрая настройка

### 1. Проверка текущего состояния
```bash
sudo python3 check_dkim_status.py
```

### 2. Автоматическая настройка OpenDKIM
```bash
sudo python3 setup_opendkim_auto.py
```

### 3. Проверка работы
```bash
# Проверить статус служб
sudo systemctl status opendkim
sudo systemctl status postfix

# Проверить логи
sudo journalctl -u opendkim -f
```

## Что делает автоматическая настройка

### 1. Создает конфигурацию OpenDKIM (`/etc/opendkim.conf`)
```
Syslog                  yes
SyslogSuccess           yes
LogWhy                  yes
Canonicalization        relaxed/simple
ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
InternalHosts           refile:/etc/opendkim/TrustedHosts
KeyTable                refile:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
Mode                    sv
PidFile                 /var/run/opendkim/opendkim.pid
SignatureAlgorithm      rsa-sha256
UserID                  opendkim:opendkim
Socket                  inet:12301@localhost
```

### 2. Создает таблицы подписи
- **KeyTable** (`/etc/opendkim/KeyTable`) - связывает селекторы с ключами
- **SigningTable** (`/etc/opendkim/SigningTable`) - указывает какие домены подписывать
- **TrustedHosts** (`/etc/opendkim/TrustedHosts`) - доверенные хосты

### 3. Настраивает интеграцию с Postfix
Добавляет в `/etc/postfix/main.cf`:
```
milter_protocol = 2
milter_default_action = accept
smtpd_milters = inet:localhost:12301
non_smtpd_milters = inet:localhost:12301
```

### 4. Устанавливает правильные права доступа
```bash
chown -R opendkim:opendkim /etc/opendkim
chmod 600 /etc/opendkim/keys/*/*
chmod 644 /etc/opendkim/KeyTable /etc/opendkim/SigningTable /etc/opendkim/TrustedHosts
```

## Ручная настройка (если автоматическая не сработала)

### 1. Установка OpenDKIM
```bash
sudo apt update
sudo apt install opendkim opendkim-tools
```

### 2. Создание пользователя и группы
```bash
sudo adduser opendkim
sudo addgroup opendkim
```

### 3. Создание директорий
```bash
sudo mkdir -p /etc/opendkim/keys
sudo chown -R opendkim:opendkim /etc/opendkim
```

### 4. Копирование ключей из apps/emails
```bash
# Для каждого домена из базы данных
sudo cp /etc/opendkim/keys/domain.com/vashsender.private /etc/opendkim/keys/domain.com/
sudo cp /etc/opendkim/keys/domain.com/vashsender.txt /etc/opendkim/keys/domain.com/
sudo chown opendkim:opendkim /etc/opendkim/keys/domain.com/*
sudo chmod 600 /etc/opendkim/keys/domain.com/*.private
```

### 5. Создание конфигурационных файлов

#### `/etc/opendkim/KeyTable`
```
vashsender._domainkey.domain.com domain.com:vashsender:/etc/opendkim/keys/domain.com/vashsender.private
```

#### `/etc/opendkim/SigningTable`
```
*@domain.com vashsender._domainkey.domain.com
```

#### `/etc/opendkim/TrustedHosts`
```
127.0.0.1
::1
localhost
*.vashsender.ru
vashsender.ru
```

### 6. Запуск служб
```bash
sudo systemctl enable opendkim
sudo systemctl start opendkim
sudo systemctl restart postfix
```

## Проверка работы

### 1. Проверка статуса служб
```bash
sudo systemctl status opendkim
sudo systemctl status postfix
```

### 2. Проверка сокета milter
```bash
sudo netstat -tlnp | grep 12301
```

### 3. Отправка тестового письма
```bash
# Через Django shell
python3 manage.py shell
>>> from apps.campaigns.tasks import send_single_email
>>> # Отправить тестовое письмо и проверить заголовки
```

### 4. Проверка заголовков письма
В полученном письме должен быть заголовок:
```
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/simple; d=domain.com; s=vashsender; ...
```

## Устранение проблем

### OpenDKIM не запускается
```bash
# Проверить логи
sudo journalctl -u opendkim -n 50

# Проверить конфигурацию
sudo opendkim -t /etc/opendkim.conf

# Проверить права доступа
sudo ls -la /etc/opendkim/keys/*/
```

### Postfix не подключается к milter
```bash
# Проверить настройки Postfix
sudo postconf | grep milter

# Проверить логи Postfix
sudo tail -f /var/log/mail.log
```

### DKIM подпись не добавляется
1. Убедитесь, что домен в From совпадает с доменом в SigningTable
2. Проверьте, что приватный ключ существует и доступен для чтения
3. Проверьте логи OpenDKIM на ошибки

## Настройки Django

В `core/settings/base.py` должно быть:
```python
EMAIL_USE_OPENDKIM = True  # Использовать OpenDKIM для подписи
EMAIL_HOST = 'localhost'   # Отправка через локальный MTA
EMAIL_PORT = 25           # Стандартный порт SMTP
EMAIL_USE_TLS = False     # Без TLS для локального MTA
EMAIL_USE_SSL = False     # Без SSL для локального MTA
```

## Проверка DNS

Убедитесь, что DNS записи для DKIM настроены правильно:
```bash
dig TXT vashsender._domainkey.domain.com
```

Запись должна содержать:
```
v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
```
