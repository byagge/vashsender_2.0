#!/usr/bin/env python3
"""
Экстренное исправление проблем с SMTP
"""

import os
import subprocess
import time
from datetime import datetime

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def run_command(command, description):
    """Выполнение команды"""
    print(f"\n{description}:")
    print(f"Команда: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Успешно")
            if result.stdout:
                print(f"Вывод: {result.stdout.strip()}")
        else:
            print(f"❌ Ошибка: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def check_and_fix_postfix():
    """Проверка и исправление Postfix"""
    print_section("ПРОВЕРКА И ИСПРАВЛЕНИЕ POSTFIX")
    
    # Проверяем статус
    print("Проверка статуса Postfix...")
    result = subprocess.run(['systemctl', 'is-active', 'postfix'], 
                          capture_output=True, text=True)
    
    if result.stdout.strip() != 'active':
        print("❌ Postfix не запущен, запускаем...")
        run_command("sudo systemctl start postfix", "Запуск Postfix")
        time.sleep(3)
        run_command("sudo systemctl enable postfix", "Включение автозапуска Postfix")
    else:
        print("✅ Postfix запущен")
    
    # Проверяем конфигурацию
    print("\nПроверка конфигурации Postfix...")
    run_command("sudo postconf -n | head -20", "Основные настройки Postfix")
    
    # Проверяем порты
    print("\nПроверка открытых портов...")
    run_command("sudo netstat -tlnp | grep :25", "Порт 25 (SMTP)")
    run_command("sudo netstat -tlnp | grep :587", "Порт 587 (SMTP submission)")

def check_and_fix_firewall():
    """Проверка и исправление файрвола"""
    print_section("ПРОВЕРКА И ИСПРАВЛЕНИЕ ФАЙРВОЛА")
    
    # Проверяем UFW
    result = subprocess.run(['sudo', 'ufw', 'status'], capture_output=True, text=True)
    if 'active' in result.stdout:
        print("UFW активен, проверяем правила...")
        run_command("sudo ufw status numbered", "Правила UFW")
        
        # Открываем порты если нужно
        run_command("sudo ufw allow 25/tcp", "Открытие порта 25")
        run_command("sudo ufw allow 587/tcp", "Открытие порта 587")
        run_command("sudo ufw allow 465/tcp", "Открытие порта 465")
    
    # Проверяем iptables
    run_command("sudo iptables -L -n | grep -E '(25|587|465)'", "Правила iptables для SMTP")

def check_dns_and_network():
    """Проверка DNS и сети"""
    print_section("ПРОВЕРКА DNS И СЕТИ")
    
    # Получаем IP сервера
    try:
        import urllib.request
        with urllib.request.urlopen('https://api.ipify.org') as response:
            server_ip = response.read().decode('utf-8')
            print(f"Внешний IP сервера: {server_ip}")
            
            # Проверяем PTR
            run_command(f"nslookup {server_ip}", "Проверка PTR записи")
            
    except Exception as e:
        print(f"❌ Ошибка получения IP: {e}")
    
    # Проверяем DNS записи
    domain = 'vashsender.ru'
    run_command(f"dig MX {domain}", "Проверка MX записи")
    run_command(f"dig A {domain}", "Проверка A записи")
    run_command(f"dig TXT {domain}", "Проверка TXT записей")

def create_basic_postfix_config():
    """Создание базовой конфигурации Postfix"""
    print_section("СОЗДАНИЕ БАЗОВОЙ КОНФИГУРАЦИИ POSTFIX")
    
    config_content = """
# Основные настройки
myhostname = mail.vashsender.ru
mydomain = vashsender.ru
myorigin = $mydomain

# Настройки сети
inet_interfaces = all
inet_protocols = ipv4

# Настройки для доставляемости
smtp_helo_name = mail.vashsender.ru
smtp_host_lookup = dns, native
disable_dns_lookups = no

# Настройки для предотвращения спама
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

# Настройки для отправки
smtp_tls_security_level = may
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt

# Настройки для получения
smtpd_recipient_restrictions = permit_mynetworks, reject_unauth_destination
smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination

# Настройки для логов
mail_name = Postfix
"""
    
    try:
        with open('/tmp/postfix_main.cf', 'w') as f:
            f.write(config_content)
        
        print("✅ Базовая конфигурация создана в /tmp/postfix_main.cf")
        print("Для применения выполните:")
        print("sudo cp /tmp/postfix_main.cf /etc/postfix/main.cf")
        print("sudo systemctl restart postfix")
        
    except Exception as e:
        print(f"❌ Ошибка создания конфигурации: {e}")

def test_smtp_connection():
    """Тест SMTP соединения"""
    print_section("ТЕСТ SMTP СОЕДИНЕНИЯ")
    
    test_script = """
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    # Тест локального SMTP
    print("Тестирование localhost:25...")
    server = smtplib.SMTP('localhost', 25, timeout=10)
    server.set_debuglevel(1)
    
    # EHLO
    server.ehlo()
    
    # Создаем тестовое письмо
    msg = MIMEMultipart()
    msg['From'] = 'test@vashsender.ru'
    msg['To'] = 'test@example.com'
    msg['Subject'] = 'SMTP Test'
    msg.attach(MIMEText('Test message', 'plain'))
    
    # Отправляем
    server.send_message(msg)
    print("✅ Тест успешен")
    
    server.quit()
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
"""
    
    try:
        with open('/tmp/test_smtp.py', 'w') as f:
            f.write(test_script)
        
        run_command("python3 /tmp/test_smtp.py", "Тест SMTP соединения")
        
    except Exception as e:
        print(f"❌ Ошибка создания теста: {e}")

def emergency_recommendations():
    """Экстренные рекомендации"""
    print_section("ЭКСТРЕННЫЕ РЕКОМЕНДАЦИИ")
    
    print("1. НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ:")
    print("   • Перезапустите Postfix: sudo systemctl restart postfix")
    print("   • Проверьте логи: sudo tail -f /var/log/mail.log")
    print("   • Откройте порты: sudo ufw allow 25,587,465")
    
    print("\n2. НАСТРОЙКА DNS (критично!):")
    print("   • Добавьте MX запись: vashsender.ru IN MX 10 mail.vashsender.ru")
    print("   • Добавьте A запись: mail.vashsender.ru IN A YOUR_IP")
    print("   • Добавьте SPF: vashsender.ru IN TXT \"v=spf1 ip4:YOUR_IP ~all\"")
    
    print("\n3. АЛЬТЕРНАТИВНЫЕ РЕШЕНИЯ:")
    print("   • Используйте внешний SMTP (Gmail, Yandex, Mail.ru)")
    print("   • Настройте SendGrid или Mailgun")
    print("   • Используйте Amazon SES")
    
    print("\n4. ПРОВЕРКА РЕЗУЛЬТАТА:")
    print("   • Запустите: python3 test_smtp_connection.py")
    print("   • Отправьте тестовое письмо")
    print("   • Проверьте логи на ошибки")

def main():
    print("🚨 ЭКСТРЕННОЕ ИСПРАВЛЕНИЕ SMTP ПРОБЛЕМ")
    print(f"Время: {datetime.now()}")
    
    # Проверяем и исправляем Postfix
    check_and_fix_postfix()
    
    # Проверяем файрвол
    check_and_fix_firewall()
    
    # Проверяем DNS и сеть
    check_dns_and_network()
    
    # Создаем базовую конфигурацию
    create_basic_postfix_config()
    
    # Тестируем соединение
    test_smtp_connection()
    
    # Даем рекомендации
    emergency_recommendations()
    
    print_section("ЗАКЛЮЧЕНИЕ")
    print("Если письма все еще не отправляются:")
    print("1. Проверьте логи: sudo tail -f /var/log/mail.log")
    print("2. Настройте DNS записи")
    print("3. Рассмотрите использование внешнего SMTP")
    print("4. Обратитесь к провайдеру по поводу блокировки порта 25")

if __name__ == "__main__":
    main() 