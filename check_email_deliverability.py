#!/usr/bin/env python3
"""
Скрипт для проверки настроек доставляемости писем
"""

import dns.resolver
import socket
import subprocess
import sys
from urllib.parse import urlparse

def print_section(title):
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def check_spf(domain):
    """Проверка SPF записи"""
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        for r in answers:
            txt = b''.join(r.strings).decode('utf-8', errors='ignore').strip('"')
            if txt.lower().startswith('v=spf1'):
                print(f"✅ SPF запись найдена: {txt}")
                return True
        print("❌ SPF запись не найдена")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки SPF: {e}")
        return False

def check_dkim(domain, selector='default'):
    """Проверка DKIM записи"""
    try:
        name = f'{selector}._domainkey.{domain}'
        answers = dns.resolver.resolve(name, 'TXT')
        for r in answers:
            txt = b''.join(r.strings).decode('utf-8', errors='ignore').strip('"')
            if txt.startswith('v=DKIM1'):
                print(f"✅ DKIM запись найдена для {name}")
                return True
        print(f"❌ DKIM запись не найдена для {name}")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки DKIM: {e}")
        return False

def check_dmarc(domain):
    """Проверка DMARC записи"""
    try:
        name = f'_dmarc.{domain}'
        answers = dns.resolver.resolve(name, 'TXT')
        for r in answers:
            txt = b''.join(r.strings).decode('utf-8', errors='ignore').strip('"')
            if txt.startswith('v=DMARC1'):
                print(f"✅ DMARC запись найдена: {txt}")
                return True
        print("❌ DMARC запись не найдена")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки DMARC: {e}")
        return False

def check_mx(domain):
    """Проверка MX записи"""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        for r in answers:
            print(f"✅ MX запись найдена: {r.exchange} (приоритет: {r.preference})")
        return True
    except Exception as e:
        print(f"❌ Ошибка проверки MX: {e}")
        return False

def check_ptr(ip):
    """Проверка PTR записи (Reverse DNS)"""
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        print(f"✅ PTR запись найдена: {ip} -> {hostname}")
        return True
    except Exception as e:
        print(f"❌ Ошибка проверки PTR для {ip}: {e}")
        return False

def check_blacklist(ip):
    """Проверка IP в черных списках"""
    blacklists = [
        'zen.spamhaus.org',
        'bl.spamcop.net',
        'dnsbl.sorbs.net',
        'b.barracudacentral.org'
    ]
    
    print("Проверка IP в черных списках:")
    for bl in blacklists:
        try:
            query = f"{ip.split('.')[::-1]}.{bl}"
            dns.resolver.resolve(query, 'A')
            print(f"❌ IP {ip} найден в черном списке: {bl}")
            return False
        except dns.resolver.NXDOMAIN:
            print(f"✅ IP {ip} не найден в {bl}")
        except Exception as e:
            print(f"⚠️  Ошибка проверки {bl}: {e}")
    
    return True

def get_server_ip():
    """Получение IP адреса сервера"""
    try:
        # Попытка получить внешний IP
        import urllib.request
        with urllib.request.urlopen('https://api.ipify.org') as response:
            return response.read().decode('utf-8')
    except:
        try:
            # Альтернативный способ
            import urllib.request
            with urllib.request.urlopen('https://checkip.amazonaws.com') as response:
                return response.read().decode('utf-8').strip()
        except:
            print("⚠️  Не удалось получить внешний IP адрес")
            return None

def check_smtp_settings():
    """Проверка настроек SMTP"""
    print_section("ПРОВЕРКА НАСТРОЕК SMTP")
    
    try:
        from django.conf import settings
        
        print(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'Не задан')}")
        print(f"EMAIL_PORT: {getattr(settings, 'EMAIL_PORT', 'Не задан')}")
        print(f"EMAIL_USE_TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Не задан')}")
        print(f"EMAIL_USE_SSL: {getattr(settings, 'EMAIL_USE_SSL', 'Не задан')}")
        print(f"DEFAULT_FROM_EMAIL: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Не задан')}")
        print(f"EMAIL_BATCH_SIZE: {getattr(settings, 'EMAIL_BATCH_SIZE', 'Не задан')}")
        print(f"EMAIL_RATE_LIMIT: {getattr(settings, 'EMAIL_RATE_LIMIT', 'Не задан')}")
        
    except Exception as e:
        print(f"❌ Ошибка проверки настроек SMTP: {e}")

def main():
    print_section("ПРОВЕРКА ДОСТАВЛЯЕМОСТИ ПИСЕМ")
    
    domain = 'vashsender.ru'
    print(f"Проверяем домен: {domain}")
    
    # Получаем IP сервера
    server_ip = get_server_ip()
    if server_ip:
        print(f"IP сервера: {server_ip}")
    
    # Проверяем DNS записи
    print_section("ПРОВЕРКА DNS ЗАПИСЕЙ")
    
    spf_ok = check_spf(domain)
    dkim_ok = check_dkim(domain)
    dmarc_ok = check_dmarc(domain)
    mx_ok = check_mx(domain)
    
    if server_ip:
        ptr_ok = check_ptr(server_ip)
        blacklist_ok = check_blacklist(server_ip)
    
    # Проверяем настройки SMTP
    check_smtp_settings()
    
    # Итоговая оценка
    print_section("ИТОГОВАЯ ОЦЕНКА")
    
    score = 0
    total = 4
    
    if spf_ok:
        score += 1
    if dkim_ok:
        score += 1
    if dmarc_ok:
        score += 1
    if mx_ok:
        score += 1
    
    if server_ip:
        total += 2
        if ptr_ok:
            score += 1
        if blacklist_ok:
            score += 1
    
    percentage = (score / total) * 100
    
    print(f"Оценка доставляемости: {score}/{total} ({percentage:.1f}%)")
    
    if percentage >= 80:
        print("✅ Отличная настройка доставляемости")
    elif percentage >= 60:
        print("⚠️  Хорошая настройка, есть возможности для улучшения")
    elif percentage >= 40:
        print("⚠️  Средняя настройка, рекомендуется улучшить")
    else:
        print("❌ Плохая настройка, требуется серьезная доработка")
    
    # Рекомендации
    print_section("РЕКОМЕНДАЦИИ")
    
    if not spf_ok:
        print("• Добавьте SPF запись в DNS")
    if not dkim_ok:
        print("• Настройте DKIM подпись")
    if not dmarc_ok:
        print("• Добавьте DMARC запись")
    if not mx_ok:
        print("• Настройте MX запись")
    if server_ip and not ptr_ok:
        print("• Настройте PTR запись для IP сервера")
    if server_ip and not blacklist_ok:
        print("• IP сервер находится в черном списке, обратитесь к провайдеру")
    
    print("\nПодробные инструкции см. в файле email_deliverability_setup.md")

if __name__ == "__main__":
    main() 