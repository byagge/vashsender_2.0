#!/usr/bin/env python3
"""
Скрипт для проверки состояния DKIM настроек
"""

import os
import sys
import subprocess
import dns.resolver
from pathlib import Path

# Добавляем путь к Django проекту
sys.path.append('/var/www/vashsender')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

import django
django.setup()

from apps.emails.models import Domain
from django.conf import settings

def check_opendkim_service():
    """Проверка службы OpenDKIM"""
    
    print("🔍 Проверка службы OpenDKIM...")
    
    try:
        result = subprocess.run(['systemctl', 'is-active', 'opendkim'], 
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("✅ OpenDKIM запущен")
        else:
            print("❌ OpenDKIM не запущен")
            return False
    except Exception as e:
        print(f"❌ Ошибка проверки OpenDKIM: {e}")
        return False
    
    return True

def check_opendkim_config():
    """Проверка конфигурации OpenDKIM"""
    
    print("🔍 Проверка конфигурации OpenDKIM...")
    
    config_files = [
        "/etc/opendkim.conf",
        "/etc/opendkim/KeyTable",
        "/etc/opendkim/SigningTable",
        "/etc/opendkim/TrustedHosts"
    ]
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"✅ {config_file} существует")
        else:
            print(f"❌ {config_file} не найден")
            return False
    
    return True

def check_domains_and_keys():
    """Проверка доменов и ключей"""
    
    print("🔍 Проверка доменов и DKIM ключей...")
    
    domains = Domain.objects.all()
    
    if not domains.exists():
        print("❌ Нет доменов в базе данных")
        return False
    
    keys_dir = getattr(settings, 'DKIM_KEYS_DIR', '/etc/opendkim/keys')
    
    for domain in domains:
        print(f"\n📋 Домен: {domain.domain_name}")
        print(f"   Селектор: {domain.dkim_selector}")
        print(f"   DKIM подтвержден: {'✅' if domain.dkim_verified else '❌'}")
        
        # Проверяем приватный ключ
        if domain.private_key_path and os.path.exists(domain.private_key_path):
            key_path = domain.private_key_path
            print(f"   Приватный ключ (DB): ✅ {key_path}")
        else:
            key_path = os.path.join(keys_dir, domain.domain_name, f"{domain.dkim_selector}.private")
            if os.path.exists(key_path):
                print(f"   Приватный ключ (fallback): ✅ {key_path}")
            else:
                print(f"   Приватный ключ: ❌ не найден")
                continue
        
        # Проверяем публичный ключ
        public_key_path = os.path.join(keys_dir, domain.domain_name, f"{domain.dkim_selector}.txt")
        if os.path.exists(public_key_path):
            print(f"   Публичный ключ: ✅ {public_key_path}")
        else:
            print(f"   Публичный ключ: ❌ не найден")
        
        # Проверяем DNS запись
        try:
            selector_domain = f"{domain.dkim_selector}._domainkey.{domain.domain_name}"
            answers = dns.resolver.resolve(selector_domain, "TXT")
            for answer in answers:
                txt_record = ''.join([part.decode() if isinstance(part, bytes) else part for part in answer.strings])
                if 'v=DKIM1' in txt_record:
                    print(f"   DNS DKIM запись: ✅ найдена")
                    break
            else:
                print(f"   DNS DKIM запись: ❌ не найдена")
        except Exception as e:
            print(f"   DNS DKIM запись: ❌ ошибка проверки ({e})")

def check_postfix_integration():
    """Проверка интеграции с Postfix"""
    
    print("🔍 Проверка интеграции Postfix с OpenDKIM...")
    
    main_cf = "/etc/postfix/main.cf"
    
    try:
        with open(main_cf, 'r') as f:
            content = f.read()
        
        if 'smtpd_milters' in content and 'inet:localhost:12301' in content:
            print("✅ Postfix настроен для работы с OpenDKIM")
        else:
            print("❌ Postfix не настроен для работы с OpenDKIM")
            return False
    except Exception as e:
        print(f"❌ Ошибка проверки Postfix: {e}")
        return False
    
    return True

def check_milter_socket():
    """Проверка сокета milter"""
    
    print("🔍 Проверка сокета OpenDKIM milter...")
    
    try:
        result = subprocess.run(['netstat', '-tlnp'], capture_output=True, text=True, check=False)
        if ':12301' in result.stdout:
            print("✅ OpenDKIM milter слушает на порту 12301")
        else:
            print("❌ OpenDKIM milter не слушает на порту 12301")
            return False
    except Exception as e:
        print(f"❌ Ошибка проверки сокета: {e}")
        return False
    
    return True

def show_recent_logs():
    """Показать последние логи"""
    
    print("📋 Последние логи OpenDKIM:")
    
    try:
        result = subprocess.run(['journalctl', '-u', 'opendkim', '--no-pager', '-n', '20'], 
                              capture_output=True, text=True, check=False)
        if result.stdout:
            print(result.stdout)
        else:
            print("Логи не найдены")
    except Exception as e:
        print(f"Ошибка получения логов: {e}")

def main():
    """Основная функция"""
    
    print("🔍 Проверка состояния DKIM для VashSender")
    print("=" * 50)
    
    checks = [
        ("Служба OpenDKIM", check_opendkim_service),
        ("Конфигурация OpenDKIM", check_opendkim_config),
        ("Домены и ключи", check_domains_and_keys),
        ("Интеграция с Postfix", check_postfix_integration),
        ("Сокет milter", check_milter_socket),
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}...")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 Все проверки прошли успешно!")
        print("✅ DKIM должен работать корректно")
    else:
        print("❌ Обнаружены проблемы с настройкой DKIM")
        print("💡 Запустите setup_opendkim_auto.py для автоматической настройки")
    
    print("\n📋 Логи OpenDKIM:")
    show_recent_logs()

if __name__ == "__main__":
    main()
