# Диагностика и исправление DKIM подписи

## Текущая ситуация
- OpenDKIM настроен и запущен ✅
- Ключи существуют в `/etc/opendkim/keys/` ✅  
- KeyTable и SigningTable настроены ✅
- Но письма не подписываются ❌

## Быстрое исправление

### 1. Активируйте виртуальное окружение и запустите диагностику:
```bash
cd /var/www/vashsender
source venv/bin/activate
chmod +x fix_dkim.sh
./fix_dkim.sh
```

### 2. Если скрипты не работают, выполните вручную:

#### Проверьте настройки Django:
```bash
source venv/bin/activate
python3 -c "
import os, sys
sys.path.append('/var/www/vashsender')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')
import django
django.setup()
from django.conf import settings
print('EMAIL_HOST:', getattr(settings, 'EMAIL_HOST', 'НЕ ЗАДАНО'))
print('EMAIL_PORT:', getattr(settings, 'EMAIL_PORT', 'НЕ ЗАДАНО'))
print('EMAIL_USE_OPENDKIM:', getattr(settings, 'EMAIL_USE_OPENDKIM', 'НЕ ЗАДАНО'))
"
```

#### Проверьте статус служб:
```bash
sudo systemctl status opendkim
sudo systemctl status postfix
sudo netstat -tlnp | grep 12301
```

#### Проверьте настройки Postfix milter:
```bash
sudo postconf -n | grep milter
```

Должно быть:
```
milter_default_action = accept
milter_protocol = 2
non_smtpd_milters = inet:127.0.0.1:12301
smtpd_milters = inet:127.0.0.1:12301
```

### 3. Если milter не настроен, добавьте:
```bash
sudo postconf -e "milter_protocol = 2"
sudo postconf -e "milter_default_action = accept"
sudo postconf -e "smtpd_milters = inet:127.0.0.1:12301"
sudo postconf -e "non_smtpd_milters = inet:127.0.0.1:12301"
sudo systemctl reload postfix
```

### 4. Проверьте логи при отправке:
```bash
# В одном терминале следите за логами:
sudo journalctl -u opendkim -f

# В другом терминале отправьте тестовое письмо:
source venv/bin/activate
python3 manage.py shell
>>> from apps.campaigns.tasks import send_single_email
>>> # Найдите ID кампании и контакта для теста
```

## Возможные проблемы и решения

### Проблема 1: OpenDKIM не подписывает письма
**Симптомы:** В логах нет записей о подписи
**Решение:**
```bash
# Проверьте SigningTable
sudo cat /etc/opendkim/SigningTable

# Должно быть что-то вроде:
# *@monocode.app vashsender._domainkey.monocode.app

# Если пусто или неправильно, обновите:
source venv/bin/activate
python3 -c "
import os, sys
sys.path.append('/var/www/vashsender')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')
import django
django.setup()
from apps.emails.models import Domain

domains = Domain.objects.filter(dkim_verified=True)
signing_table = ''
for domain in domains:
    signing_table += f'*@{domain.domain_name} {domain.dkim_selector}._domainkey.{domain.domain_name}\n'

with open('/etc/opendkim/SigningTable', 'w') as f:
    f.write(signing_table)
print('SigningTable обновлен')
"

sudo systemctl restart opendkim
```

### Проблема 2: Postfix не передает письма через milter
**Симптомы:** В логах OpenDKIM нет активности при отправке
**Решение:**
```bash
# Проверьте main.cf
sudo grep milter /etc/postfix/main.cf

# Если настроек нет, добавьте:
echo "
milter_protocol = 2
milter_default_action = accept
smtpd_milters = inet:127.0.0.1:12301
non_smtpd_milters = inet:127.0.0.1:12301
" | sudo tee -a /etc/postfix/main.cf

sudo systemctl reload postfix
```

### Проблема 3: Домен не найден в базе данных
**Симптомы:** "Domain X not found in database"
**Решение:**
```bash
source venv/bin/activate
python3 manage.py shell
>>> from apps.emails.models import Domain
>>> # Проверьте домены
>>> for d in Domain.objects.all():
...     print(f"{d.domain_name} - DKIM: {d.dkim_verified}")
>>> 
>>> # Если нужного домена нет, добавьте через админку Django
>>> # или создайте программно
```

### Проблема 4: Права доступа к ключам
**Симптомы:** "Permission denied" при чтении ключей
**Решение:**
```bash
sudo chown -R opendkim:opendkim /etc/opendkim/keys
sudo chmod 600 /etc/opendkim/keys/*/*.private
sudo chmod 644 /etc/opendkim/keys/*/*.txt
```

## Тестирование

### 1. Отправьте тестовое письмо через командную строку:
```bash
echo "Test message" | mail -s "DKIM Test" -r "test@monocode.app" test@gmail.com
```

### 2. Проверьте заголовки полученного письма:
Должен быть заголовок:
```
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/simple; d=monocode.app; s=vashsender; ...
```

### 3. Проверьте через онлайн-инструменты:
- https://www.mail-tester.com/
- https://dkimvalidator.com/

## Логи для диагностики

### OpenDKIM логи:
```bash
sudo journalctl -u opendkim -n 50
```

### Mail логи:
```bash
sudo tail -f /var/log/mail.log
```

### Postfix логи:
```bash
sudo journalctl -u postfix -n 50
```

## Если ничего не помогает

### Временно включите in-app подпись:
В `core/settings/production.py` или `base.py`:
```python
EMAIL_USE_OPENDKIM = False  # Временно отключить OpenDKIM
```

Это заставит Django подписывать письма самостоятельно через dkimpy, пока вы не исправите OpenDKIM.
