#!/usr/bin/env python3
"""
Скрипт для автоматической настройки OpenDKIM с ключами из apps/emails
"""

import os
import sys
import subprocess
from pathlib import Path

# Добавляем путь к Django проекту
sys.path.append('/var/www/vashsender')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

import django
django.setup()

from apps.emails.models import Domain
from django.conf import settings

def setup_opendkim_config():
    """Настройка OpenDKIM конфигурации"""
    
    print("🔧 Настройка OpenDKIM для автоматической подписи...")
    
    # Пути к конфигурационным файлам OpenDKIM
    opendkim_conf = "/etc/opendkim.conf"
    key_table = "/etc/opendkim/KeyTable"
    signing_table = "/etc/opendkim/SigningTable"
    trusted_hosts = "/etc/opendkim/TrustedHosts"
    
    # 1. Создаем основной конфигурационный файл OpenDKIM
    opendkim_config = """# OpenDKIM Configuration
Syslog                  yes
SyslogSuccess           yes
LogWhy                  yes
Canonicalization        relaxed/simple
ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
InternalHosts           refile:/etc/opendkim/TrustedHosts
KeyTable                refile:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
Mode                    sv
PidFile                 /var/run/opendkim/opendkim.pid
SignatureAlgorithm      rsa-sha256
UserID                  opendkim:opendkim
Socket                  inet:12301@localhost
"""
    
    try:
        with open(opendkim_conf, 'w') as f:
            f.write(opendkim_config)
        print(f"✅ Создан {opendkim_conf}")
    except Exception as e:
        print(f"❌ Ошибка создания {opendkim_conf}: {e}")
        return False
    
    # 2. Создаем TrustedHosts
    trusted_hosts_content = """127.0.0.1
::1
localhost
*.vashsender.ru
vashsender.ru
"""
    
    try:
        os.makedirs(os.path.dirname(trusted_hosts), exist_ok=True)
        with open(trusted_hosts, 'w') as f:
            f.write(trusted_hosts_content)
        print(f"✅ Создан {trusted_hosts}")
    except Exception as e:
        print(f"❌ Ошибка создания {trusted_hosts}: {e}")
        return False
    
    # 3. Получаем домены из базы данных и создаем KeyTable и SigningTable
    domains = Domain.objects.filter(dkim_verified=True)
    
    if not domains.exists():
        print("❌ Нет подтвержденных доменов с DKIM в базе данных")
        return False
    
    key_table_content = ""
    signing_table_content = ""
    
    for domain in domains:
        selector = domain.dkim_selector
        domain_name = domain.domain_name
        
        # Путь к приватному ключу
        if domain.private_key_path and os.path.exists(domain.private_key_path):
            key_path = domain.private_key_path
        else:
            # Используем стандартный путь
            keys_dir = getattr(settings, 'DKIM_KEYS_DIR', '/etc/opendkim/keys')
            key_path = os.path.join(keys_dir, domain_name, f"{selector}.private")
        
        if os.path.exists(key_path):
            # KeyTable: selector._domainkey.domain domain:selector:key_path
            key_table_content += f"{selector}._domainkey.{domain_name} {domain_name}:{selector}:{key_path}\n"
            
            # SigningTable: *@domain selector._domainkey.domain
            signing_table_content += f"*@{domain_name} {selector}._domainkey.{domain_name}\n"
            
            print(f"✅ Добавлен домен {domain_name} с селектором {selector}")
        else:
            print(f"❌ Приватный ключ не найден для домена {domain_name}: {key_path}")
    
    # Записываем KeyTable
    try:
        with open(key_table, 'w') as f:
            f.write(key_table_content)
        print(f"✅ Создан {key_table}")
    except Exception as e:
        print(f"❌ Ошибка создания {key_table}: {e}")
        return False
    
    # Записываем SigningTable
    try:
        with open(signing_table, 'w') as f:
            f.write(signing_table_content)
        print(f"✅ Создан {signing_table}")
    except Exception as e:
        print(f"❌ Ошибка создания {signing_table}: {e}")
        return False
    
    # 4. Устанавливаем правильные права доступа
    try:
        subprocess.run(['chown', '-R', 'opendkim:opendkim', '/etc/opendkim'], check=True)
        subprocess.run(['chmod', '600', '/etc/opendkim/keys/*/*'], shell=True, check=True)
        subprocess.run(['chmod', '644', key_table, signing_table, trusted_hosts], check=True)
        print("✅ Установлены права доступа")
    except Exception as e:
        print(f"❌ Ошибка установки прав доступа: {e}")
        return False
    
    return True

