#!/usr/bin/env python3
"""
Исправление конкретных проблем с Gmail и Mail.ru
"""

import os
import sys
import subprocess
import dns.resolver
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/vashsender')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

import django
django.setup()

from django.conf import settings
from decouple import config

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def check_ipv6_issues():
    """Проверка IPv6 проблем для Gmail"""
    print_section("ПРОВЕРКА IPv6 ПРОБЛЕМ ДЛЯ GMAIL")
    
    try:
        # Получаем IP сервера
        import socket
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        print(f"IP адрес сервера: {ip_address}")
        
        # Проверяем PTR запись для IPv4
        try:
            ptr_result = socket.gethostbyaddr(ip_address)
            print(f"✅ PTR запись для IPv4: {ptr_result[0]}")
        except Exception as e:
            print(f"❌ PTR запись для IPv4 не найдена: {e}")
        
        # Проверяем IPv6 адреса
        try:
            ipv6_addresses = socket.getaddrinfo(hostname, None, socket.AF_INET6)
            if ipv6_addresses:
                print(f"⚠️  Найдены IPv6 адреса: {len(ipv6_addresses)}")
                for addr in ipv6_addresses[:3]:  # Показываем первые 3
                    ipv6 = addr[4][0]
                    print(f"   IPv6: {ipv6}")
                    
                    # Проверяем PTR для IPv6
                    try:
                        ptr_result = socket.gethostbyaddr(ipv6)
                        print(f"   ✅ PTR для IPv6 {ipv6}: {ptr_result[0]}")
                    except Exception as e:
                        print(f"   ❌ PTR для IPv6 {ipv6} не найдена: {e}")
            else:
                print("✅ IPv6 адреса не найдены")
        except Exception as e:
            print(f"❌ Ошибка проверки IPv6: {e}")
            
    except Exception as e:
        print(f"❌ Ошибка получения IP: {e}")

def fix_ipv6_issues():
    """Исправление IPv6 проблем"""
    print_section("ИСПРАВЛЕНИЕ IPv6 ПРОБЛЕМ")
    
    # Создаем конфигурацию для отключения IPv6 в Postfix
    postfix_config = """
# Отключение IPv6 для исправления проблем с Gmail
# Добавьте в /etc/postfix/main.cf

# Принудительно используем только IPv4
inet_protocols = ipv4

# Отключаем IPv6 для SMTP
smtp_address_preference = ipv4
smtp_host_lookup = dns, native
disable_dns_lookups = no

# Настройки для улучшения доставляемости
smtp_helo_name = mail.vashsender.ru
smtpd_helo_required = yes
smtpd_helo_restrictions = permit_mynetworks, reject_invalid_helo_hostname, reject_non_fqdn_helo_hostname

# Настройки для аутентификации
smtpd_sasl_auth_enable = yes
smtpd_sasl_security_options = noanonymous
smtpd_sasl_local_domain = $myhostname

# Настройки для TLS
smtpd_tls_security_level = may
smtpd_tls_auth_only = no
smtpd_tls_received_header = yes
"""
    
    try:
        with open('/tmp/postfix_ipv4_config.txt', 'w') as f:
            f.write(postfix_config)
        print("✅ Конфигурация Postfix создана: /tmp/postfix_ipv4_config.txt")
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def fix_mailru_deliverability():
    """Исправление доставляемости в Mail.ru"""
    print_section("ИСПРАВЛЕНИЕ ДОСТАВЛЯЕМОСТИ В MAIL.RU")
    
    # Создаем специальные настройки для Mail.ru
    mailru_config = """
# СПЕЦИАЛЬНЫЕ НАСТРОЙКИ ДЛЯ MAIL.RU
# Добавьте в core/settings/production.py

# Mail.ru требует особого подхода
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.yandex.ru'  # Используем Yandex как релей
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'your-email@yandex.ru'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'your-email@yandex.ru'

# КРИТИЧЕСКИ ВАЖНО для Mail.ru
EMAIL_BATCH_SIZE = 5        # Очень маленькие батчи
EMAIL_RATE_LIMIT = 2        # Очень медленная отправка
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 300     # 5 минут между попытками
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60

# Дополнительные настройки для Mail.ru
EMAIL_USE_LOCALTIME = True
"""
    
    try:
        with open('/tmp/mailru_special_config.py', 'w') as f:
            f.write(mailru_config)
        print("✅ Специальная конфигурация для Mail.ru создана: /tmp/mailru_special_config.py")
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def create_mailru_headers_fix():
    """Создание исправлений заголовков для Mail.ru"""
    print_section("ИСПРАВЛЕНИЕ ЗАГОЛОВКОВ ДЛЯ MAIL.RU")
    
    headers_fix = """
# ИСПРАВЛЕНИЯ ЗАГОЛОВКОВ ДЛЯ MAIL.RU
# Примените в apps/campaigns/tasks.py в функции send_single_email

# Mail.ru требует особых заголовков
msg['Message-ID'] = f"<{uuid.uuid4()}@{from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'}>"
msg['Date'] = timezone.now().strftime('%a, %d %b %Y %H:%M:%S %z')
msg['MIME-Version'] = '1.0'

# Mail.ru любит эти заголовки
msg['X-Mailer'] = 'Microsoft Outlook Express 6.0'  # Имитируем Outlook
msg['X-Priority'] = '3'
msg['X-MSMail-Priority'] = 'Normal'
msg['Importance'] = 'normal'

# Mail.ru требует правильный Content-Type
msg['Content-Type'] = 'multipart/alternative; boundary="boundary"'

# Добавляем заголовки для предотвращения спама
msg['List-Unsubscribe'] = f'<mailto:unsubscribe@{from_email.split("@")[1] if "@" in from_email else "vashsender.ru"}>'
msg['Precedence'] = 'bulk'

# Mail.ru требует правильный From
msg['From'] = f"{sender_name} <{from_email}>"
msg['Reply-To'] = from_email

# ВКЛЮЧАЕМ DKIM подпись (обязательно для Mail.ru)
domain_name = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
msg = sign_email_with_dkim(msg, domain_name)
"""
    
    try:
        with open('/tmp/mailru_headers_fix.txt', 'w') as f:
            f.write(headers_fix)
        print("✅ Исправления заголовков для Mail.ru созданы: /tmp/mailru_headers_fix.txt")
    except Exception as e:
        print(f"❌ Ошибка создания исправлений: {e}")

