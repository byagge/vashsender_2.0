#!/usr/bin/env python3
"""
Быстрый тест SMTP соединения
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

def test_local_smtp():
    """Тест локального SMTP сервера"""
    print("="*50)
    print("ТЕСТ ЛОКАЛЬНОГО SMTP СЕРВЕРА")
    print("="*50)
    
    try:
        # Подключение к локальному SMTP
        print("Подключение к localhost:25...")
        server = smtplib.SMTP('localhost', 25, timeout=10)
        server.set_debuglevel(1)  # Включаем отладку
        
        # Получаем приветствие
        print(f"Приветствие сервера: {server.ehlo()}")
        
        # Тестируем отправку
        msg = MIMEMultipart()
        msg['From'] = 'test@vashsender.ru'
        msg['To'] = 'test@example.com'
        msg['Subject'] = f'SMTP Test - {datetime.now()}'
        
        body = "Это тестовое письмо для проверки SMTP соединения."
        msg.attach(MIMEText(body, 'plain'))
        
        # Пытаемся отправить
        print("Попытка отправки тестового письма...")
        server.send_message(msg)
        print("✅ Письмо отправлено через локальный SMTP")
        
        server.quit()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка локального SMTP: {e}")
        return False

def test_external_smtp():
    """Тест внешнего SMTP сервера"""
    print("\n" + "="*50)
    print("ТЕСТ ВНЕШНЕГО SMTP СЕРВЕРА")
    print("="*50)
    
    # Попробуем несколько популярных SMTP серверов
    smtp_servers = [
        ('smtp.gmail.com', 587, True),
        ('smtp.yandex.ru', 587, True),
        ('smtp.mail.ru', 587, True),
    ]
    
    for host, port, use_tls in smtp_servers:
        try:
            print(f"\nТестирование {host}:{port}...")
            
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(host, port, timeout=10)
            
            server.set_debuglevel(1)
            
            # Тестируем подключение
            server.ehlo()
            print(f"✅ Подключение к {host}:{port} успешно")
            
            server.quit()
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения к {host}:{port}: {e}")
    
    return False

def check_postfix_status():
    """Проверка статуса Postfix"""
    print("\n" + "="*50)
    print("ПРОВЕРКА СТАТУСА POSTFIX")
    print("="*50)
    
    try:
        import subprocess
        result = subprocess.run(['systemctl', 'status', 'postfix'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Postfix запущен")
            print(result.stdout)
        else:
            print("❌ Postfix не запущен или есть проблемы")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Ошибка проверки Postfix: {e}")

def check_mail_logs():
    """Проверка логов почты"""
    print("\n" + "="*50)
    print("ПРОВЕРКА ЛОГОВ ПОЧТЫ")
    print("="*50)
    
    log_files = [
        '/var/log/mail.log',
        '/var/log/maillog',
        '/var/log/postfix.log'
    ]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            try:
                import subprocess
                result = subprocess.run(['tail', '-n', '10', log_file], 
                                      capture_output=True, text=True)
                print(f"Последние записи в {log_file}:")
                print(result.stdout)
                break
            except Exception as e:
                print(f"❌ Ошибка чтения {log_file}: {e}")
        else:
            print(f"Файл {log_file} не найден")

def check_dns_records():
    """Проверка DNS записей"""
    print("\n" + "="*50)
    print("ПРОВЕРКА DNS ЗАПИСЕЙ")
    print("="*50)
    
    domain = 'vashsender.ru'
    
    try:
        import subprocess
        
        # Проверка MX
        print("Проверка MX записи:")
        result = subprocess.run(['dig', 'MX', domain], capture_output=True, text=True)
        print(result.stdout)
        
        # Проверка A записи
        print("Проверка A записи:")
        result = subprocess.run(['dig', 'A', domain], capture_output=True, text=True)
        print(result.stdout)
        
    except Exception as e:
        print(f"❌ Ошибка проверки DNS: {e}")

def main():
    print("БЫСТРАЯ ДИАГНОСТИКА SMTP ПРОБЛЕМ")
    print(f"Время: {datetime.now()}")
    
    # Проверяем локальный SMTP
    local_ok = test_local_smtp()
    
    # Проверяем внешний SMTP
    external_ok = test_external_smtp()
    
    # Проверяем Postfix
    check_postfix_status()
    
    # Проверяем логи
    check_mail_logs()
    
    # Проверяем DNS
    check_dns_records()
    
    print("\n" + "="*50)
    print("РЕЗУЛЬТАТЫ ДИАГНОСТИКИ")
    print("="*50)
    
    if local_ok:
        print("✅ Локальный SMTP работает")
    else:
        print("❌ Проблемы с локальным SMTP")
        
    if external_ok:
        print("✅ Внешние SMTP серверы доступны")
    else:
        print("❌ Проблемы с внешними SMTP серверами")
    
    print("\nРЕКОМЕНДАЦИИ:")
    if not local_ok:
        print("1. Проверьте настройки Postfix")
        print("2. Убедитесь, что Postfix запущен")
        print("3. Проверьте конфигурацию /etc/postfix/main.cf")
    
    print("4. Настройте правильные DNS записи")
    print("5. Проверьте, что порт 25 открыт")
    print("6. Убедитесь, что IP не в черных списках")

if __name__ == "__main__":
    main() 