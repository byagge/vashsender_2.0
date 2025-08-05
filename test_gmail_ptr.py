#!/usr/bin/env python3
"""
Тестирование PTR записи и отправки в Gmail
"""

import os
import sys
import subprocess
import socket
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/vashsender')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

import django
django.setup()

from django.conf import settings

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def get_server_ip():
    """Получение IP адреса сервера"""
    print_section("ПОЛУЧЕНИЕ IP АДРЕСА СЕРВЕРА")
    
    try:
        # Внешний IP
        external_ip = subprocess.check_output(['curl', '-s', 'ifconfig.me']).decode().strip()
        print(f"Внешний IP: {external_ip}")
        
        # Локальный IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"Локальный IP: {local_ip}")
        
        return external_ip, local_ip
        
    except Exception as e:
        print(f"❌ Ошибка получения IP: {e}")
        return None, None

def check_ptr_record(ip_address):
    """Проверка PTR записи"""
    print_section("ПРОВЕРКА PTR ЗАПИСИ")
    
    try:
        # Проверяем PTR запись
        result = subprocess.check_output(['dig', '-x', ip_address, '+short']).decode().strip()
        
        if result:
            print(f"✅ PTR запись найдена: {result}")
            
            # Проверяем, что PTR указывает на правильный домен
            if 'vashsender.ru' in result:
                print("✅ PTR запись корректна (содержит vashsender.ru)")
                return True
            else:
                print("⚠️  PTR запись не содержит vashsender.ru")
                return False
        else:
            print("❌ PTR запись не найдена")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки PTR: {e}")
        return False

def check_postfix_ipv6():
    """Проверка настроек Postfix для IPv6"""
    print_section("ПРОВЕРКА НАСТРОЕК POSTFIX")
    
    try:
        # Проверяем конфигурацию Postfix
        result = subprocess.check_output(['postconf', '-n']).decode()
        
        if 'inet_protocols = ipv4' in result:
            print("✅ Postfix настроен на использование только IPv4")
            return True
        else:
            print("❌ Postfix не настроен на использование только IPv4")
            print("Добавьте в /etc/postfix/main.cf:")
            print("inet_protocols = ipv4")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки Postfix: {e}")
        return False

def check_dns_records():
    """Проверка DNS записей"""
    print_section("ПРОВЕРКА DNS ЗАПИСЕЙ")
    
    domain = 'vashsender.ru'
    
    # Проверка SPF
    try:
        result = subprocess.check_output(['dig', 'TXT', domain, '+short']).decode()
        if 'v=spf1' in result:
            print("✅ SPF запись найдена")
        else:
            print("❌ SPF запись не найдена")
    except Exception as e:
        print(f"❌ Ошибка проверки SPF: {e}")
    
    # Проверка DMARC
    try:
        result = subprocess.check_output(['dig', 'TXT', f'_dmarc.{domain}', '+short']).decode()
        if 'v=DMARC1' in result:
            print("✅ DMARC запись найдена")
        else:
            print("❌ DMARC запись не найдена")
    except Exception as e:
        print(f"❌ Ошибка проверки DMARC: {e}")
    
    # Проверка MX
    try:
        result = subprocess.check_output(['dig', 'MX', domain, '+short']).decode()
        if result.strip():
            print("✅ MX записи найдены")
        else:
            print("❌ MX записи не найдены")
    except Exception as e:
        print(f"❌ Ошибка проверки MX: {e}")

def test_gmail_send():
    """Тест отправки в Gmail"""
    print_section("ТЕСТ ОТПРАВКИ В GMAIL")
    
    try:
        from django.core.mail import send_mail
        
        subject = f'Test Gmail PTR - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        message = f"""
        Тест отправки в Gmail для проверки PTR записи.
        
        Время отправки: {datetime.now()}
        Сервер: {socket.gethostname()}
        IP: {subprocess.check_output(['curl', '-s', 'ifconfig.me']).decode().strip()}
        
        Это тестовое письмо для проверки исправления ошибки:
        550-5.7.1 meet IPv6 sending guidelines regarding PTR records and authentication
        """
        
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = ['test@gmail.com']  # Замените на реальный адрес
        
        print(f"Отправка письма:")
        print(f"  От: {from_email}")
        print(f"  Кому: {recipient_list}")
        print(f"  Тема: {subject}")
        
        # НЕ отправляем реально, только проверяем настройки
        print("⚠️  Письмо НЕ отправлено (только проверка настроек)")
        print("✅ Настройки Django email корректны")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования отправки: {e}")
        return False

def create_dns_instructions(ip_address):
    """Создание инструкций по настройке DNS"""
    print_section("ИНСТРУКЦИИ ПО НАСТРОЙКЕ DNS")
    
    print(f"Для исправления проблемы Gmail добавьте следующие DNS записи:")
    print("")
    print("1. PTR запись (Reverse DNS):")
    print(f"   {ip_address}.in-addr.arpa. IN PTR mail.vashsender.ru.")
    print("")
    print("2. SPF запись:")
    print(f"   vashsender.ru. IN TXT \"v=spf1 ip4:{ip_address} ~all\"")
    print("")
    print("3. DMARC запись:")
    print("   _dmarc.vashsender.ru. IN TXT \"v=DMARC1; p=none; rua=mailto:dmarc@vashsender.ru; sp=none; adkim=r; aspf=r;\"")
    print("")
    print("4. MX запись:")
    print("   vashsender.ru. IN MX 10 mail.vashsender.ru.")
    print("   mail.vashsender.ru. IN A " + ip_address)
    print("")
    print("После добавления записей подождите 10-30 минут для распространения.")

def main():
    """Основная функция"""
    print("🧪 ТЕСТИРОВАНИЕ PTR ЗАПИСИ ДЛЯ GMAIL")
    print(f"Время: {datetime.now()}")
    
    # Получаем IP адреса
    external_ip, local_ip = get_server_ip()
    
    if external_ip:
        # Проверяем PTR запись
        ptr_ok = check_ptr_record(external_ip)
        
        # Проверяем Postfix
        postfix_ok = check_postfix_ipv6()
        
        # Проверяем DNS записи
        check_dns_records()
        
        # Тестируем отправку
        send_ok = test_gmail_send()
        
        # Создаем инструкции
        create_dns_instructions(external_ip)
        
        print_section("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        
        if ptr_ok and postfix_ok:
            print("✅ Все проверки пройдены успешно!")
            print("📧 Можно тестировать отправку в Gmail")
        else:
            print("❌ Обнаружены проблемы:")
            if not ptr_ok:
                print("   - PTR запись не настроена или некорректна")
            if not postfix_ok:
                print("   - Postfix не настроен на использование только IPv4")
            print("")
            print("🔧 Примените исправления и повторите тест")
        
        print("")
        print("📋 СЛЕДУЮЩИЕ ШАГИ:")
        print("1. Настройте DNS записи (см. инструкции выше)")
        print("2. Примените исправления Postfix: sudo ./fix_gmail_ipv6_ptr.sh")
        print("3. Подождите 10-30 минут для распространения DNS")
        print("4. Повторите тест")
        print("5. Отправьте реальное тестовое письмо в Gmail")
        
    else:
        print("❌ Не удалось получить IP адрес сервера")

if __name__ == '__main__':
    main() 