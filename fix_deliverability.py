#!/usr/bin/env python3
"""
Скрипт для быстрого исправления проблем с доставляемостью писем
"""

import os
import sys
import subprocess
import time
from datetime import datetime

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def run_command(command, description):
    """Выполнение команды с выводом результата"""
    print(f"\n{description}:")
    print(f"Команда: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Успешно выполнено")
            if result.stdout:
                print(f"Вывод: {result.stdout.strip()}")
        else:
            print(f"❌ Ошибка: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def check_dns_records():
    """Проверка DNS записей"""
    print_section("ПРОВЕРКА DNS ЗАПИСЕЙ")
    
    domain = 'vashsender.ru'
    
    # Проверка SPF
    run_command(f"dig TXT {domain}", "Проверка SPF записи")
    
    # Проверка DKIM
    run_command(f"dig TXT default._domainkey.{domain}", "Проверка DKIM записи")
    
    # Проверка DMARC
    run_command(f"dig TXT _dmarc.{domain}", "Проверка DMARC записи")
    
    # Проверка MX
    run_command(f"dig MX {domain}", "Проверка MX записи")

def check_server_status():
    """Проверка статуса сервера"""
    print_section("ПРОВЕРКА СТАТУСА СЕРВЕРА")
    
    # Проверка Postfix
    run_command("systemctl status postfix", "Статус Postfix")
    
    # Проверка OpenDKIM
    run_command("systemctl status opendkim", "Статус OpenDKIM")
    
    # Проверка логов
    run_command("tail -n 20 /var/log/mail.log", "Последние записи в логах почты")

def restart_services():
    """Перезапуск сервисов"""
    print_section("ПЕРЕЗАПУСК СЕРВИСОВ")
    
    services = ['postfix', 'opendkim']
    
    for service in services:
        print(f"\nПерезапуск {service}...")
        run_command(f"systemctl restart {service}", f"Перезапуск {service}")
        time.sleep(2)
        run_command(f"systemctl status {service}", f"Статус {service} после перезапуска")

def check_ip_reputation():
    """Проверка репутации IP"""
    print_section("ПРОВЕРКА РЕПУТАЦИИ IP")
    
    # Получение внешнего IP
    try:
        import urllib.request
        with urllib.request.urlopen('https://api.ipify.org') as response:
            ip = response.read().decode('utf-8')
            print(f"Внешний IP: {ip}")
            
            # Проверка в черных списках
            blacklists = [
                'zen.spamhaus.org',
                'bl.spamcop.net',
                'dnsbl.sorbs.net',
                'b.barracudacentral.org'
            ]
            
            for bl in blacklists:
                run_command(f"dig +short {ip.split('.')[::-1]}.{bl}", f"Проверка в {bl}")
                
    except Exception as e:
        print(f"❌ Ошибка получения IP: {e}")

def optimize_smtp_settings():
    """Оптимизация настроек SMTP"""
    print_section("ОПТИМИЗАЦИЯ НАСТРОЕК SMTP")
    
    # Проверка текущих настроек
    print("\nТекущие настройки SMTP:")
    run_command("postconf -n | grep -E '(myhostname|mydomain|smtp_helo_name)'", "Основные настройки")
    
    # Рекомендации по настройке
    print("\nРекомендации по настройке Postfix:")
    print("1. Добавьте в /etc/postfix/main.cf:")
    print("   myhostname = mail.vashsender.ru")
    print("   mydomain = vashsender.ru")
    print("   smtp_helo_name = mail.vashsender.ru")
    print("   smtpd_helo_required = yes")
    print("   smtpd_helo_restrictions = permit_mynetworks, reject_invalid_helo_hostname")

def check_email_headers():
    """Проверка заголовков писем"""
    print_section("ПРОВЕРКА ЗАГОЛОВКОВ ПИСЕМ")
    
    print("Рекомендуемые заголовки для улучшения доставляемости:")
    print("• X-Mailer: VashSender/1.0")
    print("• List-Unsubscribe: <mailto:unsubscribe@vashsender.ru>")
    print("• Precedence: bulk")
    print("• X-Priority: 3")
    print("• Importance: normal")

def generate_dns_records():
    """Генерация DNS записей"""
    print_section("ГЕНЕРАЦИЯ DNS ЗАПИСЕЙ")
    
    print("Добавьте следующие записи в DNS:")
    print("\n1. SPF запись (TXT для vashsender.ru):")
    print('   "v=spf1 ip4:YOUR_SERVER_IP ~all"')
    
    print("\n2. DMARC запись (TXT для _dmarc.vashsender.ru):")
    print('   "v=DMARC1; p=quarantine; rua=mailto:dmarc@vashsender.ru; ruf=mailto:dmarc@vashsender.ru; sp=quarantine; adkim=r; aspf=r;"')
    
    print("\n3. MX запись:")
    print("   vashsender.ru. IN MX 10 mail.vashsender.ru.")
    
    print("\n4. A запись для mail.vashsender.ru:")
    print("   mail.vashsender.ru. IN A YOUR_SERVER_IP")

def immediate_actions():
    """Немедленные действия для улучшения доставляемости"""
    print_section("НЕМЕДЛЕННЫЕ ДЕЙСТВИЯ")
    
    print("1. Уменьшите скорость отправки:")
    print("   - EMAIL_BATCH_SIZE = 50")
    print("   - EMAIL_RATE_LIMIT = 10")
    
    print("\n2. Добавьте задержки между письмами:")
    print("   - Минимум 0.1-0.3 секунды между письмами")
    print("   - Пауза 2-4 секунды каждые 10 писем")
    
    print("\n3. Проверьте содержимое писем:")
    print("   - Избегайте спам-слов")
    print("   - Добавьте ссылку для отписки")
    print("   - Используйте правильное соотношение текста и изображений")
    
    print("\n4. Настройте правильные заголовки:")
    print("   - From: с реальным именем")
    print("   - Reply-To: с реальным адресом")
    print("   - Message-ID: уникальный для каждого письма")

def main():
    print_section("ИСПРАВЛЕНИЕ ПРОБЛЕМ С ДОСТАВЛЯЕМОСТЬЮ")
    print(f"Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Проверки
    check_dns_records()
    check_server_status()
    check_ip_reputation()
    
    # Оптимизация
    optimize_smtp_settings()
    check_email_headers()
    
    # Рекомендации
    generate_dns_records()
    immediate_actions()
    
    print_section("ЗАКЛЮЧЕНИЕ")
    print("Для улучшения доставляемости:")
    print("1. Настройте DNS записи (SPF, DKIM, DMARC)")
    print("2. Уменьшите скорость отправки")
    print("3. Добавьте правильные заголовки")
    print("4. Проверьте репутацию IP")
    print("5. Настройте PTR запись")
    
    print("\nПодробные инструкции см. в файле email_deliverability_setup.md")

if __name__ == "__main__":
    main() 