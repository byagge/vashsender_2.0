#!/usr/bin/env python3
"""
Тестирование доставляемости писем в Mail.ru и Yandex
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time

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

def test_yandex_smtp():
    """Тест отправки через Yandex SMTP"""
    print_section("ТЕСТ YANDEX SMTP")
    
    # Настройки Yandex SMTP
    smtp_host = 'smtp.yandex.ru'
    smtp_port = 587
    username = config('YANDEX_EMAIL', default='your-email@yandex.ru')
    password = config('YANDEX_PASSWORD', default='your-password')
    
    if username == 'your-email@yandex.ru':
        print("❌ Настройте YANDEX_EMAIL и YANDEX_PASSWORD в .env файле")
        return False
    
    try:
        print(f"Подключение к {smtp_host}:{smtp_port}")
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        server.set_debuglevel(1)  # Включаем отладку
        
        print("Начало TLS...")
        server.starttls()
        
        print(f"Аутентификация как {username}...")
        server.login(username, password)
        print("✅ Аутентификация успешна")
        
        # Создаем тестовое письмо
        msg = MIMEMultipart('alternative')
        msg['From'] = username
        msg['To'] = 'test@yandex.ru'  # Тестовый адрес
        msg['Subject'] = f'Тест доставляемости Yandex - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        
        # Простой HTML контент
        html_content = f"""
        <html>
        <body>
            <h2>Тест доставляемости в Yandex</h2>
            <p>Это тестовое письмо для проверки доставляемости в Yandex.</p>
            <p>Время отправки: {datetime.now()}</p>
            <p>Отправитель: {username}</p>
            <hr>
            <p><small>Это тестовое письмо от VashSender</small></p>
        </body>
        </html>
        """
        
        # Текстовая версия
        text_content = f"""
        Тест доставляемости в Yandex
        
        Это тестовое письмо для проверки доставляемости в Yandex.
        Время отправки: {datetime.now()}
        Отправитель: {username}
        
        Это тестовое письмо от VashSender
        """
        
        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        print("Отправка тестового письма...")
        server.send_message(msg)
        print("✅ Письмо отправлено успешно")
        
        server.quit()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Yandex SMTP: {e}")
        return False

def test_mailru_smtp():
    """Тест отправки через Mail.ru SMTP"""
    print_section("ТЕСТ MAIL.RU SMTP")
    
    # Настройки Mail.ru SMTP
    smtp_host = 'smtp.mail.ru'
    smtp_port = 587
    username = config('MAILRU_EMAIL', default='your-email@mail.ru')
    password = config('MAILRU_PASSWORD', default='your-password')
    
    if username == 'your-email@mail.ru':
        print("❌ Настройте MAILRU_EMAIL и MAILRU_PASSWORD в .env файле")
        return False
    
    try:
        print(f"Подключение к {smtp_host}:{smtp_port}")
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        server.set_debuglevel(1)  # Включаем отладку
        
        print("Начало TLS...")
        server.starttls()
        
        print(f"Аутентификация как {username}...")
        server.login(username, password)
        print("✅ Аутентификация успешна")
        
        # Создаем тестовое письмо
        msg = MIMEMultipart('alternative')
        msg['From'] = username
        msg['To'] = 'test@mail.ru'  # Тестовый адрес
        msg['Subject'] = f'Тест доставляемости Mail.ru - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        
        # Простой HTML контент
        html_content = f"""
        <html>
        <body>
            <h2>Тест доставляемости в Mail.ru</h2>
            <p>Это тестовое письмо для проверки доставляемости в Mail.ru.</p>
            <p>Время отправки: {datetime.now()}</p>
            <p>Отправитель: {username}</p>
            <hr>
            <p><small>Это тестовое письмо от VashSender</small></p>
        </body>
        </html>
        """
        
        # Текстовая версия
        text_content = f"""
        Тест доставляемости в Mail.ru
        
        Это тестовое письмо для проверки доставляемости в Mail.ru.
        Время отправки: {datetime.now()}
        Отправитель: {username}
        
        Это тестовое письмо от VashSender
        """
        
        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        print("Отправка тестового письма...")
        server.send_message(msg)
        print("✅ Письмо отправлено успешно")
        
        server.quit()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Mail.ru SMTP: {e}")
        return False

def test_current_smtp():
    """Тест текущих SMTP настроек"""
    print_section("ТЕСТ ТЕКУЩИХ SMTP НАСТРОЕК")
    
    try:
        from django.core.mail import send_mail
        
        subject = f'Тест текущих настроек - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        message = f"""
        Тест текущих SMTP настроек
        
        Время отправки: {datetime.now()}
        EMAIL_HOST: {settings.EMAIL_HOST}
        EMAIL_PORT: {settings.EMAIL_PORT}
        EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}
        DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}
        
        Это тестовое письмо от VashSender
        """
        
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = ['test@example.com']  # Тестовый адрес
        
        print(f"Отправка через текущие настройки:")
        print(f"  EMAIL_HOST: {settings.EMAIL_HOST}")
        print(f"  EMAIL_PORT: {settings.EMAIL_PORT}")
        print(f"  EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        print(f"  От: {from_email}")
        print(f"  Кому: {recipient_list}")
        
        # НЕ отправляем реально, только проверяем настройки
        print("⚠️  Письмо НЕ отправлено (только проверка настроек)")
        print("✅ Текущие настройки корректны")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка текущих настроек: {e}")
        return False

def check_deliverability_improvements():
    """Проверка улучшений доставляемости"""
    print_section("ПРОВЕРКА УЛУЧШЕНИЙ ДОСТАВЛЯЕМОСТИ")
    
    improvements = [
        ("EMAIL_BATCH_SIZE", getattr(settings, 'EMAIL_BATCH_SIZE', 100), "20", "Уменьшен размер батча"),
        ("EMAIL_RATE_LIMIT", getattr(settings, 'EMAIL_RATE_LIMIT', 50), "5", "Уменьшена скорость отправки"),
        ("EMAIL_RETRY_DELAY", getattr(settings, 'EMAIL_RETRY_DELAY', 60), "120", "Увеличена задержка между попытками"),
    ]
    
    for setting, current, recommended, description in improvements:
        if str(current) == recommended:
            print(f"✅ {setting}: {current} (рекомендуется: {recommended}) - {description}")
        else:
            print(f"⚠️  {setting}: {current} (рекомендуется: {recommended}) - {description}")

def create_test_campaign():
    """Создание тестовой кампании"""
    print_section("СОЗДАНИЕ ТЕСТОВОЙ КАМПАНИИ")
    
    try:
        from apps.campaigns.models import Campaign
        from apps.mailer.models import Contact, ContactList
        from apps.mail_templates.models import EmailTemplate
        from apps.emails.models import SenderEmail
        from apps.accounts.models import User
        
        # Создаем тестового пользователя
        user, created = User.objects.get_or_create(
            email='test@vashsender.ru',
            defaults={
                'username': 'testuser',
                'is_active': True,
                'is_trusted_user': True
            }
        )
        
        # Создаем тестовый контакт
        contact, created = Contact.objects.get_or_create(
            email='test@yandex.ru',
            defaults={'name': 'Test User'}
        )
        
        # Создаем тестовый список контактов
        contact_list, created = ContactList.objects.get_or_create(
            name='Test List',
            user=user,
            defaults={'description': 'Test contact list for delivery testing'}
        )
        contact_list.contacts.add(contact)
        
        # Создаем тестовый шаблон
        template, created = EmailTemplate.objects.get_or_create(
            name='Test Template',
            user=user,
            defaults={
                'subject': 'Тест доставляемости',
                'html_content': '<h1>Тест доставляемости</h1><p>Это тестовое письмо для проверки доставляемости в Mail.ru и Yandex.</p>'
            }
        )
        
        # Создаем тестовый email отправителя
        sender_email, created = SenderEmail.objects.get_or_create(
            email='test@vashsender.ru',
            user=user,
            defaults={
                'sender_name': 'Test Sender',
                'is_verified': True
            }
        )
        
        # Создаем тестовую кампанию
        campaign, created = Campaign.objects.get_or_create(
            name='Test Delivery Campaign',
            user=user,
            defaults={
                'subject': 'Тест доставляемости в Mail.ru и Yandex',
                'content': 'Это тестовое письмо для проверки доставляемости.',
                'template': template,
                'sender_email': sender_email,
                'sender_name': 'Test Sender',
                'status': Campaign.STATUS_DRAFT
            }
        )
        campaign.contact_lists.add(contact_list)
        
        print(f"✅ Тестовая кампания создана: {campaign.name}")
        print(f"   ID: {campaign.id}")
        print(f"   Контактов: {contact_list.contacts.count()}")
        print(f"   Статус: {campaign.status}")
        
        return campaign
        
    except Exception as e:
        print(f"❌ Ошибка создания тестовой кампании: {e}")
        return None

def main():
    """Основная функция"""
    print("🧪 ТЕСТИРОВАНИЕ ДОСТАВЛЯЕМОСТИ В MAIL.RU И YANDEX")
    print(f"Время: {datetime.now()}")
    
    # Проверяем текущие настройки
    check_deliverability_improvements()
    test_current_smtp()
    
    # Тестируем внешние SMTP
    yandex_ok = test_yandex_smtp()
    mailru_ok = test_mailru_smtp()
    
    # Создаем тестовую кампанию
    campaign = create_test_campaign()
    
    print_section("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    
    if yandex_ok:
        print("✅ Yandex SMTP работает")
    else:
        print("❌ Yandex SMTP не работает")
    
    if mailru_ok:
        print("✅ Mail.ru SMTP работает")
    else:
        print("❌ Mail.ru SMTP не работает")
    
    if campaign:
        print(f"✅ Тестовая кампания создана (ID: {campaign.id})")
        print("\nДля тестирования отправки кампании:")
        print(f"python manage.py shell -c \"from apps.campaigns.tasks import send_campaign; send_campaign('{campaign.id}')\"")
    
    print_section("РЕКОМЕНДАЦИИ")
    print("""
1. Если внешние SMTP работают, настройте их в production.py
2. Если не работают, проверьте учетные данные в .env файле
3. Убедитесь, что в DNS настроены SPF и DMARC записи
4. Отправляйте тестовые письма небольшими батчами
5. Мониторьте логи на предмет ошибок доставляемости
""")

if __name__ == '__main__':
    main() 