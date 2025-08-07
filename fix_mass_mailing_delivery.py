#!/usr/bin/env python3
"""
Скрипт для исправления проблем с доставкой массовых рассылок
Решает проблемы с доставкой писем при отправке на тысячи контактов
"""

import os
import sys
import time
import smtplib
import dns.resolver
import subprocess
from pathlib import Path

def print_section(title):
    """Печать заголовка секции"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_step(step, description):
    """Печать шага"""
    print(f"\n{step}. {description}")

def check_smtp_connection():
    """Проверка SMTP соединения"""
    print_step(1, "Проверка SMTP соединения")
    
    try:
        # Читаем настройки из env файла
        env_file = Path('.env')
        if not env_file.exists():
            env_file = Path('env')
        
        if not env_file.exists():
            print("❌ Файл .env не найден")
            return False
        
        # Парсим настройки
        settings = {}
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    settings[key] = value
        
        email_host = settings.get('EMAIL_HOST', 'localhost')
        email_port = int(settings.get('EMAIL_PORT', 25))
        email_use_tls = settings.get('EMAIL_USE_TLS', 'False').lower() == 'true'
        email_user = settings.get('EMAIL_HOST_USER', '')
        email_password = settings.get('EMAIL_HOST_PASSWORD', '')
        
        print(f"📧 SMTP настройки:")
        print(f"   Host: {email_host}")
        print(f"   Port: {email_port}")
        print(f"   TLS: {email_use_tls}")
        print(f"   User: {email_user if email_user else 'Не указан'}")
        
        # Тестируем соединение
        print(f"\n🔍 Тестирование SMTP соединения...")
        
        if email_host == 'localhost':
            print("⚠️  Используется локальный SMTP сервер")
            print("   Это может быть причиной проблем с доставкой")
            
            # Проверяем, запущен ли Postfix
            try:
                result = subprocess.run(['systemctl', 'is-active', 'postfix'], 
                                      capture_output=True, text=True)
                if result.stdout.strip() == 'active':
                    print("✅ Postfix запущен")
                else:
                    print("❌ Postfix не запущен")
                    return False
            except FileNotFoundError:
                print("⚠️  Не удалось проверить статус Postfix")
        
        # Тестируем соединение
        connection = smtplib.SMTP(email_host, email_port, timeout=10)
        
        if email_use_tls:
            connection.starttls()
        
        if email_user and email_password:
            connection.login(email_user, email_password)
        
        connection.quit()
        print("✅ SMTP соединение работает")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка SMTP соединения: {e}")
        return False

def check_dns_records():
    """Проверка DNS записей"""
    print_step(2, "Проверка DNS записей")
    
    domain = "vashsender.ru"
    
    print(f"🔍 Проверка DNS записей для {domain}")
    
    # Проверяем SPF
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        spf_found = False
        for answer in answers:
            if 'v=spf1' in str(answer):
                print(f"✅ SPF запись найдена: {answer}")
                spf_found = True
                break
        
        if not spf_found:
            print("❌ SPF запись не найдена")
            print("   Добавьте TXT запись: v=spf1 ip4:YOUR_SERVER_IP ~all")
    except Exception as e:
        print(f"❌ Ошибка проверки SPF: {e}")
    
    # Проверяем DMARC
    try:
        answers = dns.resolver.resolve(f'_dmarc.{domain}', 'TXT')
        dmarc_found = False
        for answer in answers:
            if 'v=DMARC1' in str(answer):
                print(f"✅ DMARC запись найдена: {answer}")
                dmarc_found = True
                break
        
        if not dmarc_found:
            print("❌ DMARC запись не найдена")
            print("   Добавьте TXT запись: v=DMARC1; p=quarantine; rua=mailto:dmarc@vashsender.ru")
    except Exception as e:
        print(f"❌ Ошибка проверки DMARC: {e}")
    
    # Проверяем DKIM
    try:
        answers = dns.resolver.resolve(f'default._domainkey.{domain}', 'TXT')
        dkim_found = False
        for answer in answers:
            if 'v=DKIM1' in str(answer):
                print(f"✅ DKIM запись найдена: {answer}")
                dkim_found = True
                break
        
        if not dkim_found:
            print("❌ DKIM запись не найдена")
            print("   Настройте OpenDKIM и добавьте DNS запись")
    except Exception as e:
        print(f"❌ Ошибка проверки DKIM: {e}")

def check_current_settings():
    """Проверка текущих настроек"""
    print_step(3, "Проверка текущих настроек отправки")
    
    env_file = Path('.env')
    if not env_file.exists():
        env_file = Path('env')
    
    if not env_file.exists():
        print("❌ Файл .env не найден")
        return
    
    settings = {}
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                settings[key] = value
    
    print("📊 Текущие настройки:")
    print(f"   EMAIL_BATCH_SIZE: {settings.get('EMAIL_BATCH_SIZE', 'Не указан')}")
    print(f"   EMAIL_RATE_LIMIT: {settings.get('EMAIL_RATE_LIMIT', 'Не указан')}")
    print(f"   EMAIL_RETRY_DELAY: {settings.get('EMAIL_RETRY_DELAY', 'Не указан')}")
    
    # Анализируем проблемы
    batch_size = int(settings.get('EMAIL_BATCH_SIZE', 200))
    rate_limit = int(settings.get('EMAIL_RATE_LIMIT', 100))
    
    print(f"\n⚠️  Проблемы в настройках:")
    
    if batch_size > 50:
        print(f"   ❌ EMAIL_BATCH_SIZE={batch_size} слишком высокий")
        print(f"      Рекомендуется: 20-50 для массовых рассылок")
    
    if rate_limit > 10:
        print(f"   ❌ EMAIL_RATE_LIMIT={rate_limit} слишком высокий")
        print(f"      Рекомендуется: 2-10 писем в секунду")
    
    if settings.get('EMAIL_HOST') == 'localhost':
        print(f"   ❌ Используется локальный SMTP сервер")
        print(f"      Рекомендуется: внешний SMTP (Yandex, Gmail, SendGrid)")

def create_optimized_settings():
    """Создание оптимизированных настроек"""
    print_step(4, "Создание оптимизированных настроек")
    
    optimized_config = """# ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ ДЛЯ МАССОВЫХ РАССЫЛОК