def create_dns_fixes():
    """Создание DNS исправлений"""
    print_section("DNS ИСПРАВЛЕНИЯ")
    
    dns_fixes = """
# DNS ИСПРАВЛЕНИЯ ДЛЯ GMAIL И MAIL.RU

## 1. PTR ЗАПИСЬ (Reverse DNS)
# Добавьте в DNS провайдере для IP 146.185.196.123:
146.185.196.123.in-addr.arpa. IN PTR mail.vashsender.ru.

## 2. SPF ЗАПИСЬ (улучшенная)
# TXT запись для vashsender.ru:
"v=spf1 ip4:146.185.196.123 include:_spf.yandex.ru ~all"

## 3. DMARC ЗАПИСЬ (мягкая политика)
# TXT запись для _dmarc.vashsender.ru:
"v=DMARC1; p=none; rua=mailto:dmarc@vashsender.ru; ruf=mailto:dmarc@vashsender.ru; sp=none; adkim=r; aspf=r; pct=100;"

## 4. MX ЗАПИСИ
vashsender.ru. IN MX 10 mail.vashsender.ru.
vashsender.ru. IN MX 20 backup.vashsender.ru.

## 5. A ЗАПИСИ
mail.vashsender.ru. IN A 146.185.196.123
backup.vashsender.ru. IN A 146.185.196.123

## 6. DKIM ЗАПИСЬ
# TXT запись для default._domainkey.vashsender.ru:
"v=DKIM1; k=rsa; p=YOUR_PUBLIC_KEY_HERE"

## ПРОВЕРКА:
dig -x 146.185.196.123
dig TXT vashsender.ru
dig TXT _dmarc.vashsender.ru
dig MX vashsender.ru
dig TXT default._domainkey.vashsender.ru
"""
    
    try:
        with open('/tmp/dns_fixes.txt', 'w') as f:
            f.write(dns_fixes)
        print("✅ DNS исправления созданы: /tmp/dns_fixes.txt")
    except Exception as e:
        print(f"❌ Ошибка создания DNS исправлений: {e}")

