#!/usr/bin/env python3
"""
Настройка внешнего SMTP сервера как альтернативы
"""

import os
import subprocess
from datetime import datetime

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def create_gmail_smtp_config():
    """Создание конфигурации для Gmail SMTP"""
    print_section("НАСТРОЙКА GMAIL SMTP")
    
    config_content = """
# Gmail SMTP настройки
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'your-email@gmail.com'
SERVER_EMAIL = 'your-email@gmail.com'

# Настройки для доставляемости
EMAIL_BATCH_SIZE = 50
EMAIL_RATE_LIMIT = 10
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 120
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60
"""
    
    try:
        with open('/tmp/gmail_smtp_config.py', 'w') as f:
            f.write(config_content)
        
        print("✅ Конфигурация Gmail создана в /tmp/gmail_smtp_config.py")
        print("\nДля использования Gmail SMTP:")
        print("1. Создайте приложение в Google Account")
        print("2. Получите пароль приложения")
        print("3. Замените your-email@gmail.com и your-app-password")
        print("4. Добавьте настройки в core/settings/production.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def create_yandex_smtp_config():
    """Создание конфигурации для Yandex SMTP"""
    print_section("НАСТРОЙКА YANDEX SMTP")
    
    config_content = """
# Yandex SMTP настройки
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.yandex.ru'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'your-email@yandex.ru'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'your-email@yandex.ru'
SERVER_EMAIL = 'your-email@yandex.ru'

# Настройки для доставляемости
EMAIL_BATCH_SIZE = 50
EMAIL_RATE_LIMIT = 10
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 120
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60
"""
    
    try:
        with open('/tmp/yandex_smtp_config.py', 'w') as f:
            f.write(config_content)
        
        print("✅ Конфигурация Yandex создана в /tmp/yandex_smtp_config.py")
        print("\nДля использования Yandex SMTP:")
        print("1. Включите SMTP в настройках Yandex")
        print("2. Используйте пароль от аккаунта")
        print("3. Замените your-email@yandex.ru и your-password")
        print("4. Добавьте настройки в core/settings/production.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def create_mailru_smtp_config():
    """Создание конфигурации для Mail.ru SMTP"""
    print_section("НАСТРОЙКА MAIL.RU SMTP")
    
    config_content = """
# Mail.ru SMTP настройки
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.mail.ru'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'your-email@mail.ru'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'your-email@mail.ru'
SERVER_EMAIL = 'your-email@mail.ru'

# Настройки для доставляемости
EMAIL_BATCH_SIZE = 50
EMAIL_RATE_LIMIT = 10
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 120
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60
"""
    
    try:
        with open('/tmp/mailru_smtp_config.py', 'w') as f:
            f.write(config_content)
        
        print("✅ Конфигурация Mail.ru создана в /tmp/mailru_smtp_config.py")
        print("\nДля использования Mail.ru SMTP:")
        print("1. Включите SMTP в настройках Mail.ru")
        print("2. Используйте пароль от аккаунта")
        print("3. Замените your-email@mail.ru и your-password")
        print("4. Добавьте настройки в core/settings/production.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def create_sendgrid_config():
    """Создание конфигурации для SendGrid"""
    print_section("НАСТРОЙКА SENDGRID")
    
    config_content = """
# SendGrid настройки
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = 'your-sendgrid-api-key'
DEFAULT_FROM_EMAIL = 'noreply@vashsender.ru'
SERVER_EMAIL = 'noreply@vashsender.ru'

# Настройки для доставляемости
EMAIL_BATCH_SIZE = 100
EMAIL_RATE_LIMIT = 20
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAY = 60
EMAIL_CONNECTION_TIMEOUT = 30
EMAIL_SEND_TIMEOUT = 60
"""
    
    try:
        with open('/tmp/sendgrid_config.py', 'w') as f:
            f.write(config_content)
        
        print("✅ Конфигурация SendGrid создана в /tmp/sendgrid_config.py")
        print("\nДля использования SendGrid:")
        print("1. Зарегистрируйтесь на sendgrid.com")
        print("2. Получите API ключ")
        print("3. Замените your-sendgrid-api-key")
        print("4. Добавьте настройки в core/settings/production.py")
        
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def test_external_smtp():
    """Тест внешнего SMTP"""
    print_section("ТЕСТ ВНЕШНЕГО SMTP")
    
    test_script = """
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Тест Gmail SMTP
def test_gmail():
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        print("✅ Gmail SMTP доступен")
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Gmail SMTP недоступен: {e}")
        return False

# Тест Yandex SMTP
def test_yandex():
    try:
        server = smtplib.SMTP('smtp.yandex.ru', 587, timeout=10)
        server.starttls()
        print("✅ Yandex SMTP доступен")
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Yandex SMTP недоступен: {e}")
        return False

# Тест Mail.ru SMTP
def test_mailru():
    try:
        server = smtplib.SMTP('smtp.mail.ru', 587, timeout=10)
        server.starttls()
        print("✅ Mail.ru SMTP доступен")
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Mail.ru SMTP недоступен: {e}")
        return False

# Тест SendGrid SMTP
def test_sendgrid():
    try:
        server = smtplib.SMTP('smtp.sendgrid.net', 587, timeout=10)
        server.starttls()
        print("✅ SendGrid SMTP доступен")
        server.quit()
        return True
    except Exception as e:
        print(f"❌ SendGrid SMTP недоступен: {e}")
        return False

print("Тестирование внешних SMTP серверов...")
test_gmail()
test_yandex()
test_mailru()
test_sendgrid()
"""
    
    try:
        with open('/tmp/test_external_smtp.py', 'w') as f:
            f.write(test_script)
        
        subprocess.run(['python3', '/tmp/test_external_smtp.py'])
        
    except Exception as e:
        print(f"❌ Ошибка создания теста: {e}")

def quick_fix_instructions():
    """Быстрые инструкции по исправлению"""
    print_section("БЫСТРОЕ ИСПРАВЛЕНИЕ")
    
    print("🚨 ЭКСТРЕННЫЕ ДЕЙСТВИЯ:")
    print("\n1. ВЫБЕРИТЕ ВНЕШНИЙ SMTP:")
    print("   • Gmail (рекомендуется для тестирования)")
    print("   • Yandex (хорошо для России)")
    print("   • Mail.ru (хорошо для России)")
    print("   • SendGrid (профессиональное решение)")
    
    print("\n2. НАСТРОЙТЕ ВЫБРАННЫЙ SMTP:")
    print("   • Скопируйте конфигурацию из /tmp/")
    print("   • Замените учетные данные")
    print("   • Добавьте в core/settings/production.py")
    
    print("\n3. ПЕРЕЗАПУСТИТЕ СЕРВИСЫ:")
    print("   sudo systemctl restart celery")
    print("   sudo systemctl restart gunicorn")
    
    print("\n4. ПРОТЕСТИРУЙТЕ:")
    print("   • Отправьте тестовое письмо")
    print("   • Проверьте логи")
    print("   • Убедитесь в доставляемости")
    
    print("\n5. АЛЬТЕРНАТИВЫ:")
    print("   • Используйте готовые сервисы (Mailgun, SendGrid)")
    print("   • Настройте Amazon SES")
    print("   • Используйте SMTP провайдера")

def main():
    print("🔧 НАСТРОЙКА ВНЕШНЕГО SMTP")
    print(f"Время: {datetime.now()}")
    
    # Создаем конфигурации
    create_gmail_smtp_config()
    create_yandex_smtp_config()
    create_mailru_smtp_config()
    create_sendgrid_config()
    
    # Тестируем внешние SMTP
    test_external_smtp()
    
    # Даем инструкции
    quick_fix_instructions()
    
    print_section("РЕКОМЕНДАЦИИ")
    print("1. Начните с Gmail для быстрого тестирования")
    print("2. Для продакшена используйте SendGrid или Mailgun")
    print("3. Настройте правильные заголовки писем")
    print("4. Мониторьте статистику доставляемости")
    print("5. Постепенно увеличивайте объемы")

if __name__ == "__main__":
    main() 