# Скопируйте эти настройки в файл .env

# Django settings
SECRET_KEY=2r32e44eqkx7qzufrv&3qz$(--r#t&@68%f2p$xhn=8!dvztfe
DEBUG=False

# Database settings
DATABASE_URL=sqlite:///db.sqlite3

# Redis settings
REDIS_URL=redis://localhost:6379/0

# Email settings - ВЫБЕРИТЕ ОДИН ВАРИАНТ

# ВАРИАНТ 1: Yandex SMTP (рекомендуется для России)
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your-email@yandex.ru
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=your-email@yandex.ru

# ВАРИАНТ 2: Gmail SMTP
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_USE_SSL=False
# EMAIL_HOST_USER=your-email@gmail.com
# EMAIL_HOST_PASSWORD=your-app-password
# DEFAULT_FROM_EMAIL=your-email@gmail.com

# ВАРИАНТ 3: SendGrid
# EMAIL_HOST=smtp.sendgrid.net
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_USE_SSL=False
# EMAIL_HOST_USER=apikey
# EMAIL_HOST_PASSWORD=your-sendgrid-api-key
# DEFAULT_FROM_EMAIL=noreply@vashsender.ru

# ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ ДЛЯ МАССОВЫХ РАССЫЛОК
EMAIL_BATCH_SIZE=20          # Уменьшено с 200 до 20
EMAIL_RATE_LIMIT=5           # Уменьшено с 100 до 5 писем в секунду
EMAIL_MAX_RETRIES=3
EMAIL_RETRY_DELAY=120        # Увеличено до 2 минут
EMAIL_CONNECTION_TIMEOUT=30
EMAIL_SEND_TIMEOUT=60

# Celery settings
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Security settings
ALLOWED_HOSTS=vashsender.ru,www.vashsender.ru,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://vashsender.ru,https://www.vashsender.ru
"""
    
    try:
        with open('optimized_env_settings.txt', 'w', encoding='utf-8') as f:
            f.write(optimized_config)
        
        print("✅ Оптимизированные настройки сохранены в optimized_env_settings.txt")
        print("\n📋 Инструкции:")
        print("1. Выберите один из вариантов SMTP (рекомендуется Yandex)")
        print("2. Замените your-email@yandex.ru и your-password на ваши данные")
        print("3. Скопируйте настройки в файл .env")
        print("4. Перезапустите сервисы")
        
    except Exception as e:
        print(f"❌ Ошибка создания файла: {e}")

def create_gradual_increase_script():
    """Создание скрипта для постепенного увеличения объема"""
    print_step(5, "Создание скрипта для постепенного увеличения объема")
    
    script_content = """#!/usr/bin/env python3
\"\"\"
Скрипт для постепенного увеличения объема рассылок
Помогает избежать попадания в спам при массовых рассылках
\"\"\"

import os
import time
from datetime import datetime, timedelta

def update_settings_for_volume(target_volume):
    \"\"\"Обновление настроек в зависимости от целевого объема\"\"\"
    
    if target_volume <= 100:
        # Малые рассылки (до 100 писем)
        settings = {
            'EMAIL_BATCH_SIZE': 10,
            'EMAIL_RATE_LIMIT': 2,
            'EMAIL_RETRY_DELAY': 60
        }
    elif target_volume <= 500:
        # Средние рассылки (100-500 писем)
        settings = {
            'EMAIL_BATCH_SIZE': 20,
            'EMAIL_RATE_LIMIT': 5,
            'EMAIL_RETRY_DELAY': 120
        }
    elif target_volume <= 1000:
        # Большие рассылки (500-1000 писем)
        settings = {
            'EMAIL_BATCH_SIZE': 30,
            'EMAIL_RATE_LIMIT': 8,
            'EMAIL_RETRY_DELAY': 180
        }
    else:
        # Очень большие рассылки (1000+ писем)
        settings = {
            'EMAIL_BATCH_SIZE': 50,
            'EMAIL_RATE_LIMIT': 10,
            'EMAIL_RETRY_DELAY': 300
        }
    
    return settings

def calculate_send_time(volume, rate_limit):
    \"\"\"Расчет времени отправки\"\"\"
    batches = (volume + 19) // 20  # Округление вверх
    time_per_batch = 20 / rate_limit  # секунд на батч
    total_time = batches * time_per_batch
    return total_time

def main():
    print("📊 Калькулятор объема рассылок")
    print("=" * 40)
    
    while True:
        try:
            volume = int(input("Введите количество писем для рассылки: "))
            break
        except ValueError:
            print("❌ Введите корректное число")
    
    settings = update_settings_for_volume(volume)
    send_time = calculate_send_time(volume, settings['EMAIL_RATE_LIMIT'])
    
    print(f"\\n📈 Рекомендуемые настройки для {volume} писем:")
    print(f"   EMAIL_BATCH_SIZE: {settings['EMAIL_BATCH_SIZE']}")
    print(f"   EMAIL_RATE_LIMIT: {settings['EMAIL_RATE_LIMIT']}")
    print(f"   EMAIL_RETRY_DELAY: {settings['EMAIL_RETRY_DELAY']}")
    print(f"\\n⏱️  Примерное время отправки: {send_time:.1f} секунд")
    
    # Рекомендации
    print(f"\\n💡 Рекомендации:")
    if volume > 1000:
        print("   - Разделите рассылку на несколько частей")
        print("   - Отправляйте с интервалом 1-2 часа")
        print("   - Используйте внешний SMTP (Yandex, Gmail)")
    elif volume > 500:
        print("   - Отправляйте в нерабочее время")
        print("   - Мониторьте статистику доставляемости")
    else:
        print("   - Настройки подходят для текущего объема")

if __name__ == "__main__":
    main()
"""
    
    try:
        with open('calculate_mailing_volume.py', 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        print("✅ Скрипт калькулятора создан: calculate_mailing_volume.py")
        print("   Запустите: python calculate_mailing_volume.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания скрипта: {e}")

def create_monitoring_script():
    """Создание скрипта для мониторинга доставляемости"""
    print_step(6, "Создание скрипта мониторинга")
    
    script_content = """#!/usr/bin/env python3
\"\"\"
Скрипт для мониторинга доставляемости писем
\"\"\"

import os
import sys
import django
from datetime import datetime, timedelta

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.mailer.models import Contact

def check_deliverability():
    \"\"\"Проверка статистики доставляемости\"\"\"
    
    print("📊 Статистика доставляемости")
    print("=" * 50)
    
    # Статистика за последние 24 часа
    yesterday = datetime.now() - timedelta(days=1)
    
    campaigns = Campaign.objects.filter(
        created_at__gte=yesterday
    ).order_by('-created_at')
    
    if not campaigns.exists():
        print("📭 Нет кампаний за последние 24 часа")
        return
    
    for campaign in campaigns:
        print(f"\\n📧 Кампания: {campaign.name}")
        print(f"   Статус: {campaign.get_status_display()}")
        print(f"   Создана: {campaign.created_at}")
        
        recipients = CampaignRecipient.objects.filter(campaign=campaign)
        total = recipients.count()
        sent = recipients.filter(is_sent=True).count()
        failed = recipients.filter(is_sent=False).count()
        
        if total > 0:
            success_rate = (sent / total) * 100
            print(f"   Всего получателей: {total}")
            print(f"   Отправлено: {sent}")
            print(f"   Ошибок: {failed}")
            print(f"   Успешность: {success_rate:.1f}%")
            
            if success_rate < 80:
                print("   ⚠️  Низкая доставляемость!")
            elif success_rate < 95:
                print("   ⚠️  Средняя доставляемость")
            else:
                print("   ✅ Хорошая доставляемость")

def check_recent_errors():
    \"\"\"Проверка последних ошибок\"\"\"
    
    print("\\n🔍 Последние ошибки отправки")
    print("=" * 50)
    
    # Получаем последние неудачные отправки
    failed_recipients = CampaignRecipient.objects.filter(
        is_sent=False,
        created_at__gte=datetime.now() - timedelta(hours=1)
    ).select_related('campaign', 'contact')[:10]
    
    if not failed_recipients.exists():
        print("✅ Нет ошибок за последний час")
        return
    
    for recipient in failed_recipients:
        print(f"\\n❌ Ошибка:")
        print(f"   Кампания: {recipient.campaign.name}")
        print(f"   Email: {recipient.contact.email}")
        print(f"   Время: {recipient.created_at}")

def main():
    check_deliverability()
    check_recent_errors()

if __name__ == "__main__":
    main()
"""
    
    try:
        with open('monitor_deliverability.py', 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        print("✅ Скрипт мониторинга создан: monitor_deliverability.py")
        print("   Запустите: python monitor_deliverability.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания скрипта: {e}")

def main():
    """Основная функция"""
    print_section("ИСПРАВЛЕНИЕ ПРОБЛЕМ С ДОСТАВКОЙ МАССОВЫХ РАССЫЛОК")
    
    print("🔍 Диагностика проблем с доставкой писем при массовых рассылках")
    print("   Проблема: письма не доставляются при отправке на тысячи контактов")
    
    # Выполняем проверки
    smtp_ok = check_smtp_connection()
    check_dns_records()
    check_current_settings()
    
    # Создаем решения
    create_optimized_settings()
    create_gradual_increase_script()
    create_monitoring_script()
    
    print_section("РЕКОМЕНДАЦИИ")
    
    print("🚀 Немедленные действия:")
    print("1. Замените локальный SMTP на внешний (Yandex, Gmail, SendGrid)")
    print("2. Уменьшите EMAIL_BATCH_SIZE до 20-50")
    print("3. Уменьшите EMAIL_RATE_LIMIT до 2-10 писем/сек")
    print("4. Увеличьте EMAIL_RETRY_DELAY до 120-300 секунд")
    
    print("\\n📈 Стратегия для больших рассылок:")
    print("1. Начинайте с малых объемов (50-100 писем)")
    print("2. Постепенно увеличивайте объем")
    print("3. Разделяйте большие рассылки на части")
    print("4. Отправляйте в нерабочее время")
    print("5. Мониторьте статистику доставляемости")
    
    print("\\n🔧 Технические улучшения:")
    print("1. Настройте SPF, DKIM, DMARC DNS записи")
    print("2. Используйте качественные списки контактов")
    print("3. Добавьте ссылку для отписки")
    print("4. Избегайте спам-слов в письмах")
    
    print("\\n📁 Созданные файлы:")
    print("   - optimized_env_settings.txt (оптимизированные настройки)")
    print("   - calculate_mailing_volume.py (калькулятор объема)")
    print("   - monitor_deliverability.py (мониторинг доставляемости)")
    
    if not smtp_ok:
        print("\\n⚠️  ВНИМАНИЕ: Проблемы с SMTP соединением!")
        print("   Рекомендуется немедленно перейти на внешний SMTP")

if __name__ == "__main__":
    main() 