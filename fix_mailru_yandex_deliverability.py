#!/usr/bin/env python3
"""
Экстренное исправление проблем с доставляемостью в Mail.ru и Yandex
"""

import os
import sys
import smtplib
import dns.resolver
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import subprocess

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

def check_current_smtp_settings():
    """Проверка текущих SMTP настроек"""
    print_section("ТЕКУЩИЕ SMTP НАСТРОЙКИ")
    
    print(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'НЕ УСТАНОВЛЕН')}")
    print(f"EMAIL_PORT: {getattr(settings, 'EMAIL_PORT', 'НЕ УСТАНОВЛЕН')}")
    print(f"EMAIL_USE_TLS: {getattr(settings, 'EMAIL_USE_TLS', 'НЕ УСТАНОВЛЕН')}")
    print(f"EMAIL_HOST_USER: {getattr(settings, 'EMAIL_HOST_USER', 'НЕ УСТАНОВЛЕН')}")
    print(f"DEFAULT_FROM_EMAIL: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'НЕ УСТАНОВЛЕН')}")
    print(f"EMAIL_BATCH_SIZE: {getattr(settings, 'EMAIL_BATCH_SIZE', 'НЕ УСТАНОВЛЕН')}")
    print(f"EMAIL_RATE_LIMIT: {getattr(settings, 'EMAIL_RATE_LIMIT', 'НЕ УСТАНОВЛЕН')}")

def check_dns_records():
    """Проверка DNS записей"""
    print_section("ПРОВЕРКА DNS ЗАПИСЕЙ")
    
    domain = 'vashsender.ru'
    
    # Проверка SPF
    try:
        answers = dns.resolver.resolve(domain, "TXT")
        spf_found = False
        for rdata in answers:
            txt = str(rdata)
            if txt.startswith('"v=spf1'):
                print(f"✅ SPF: {txt}")
                spf_found = True
                break
        if not spf_found:
            print("❌ SPF запись не найдена!")
    except Exception as e:
        print(f"❌ Ошибка проверки SPF: {e}")
    
    # Проверка DMARC
    try:
        answers = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
        dmarc_found = False
        for rdata in answers:
            txt = str(rdata)
            if txt.startswith('"v=DMARC1'):
                print(f"✅ DMARC: {txt}")
                dmarc_found = True
                break
        if not dmarc_found:
            print("❌ DMARC запись не найдена!")
    except Exception as e:
        print(f"❌ Ошибка проверки DMARC: {e}")
    
    # Проверка MX
    try:
        answers = dns.resolver.resolve(domain, "MX")
        print(f"✅ MX записи найдены: {len(answers)}")
        for rdata in answers:
            print(f"   {rdata.preference} {rdata.exchange}")
    except Exception as e:
        print(f"❌ Ошибка проверки MX: {e}")

def create_emergency_smtp_config():
    """Создание экстренной конфигурации SMTP"""
    print_section("СОЗДАНИЕ ЭКСТРЕННОЙ SMTP КОНФИГУРАЦИИ")
    
    # Конфигурация для Yandex SMTP (рекомендуется для России)
    yandex_config = """
# ЭКСТРЕННАЯ КОНФИГУРАЦИЯ YANDEX SMTP
# Добавьте эти настройки в core/settings/production.py

# Yandex SMTP настройки
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.yandex.ru'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'your-email@yandex.ru'  # ЗАМЕНИТЕ НА ВАШ EMAIL
EMAIL_HOST_PASSWORD = 'your-password'     # ЗАМЕНИТЕ НА ВАШ ПАРОЛЬ
DEFAULT_FROM_EMAIL = 'your-email@yandex.ru'  # ЗАМЕНИТЕ НА ВАШ EMAIL
SERVER_EMAIL = 'your-email@yandex.ru'     # ЗАМЕНИТЕ НА ВАШ EMAIL

# КРИТИЧЕСКИ ВАЖНО: Уменьшаем скорость отправки для Mail.ru и Yandex
EMAIL_BATCH_SIZE = 20      # Уменьшено с 100 до 20
EMAIL_RATE_LIMIT = 5       # Уменьшено с 100 до 5 писем в секунду
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 120    # Увеличено до 2 минут
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60

# Дополнительные настройки для доставляемости
EMAIL_USE_LOCALTIME = True
"""
    
    # Конфигурация для Mail.ru SMTP
    mailru_config = """
# АЛЬТЕРНАТИВНАЯ КОНФИГУРАЦИЯ MAIL.RU SMTP
# Используйте эту конфигурацию, если Yandex не подходит

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.mail.ru'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'your-email@mail.ru'    # ЗАМЕНИТЕ НА ВАШ EMAIL
EMAIL_HOST_PASSWORD = 'your-password'     # ЗАМЕНИТЕ НА ВАШ ПАРОЛЬ
DEFAULT_FROM_EMAIL = 'your-email@mail.ru' # ЗАМЕНИТЕ НА ВАШ EMAIL
SERVER_EMAIL = 'your-email@mail.ru'       # ЗАМЕНИТЕ НА ВАШ EMAIL

# Настройки для Mail.ru (еще более консервативные)
EMAIL_BATCH_SIZE = 10      # Очень маленькие батчи
EMAIL_RATE_LIMIT = 3       # Очень медленная отправка
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 180    # 3 минуты между попытками
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60
"""
    
    try:
        with open('/tmp/emergency_yandex_smtp.py', 'w', encoding='utf-8') as f:
            f.write(yandex_config)
        
        with open('/tmp/emergency_mailru_smtp.py', 'w', encoding='utf-8') as f:
            f.write(mailru_config)
        
        print("✅ Конфигурации созданы:")
        print("   /tmp/emergency_yandex_smtp.py")
        print("   /tmp/emergency_mailru_smtp.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания конфигураций: {e}")