def create_postfix_restart_script():
    """Создание скрипта перезапуска Postfix"""
    print_section("СКРИПТ ПЕРЕЗАПУСКА POSTFIX")
    
    restart_script = """#!/bin/bash
# ПЕРЕЗАПУСК POSTFIX С НОВЫМИ НАСТРОЙКАМИ

echo "🔄 Применение исправлений для Gmail и Mail.ru..."

# Останавливаем сервисы
sudo systemctl stop celery
sudo systemctl stop celerybeat

# Применяем конфигурацию Postfix
sudo cp /tmp/postfix_ipv4_config.txt /etc/postfix/main.cf.new
sudo mv /etc/postfix/main.cf /etc/postfix/main.cf.backup
sudo mv /etc/postfix/main.cf.new /etc/postfix/main.cf

# Перезапускаем Postfix
sudo systemctl restart postfix

# Проверяем статус
sudo systemctl status postfix

# Перезапускаем Celery
sudo systemctl start celery
sudo systemctl start celerybeat

# Очищаем очереди Redis
redis-cli FLUSHALL

echo "✅ Перезапуск завершен"
echo "📊 Проверьте логи: sudo tail -f /var/log/mail.log"
"""
    
    try:
        with open('/tmp/apply_fixes.sh', 'w') as f:
            f.write(restart_script)
        os.chmod('/tmp/apply_fixes.sh', 0o755)
        print("✅ Скрипт перезапуска создан: /tmp/apply_fixes.sh")
    except Exception as e:
        print(f"❌ Ошибка создания скрипта: {e}")

def test_current_delivery():
    """Тест текущей доставляемости"""
    print_section("ТЕСТ ТЕКУЩЕЙ ДОСТАВЛЯЕМОСТИ")
    
    try:
        from apps.campaigns.models import Campaign, CampaignRecipient
        from django.utils import timezone
        from datetime import timedelta
        
        # Проверяем последние кампании
        recent_campaigns = Campaign.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).order_by('-created_at')[:5]
        
        print(f"Найдено кампаний за последние 24 часа: {recent_campaigns.count()}")
        
        for campaign in recent_campaigns:
            print(f"\nКампания: {campaign.name}")
            print(f"  Статус: {campaign.status}")
            print(f"  Создана: {campaign.created_at}")
            
            # Проверяем получателей
            recipients = CampaignRecipient.objects.filter(campaign=campaign)
            sent_count = recipients.filter(is_sent=True).count()
            total_count = recipients.count()
            
            print(f"  Отправлено: {sent_count}/{total_count}")
            
            if total_count > 0:
                success_rate = (sent_count / total_count) * 100
                print(f"  Успешность: {success_rate:.1f}%")
        
    except Exception as e:
        print(f"❌ Ошибка проверки кампаний: {e}")

def main():
    """Основная функция"""
    print("🔧 ИСПРАВЛЕНИЕ ПРОБЛЕМ С GMAIL И MAIL.RU")
    print(f"Время: {datetime.now()}")
    
    # Проверяем текущие проблемы
    check_ipv6_issues()
    test_current_delivery()
    
    # Создаем исправления
    fix_ipv6_issues()
    fix_mailru_deliverability()
    create_mailru_headers_fix()
    create_dns_fixes()
    create_postfix_restart_script()
    
    print_section("ПЛАН ИСПРАВЛЕНИЙ")
    print("""
🚨 КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ:

1. GMAIL (IPv6 PTR ошибка):
   • Отключите IPv6 в Postfix
   • Добавьте PTR запись для IP
   • Примените конфигурацию из /tmp/postfix_ipv4_config.txt

2. MAIL.RU (спам):
   • Используйте Yandex как релей
   • Уменьшите скорость до 2 писем/сек
   • Примените заголовки из /tmp/mailru_headers_fix.txt
   • Добавьте DNS записи из /tmp/dns_fixes.txt

3. НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:
   • sudo bash /tmp/apply_fixes.sh
   • Настройте DNS записи
   • Протестируйте отправку

4. ПРОВЕРКА:
   • Отправьте тестовое письмо в Gmail
   • Отправьте тестовое письмо в Mail.ru
   • Проверьте логи: sudo tail -f /var/log/mail.log
""")

if __name__ == '__main__':
    main() 