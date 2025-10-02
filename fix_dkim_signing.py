#!/usr/bin/env python3
"""
Скрипт для исправления DKIM подписи в VashSender
"""

import os
import sys
import subprocess

# Добавляем путь к Django проекту
sys.path.append('/var/www/vashsender')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

import django
django.setup()

from apps.emails.models import Domain
from django.conf import settings

def check_opendkim_status():
    """Проверка статуса OpenDKIM"""
    print("🔍 Проверка статуса OpenDKIM...")
    
    try:
        result = subprocess.run(['systemctl', 'status', 'opendkim'], 
                              capture_output=True, text=True, check=False)
        if 'active (running)' in result.stdout:
            print("✅ OpenDKIM запущен")
        else:
            print("❌ OpenDKIM не запущен")
            print("Попытка запуска...")
            subprocess.run(['systemctl', 'start', 'opendkim'], check=True)
            print("✅ OpenDKIM запущен")
    except Exception as e:
        print(f"❌ Ошибка с OpenDKIM: {e}")
        return False
    
    return True

def check_postfix_milter():
    """Проверка настроек milter в Postfix"""
    print("🔍 Проверка настроек milter в Postfix...")
    
    try:
        result = subprocess.run(['postconf', '-n'], capture_output=True, text=True, check=True)
        config = result.stdout
        
        if 'smtpd_milters' in config and '12301' in config:
            print("✅ Postfix настроен для работы с OpenDKIM")
        else:
            print("❌ Postfix не настроен для milter")
            print("Добавление настроек milter...")
            
            # Добавляем настройки milter
            milter_settings = [
                'milter_protocol = 2',
                'milter_default_action = accept', 
                'smtpd_milters = inet:127.0.0.1:12301',
                'non_smtpd_milters = inet:127.0.0.1:12301'
            ]
            
            for setting in milter_settings:
                subprocess.run(['postconf', '-e', setting], check=True)
            
            print("✅ Настройки milter добавлены")
            
            # Перезапускаем Postfix
            subprocess.run(['systemctl', 'reload', 'postfix'], check=True)
            print("✅ Postfix перезагружен")
            
    except Exception as e:
        print(f"❌ Ошибка настройки Postfix: {e}")
        return False
    
    return True

def check_socket_connection():
    """Проверка соединения с сокетом OpenDKIM"""
    print("🔍 Проверка сокета OpenDKIM...")
    
    try:
        result = subprocess.run(['netstat', '-tlnp'], capture_output=True, text=True, check=False)
        if ':12301' in result.stdout:
            print("✅ OpenDKIM слушает на порту 12301")
        else:
            print("❌ OpenDKIM не слушает на порту 12301")
            return False
    except Exception as e:
        print(f"❌ Ошибка проверки сокета: {e}")
        return False
    
    return True

def update_signing_table():
    """Обновление SigningTable для всех доменов"""
    print("🔍 Обновление SigningTable...")
    
    try:
        domains = Domain.objects.filter(dkim_verified=True)
        
        if not domains.exists():
            print("❌ Нет подтвержденных доменов в базе данных")
            return False
        
        signing_table_content = ""
        
        for domain in domains:
            selector = domain.dkim_selector
            domain_name = domain.domain_name
            
            # Проверяем существование ключа
            key_path = f"/etc/opendkim/keys/{domain_name}/{selector}.private"
            if os.path.exists(key_path):
                signing_table_content += f"*@{domain_name} {selector}._domainkey.{domain_name}\n"
                print(f"✅ Добавлен домен {domain_name}")
            else:
                print(f"❌ Ключ не найден для домена {domain_name}: {key_path}")
        
        # Записываем SigningTable
        with open('/etc/opendkim/SigningTable', 'w') as f:
            f.write(signing_table_content)
        
        print("✅ SigningTable обновлен")
        
        # Перезапускаем OpenDKIM
        subprocess.run(['systemctl', 'restart', 'opendkim'], check=True)
        print("✅ OpenDKIM перезапущен")
        
    except Exception as e:
        print(f"❌ Ошибка обновления SigningTable: {e}")
        return False
    
    return True

def test_email_sending():
    """Тест отправки письма"""
    print("🧪 Тест отправки письма...")
    
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Создаем тестовое письмо
        msg = MIMEMultipart()
        msg['From'] = 'test@monocode.app'  # Используем домен из KeyTable
        msg['To'] = 'test@example.com'
        msg['Subject'] = 'DKIM Test'
        
        body = "This is a DKIM test message"
        msg.attach(MIMEText(body, 'plain'))
        
        # Отправляем через localhost (Postfix + OpenDKIM)
        server = smtplib.SMTP('localhost', 25)
        text = msg.as_string()
        server.sendmail('test@monocode.app', 'test@example.com', text)
        server.quit()
        
        print("✅ Тестовое письмо отправлено через localhost")
        
    except Exception as e:
        print(f"❌ Ошибка отправки тестового письма: {e}")
        return False
    
    return True

def show_logs():
    """Показать логи OpenDKIM"""
    print("📋 Последние логи OpenDKIM:")
    
    try:
        result = subprocess.run(['journalctl', '-u', 'opendkim', '--no-pager', '-n', '10'], 
                              capture_output=True, text=True, check=False)
        if result.stdout:
            print(result.stdout)
        
        print("\n📋 Последние логи mail:")
        result = subprocess.run(['tail', '-n', '10', '/var/log/mail.log'], 
                              capture_output=True, text=True, check=False)
        if result.stdout:
            print(result.stdout)
            
    except Exception as e:
        print(f"Ошибка получения логов: {e}")

def main():
    """Основная функция"""
    
    print("🔧 Исправление DKIM подписи для VashSender")
    print("=" * 50)
    
    steps = [
        ("Проверка статуса OpenDKIM", check_opendkim_status),
        ("Проверка настроек Postfix milter", check_postfix_milter),
        ("Проверка сокета OpenDKIM", check_socket_connection),
        ("Обновление SigningTable", update_signing_table),
        ("Тест отправки письма", test_email_sending),
    ]
    
    for step_name, step_func in steps:
        print(f"\n📋 {step_name}...")
        if not step_func():
            print(f"❌ Ошибка на этапе: {step_name}")
            show_logs()
            sys.exit(1)
    
    print("\n🎉 Исправление DKIM завершено!")
    print("\n📋 Проверьте логи:")
    show_logs()
    
    print("\n💡 Следующие шаги:")
    print("1. Отправьте тестовую кампанию")
    print("2. Проверьте заголовки письма на наличие DKIM-Signature")
    print("3. Если проблемы остались, проверьте логи: journalctl -u opendkim -f")

if __name__ == "__main__":
    main()