def fix_email_headers_in_code():
    """Исправление заголовков писем в коде"""
    print_section("ИСПРАВЛЕНИЕ ЗАГОЛОВКОВ ПИСЕМ")
    
    # Создаем патч для tasks.py
    patch_content = """
# ПАТЧ ДЛЯ apps/campaigns/tasks.py
# Добавьте эти изменения в функцию send_single_email

# УБИРАЕМ проблемные заголовки
# msg['X-Mailer'] = 'VashSender/1.0'  # УДАЛИТЬ ЭТУ СТРОКУ
# msg['X-Priority'] = '3'              # УДАЛИТЬ ЭТУ СТРОКУ
# msg['X-MSMail-Priority'] = 'Normal'  # УДАЛИТЬ ЭТУ СТРОКУ
# msg['Importance'] = 'normal'         # УДАЛИТЬ ЭТУ СТРОКУ

# УБИРАЕМ заголовки, которые могут вызывать блокировку
# msg['List-Unsubscribe'] = f'<mailto:unsubscribe@{from_email.split("@")[1] if "@" in from_email else "vashsender.ru"}>'
# msg['Precedence'] = 'bulk'

# ДОБАВЛЯЕМ правильные заголовки для Mail.ru и Yandex
msg['Message-ID'] = f"<{uuid.uuid4()}@{from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'}>"
msg['Date'] = timezone.now().strftime('%a, %d %b %Y %H:%M:%S %z')
msg['MIME-Version'] = '1.0'

# ВКЛЮЧАЕМ DKIM подпись (раскомментируйте строку 835)
domain_name = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
msg = sign_email_with_dkim(msg, domain_name)
"""
    
    try:
        with open('/tmp/email_headers_patch.txt', 'w', encoding='utf-8') as f:
            f.write(patch_content)
        
        print("✅ Патч для заголовков создан: /tmp/email_headers_patch.txt")
        
    except Exception as e:
        print(f"❌ Ошибка создания патча: {e}")

def create_dns_fix_instructions():
    """Создание инструкций по исправлению DNS"""
    print_section("ИНСТРУКЦИИ ПО DNS")
    
    dns_instructions = """
# ЭКСТРЕННЫЕ DNS ЗАПИСИ ДЛЯ VASHSENDER.RU

## 1. SPF ЗАПИСЬ (TXT для vashsender.ru)
"v=spf1 ip4:146.185.196.123 ~all"

## 2. DMARC ЗАПИСЬ (TXT для _dmarc.vashsender.ru)
"v=DMARC1; p=none; rua=mailto:dmarc@vashsender.ru; sp=none; adkim=r; aspf=r;"

## 3. MX ЗАПИСЬ
vashsender.ru. IN MX 10 mail.vashsender.ru.

## 4. A ЗАПИСЬ ДЛЯ MAIL
mail.vashsender.ru. IN A 146.185.196.123

## КАК ДОБАВИТЬ:
1. Зайдите в панель управления DNS вашего домена
2. Добавьте TXT записи для SPF и DMARC
3. Добавьте MX и A записи
4. Подождите 10-30 минут для распространения

## ПРОВЕРКА:
dig TXT vashsender.ru
dig TXT _dmarc.vashsender.ru
dig MX vashsender.ru
"""
    
    try:
        with open('/tmp/dns_fix_instructions.txt', 'w', encoding='utf-8') as f:
            f.write(dns_instructions)
        
        print("✅ Инструкции по DNS созданы: /tmp/dns_fix_instructions.txt")
        
    except Exception as e:
        print(f"❌ Ошибка создания инструкций: {e}")