def setup_postfix_integration():
    """Настройка интеграции Postfix с OpenDKIM"""
    
    print("🔧 Настройка интеграции Postfix с OpenDKIM...")
    
    main_cf = "/etc/postfix/main.cf"
    
    # Добавляем milter настройки в main.cf
    milter_config = """
# OpenDKIM milter configuration
milter_protocol = 2
milter_default_action = accept
smtpd_milters = inet:localhost:12301
non_smtpd_milters = inet:localhost:12301
"""
    
    try:
        # Читаем текущий main.cf
        with open(main_cf, 'r') as f:
            content = f.read()
        
        # Проверяем, не добавлены ли уже настройки milter
        if 'smtpd_milters' not in content:
            with open(main_cf, 'a') as f:
                f.write(milter_config)
            print(f"✅ Добавлены milter настройки в {main_cf}")
        else:
            print(f"ℹ️  Milter настройки уже присутствуют в {main_cf}")
        
    except Exception as e:
        print(f"❌ Ошибка настройки Postfix: {e}")
        return False
    
    return True

def restart_services():
    """Перезапуск служб"""
    
    print("🔄 Перезапуск служб...")
    
    services = ['opendkim', 'postfix']
    
    for service in services:
        try:
            subprocess.run(['systemctl', 'restart', service], check=True)
            print(f"✅ Перезапущен {service}")
        except Exception as e:
            print(f"❌ Ошибка перезапуска {service}: {e}")
            return False
    
    return True

def test_opendkim():
    """Тест OpenDKIM"""
    
    print("🧪 Тестирование OpenDKIM...")
    
    try:
        result = subprocess.run(['systemctl', 'status', 'opendkim'], 
                              capture_output=True, text=True, check=True)
        print("✅ OpenDKIM запущен")
        
        # Проверяем логи
        result = subprocess.run(['journalctl', '-u', 'opendkim', '--no-pager', '-n', '10'], 
                              capture_output=True, text=True, check=False)
        if result.stdout:
            print("📋 Последние логи OpenDKIM:")
            print(result.stdout)
        
    except Exception as e:
        print(f"❌ Ошибка тестирования OpenDKIM: {e}")
        return False
    
    return True

def main():
    """Основная функция"""
    
    print("🚀 Автоматическая настройка OpenDKIM для VashSender")
    print("=" * 50)
    
    # Проверяем, что скрипт запущен от root
    if os.geteuid() != 0:
        print("❌ Скрипт должен быть запущен от root")
        sys.exit(1)
    
    # Выполняем настройку
    steps = [
        ("Настройка OpenDKIM конфигурации", setup_opendkim_config),
        ("Настройка интеграции Postfix", setup_postfix_integration),
        ("Перезапуск служб", restart_services),
        ("Тестирование OpenDKIM", test_opendkim),
    ]
    
    for step_name, step_func in steps:
        print(f"\n📋 {step_name}...")
        if not step_func():
            print(f"❌ Ошибка на этапе: {step_name}")
            sys.exit(1)
    
    print("\n🎉 Настройка OpenDKIM завершена успешно!")
    print("\n📝 Следующие шаги:")
    print("1. Убедитесь, что DNS записи для DKIM настроены правильно")
    print("2. Отправьте тестовое письмо для проверки подписи")
    print("3. Проверьте заголовки письма на наличие DKIM-Signature")

if __name__ == "__main__":
    main()