def create_emergency_restart_script():
    """Создание скрипта экстренного перезапуска"""
    print_section("СКРИПТ ЭКСТРЕННОГО ПЕРЕЗАПУСКА")
    
    restart_script = """#!/bin/bash
# ЭКСТРЕННЫЙ ПЕРЕЗАПУСК СЕРВИСОВ

echo "🔄 Перезапуск сервисов..."

# Останавливаем Celery
sudo systemctl stop celery
sudo systemctl stop celerybeat

# Очищаем очереди Redis
redis-cli FLUSHALL

# Перезапускаем Postfix (если используется)
sudo systemctl restart postfix

# Перезапускаем Celery
sudo systemctl start celery
sudo systemctl start celerybeat

# Перезапускаем Gunicorn
sudo systemctl restart gunicorn

# Проверяем статус
echo "📊 Статус сервисов:"
sudo systemctl status celery
sudo systemctl status gunicorn

echo "✅ Перезапуск завершен"
"""
    
    try:
        with open('/tmp/emergency_restart.sh', 'w') as f:
            f.write(restart_script)
        
        # Делаем скрипт исполняемым
        os.chmod('/tmp/emergency_restart.sh', 0o755)
        
        print("✅ Скрипт перезапуска создан: /tmp/emergency_restart.sh")
        
    except Exception as e:
        print(f"❌ Ошибка создания скрипта: {e}")

def test_external_smtp():
    """Тест внешних SMTP серверов"""
    print_section("ТЕСТ ВНЕШНИХ SMTP")
    
    smtp_servers = [
        ('smtp.yandex.ru', 587),
        ('smtp.mail.ru', 587),
        ('smtp.gmail.com', 587),
    ]
    
    for host, port in smtp_servers:
        try:
            print(f"Тестирование {host}:{port}...")
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
            print(f"✅ {host}:{port} - доступен")
            server.quit()
        except Exception as e:
            print(f"❌ {host}:{port} - недоступен: {e}")

def main():
    """Основная функция"""
    print("🚨 ЭКСТРЕННОЕ ИСПРАВЛЕНИЕ ДОСТАВЛЯЕМОСТИ В MAIL.RU И YANDEX")
    print(f"Время: {datetime.now()}")
    
    # Проверяем текущее состояние
    check_current_smtp_settings()
    check_dns_records()
    
    # Создаем исправления
    create_emergency_smtp_config()
    fix_email_headers_in_code()
    create_dns_fix_instructions()
    create_emergency_restart_script()
    
    # Тестируем внешние SMTP
    test_external_smtp()
    
    print_section("ЭКСТРЕННЫЙ ПЛАН ДЕЙСТВИЙ")
    print("""
🚨 НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:

1. ВЫБЕРИТЕ ВНЕШНИЙ SMTP:
   • Yandex (рекомендуется для России)
   • Mail.ru (альтернатива)
   • Gmail (для тестирования)

2. НАСТРОЙТЕ ВЫБРАННЫЙ SMTP:
   • Скопируйте конфигурацию из /tmp/emergency_*_smtp.py
   • Замените учетные данные
   • Добавьте в core/settings/production.py

3. ИСПРАВЬТЕ ЗАГОЛОВКИ ПИСЕМ:
   • Примените патч из /tmp/email_headers_patch.txt
   • Удалите проблемные заголовки
   • Включите DKIM подпись

4. НАСТРОЙТЕ DNS:
   • Добавьте SPF и DMARC записи
   • Следуйте инструкциям из /tmp/dns_fix_instructions.txt

5. ПЕРЕЗАПУСТИТЕ СЕРВИСЫ:
   • sudo bash /tmp/emergency_restart.sh

6. ПРОТЕСТИРУЙТЕ:
   • Отправьте тестовое письмо
   • Проверьте логи
   • Убедитесь в доставляемости

⚠️  ВАЖНО:
• Уменьшите скорость отправки до 5 писем в секунду
• Используйте маленькие батчи (10-20 писем)
• Добавьте задержки между попытками
• Мониторьте статистику доставляемости
""")

if __name__ == '__main__':
    main() 