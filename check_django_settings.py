#!/usr/bin/env python3
"""
Проверка настроек Django для DKIM
"""

import os
import sys

# Добавляем путь к Django проекту
sys.path.append('/var/www/vashsender')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')

import django
django.setup()

from django.conf import settings
from apps.emails.models import Domain

def check_email_settings():
    """Проверка настроек email"""
    print("🔍 Проверка настроек email в Django...")
    
    print(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'НЕ ЗАДАНО')}")
    print(f"EMAIL_PORT: {getattr(settings, 'EMAIL_PORT', 'НЕ ЗАДАНО')}")
    print(f"EMAIL_USE_TLS: {getattr(settings, 'EMAIL_USE_TLS', 'НЕ ЗАДАНО')}")
    print(f"EMAIL_USE_SSL: {getattr(settings, 'EMAIL_USE_SSL', 'НЕ ЗАДАНО')}")
    print(f"EMAIL_USE_OPENDKIM: {getattr(settings, 'EMAIL_USE_OPENDKIM', 'НЕ ЗАДАНО')}")
    print(f"DEFAULT_FROM_EMAIL: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'НЕ ЗАДАНО')}")
    
    # Проверяем правильность настроек для OpenDKIM
    if getattr(settings, 'EMAIL_HOST', '') == 'localhost' and getattr(settings, 'EMAIL_PORT', 0) == 25:
        print("✅ Email настроен для отправки через localhost (Postfix)")
    else:
        print("❌ Email не настроен для localhost. Нужно:")
        print("   EMAIL_HOST = 'localhost'")
        print("   EMAIL_PORT = 25")

def check_domains():
    """Проверка доменов в базе данных"""
    print("\n🔍 Проверка доменов в базе данных...")
    
    domains = Domain.objects.all()
    
    if not domains.exists():
        print("❌ Нет доменов в базе данных")
        return
    
    for domain in domains:
        print(f"\n📋 Домен: {domain.domain_name}")
        print(f"   DKIM подтвержден: {'✅' if domain.dkim_verified else '❌'}")
        print(f"   Селектор: {domain.dkim_selector}")
        print(f"   Путь к ключу: {domain.private_key_path or 'НЕ ЗАДАН'}")
        
        # Проверяем ключ в стандартном месте
        keys_dir = getattr(settings, 'DKIM_KEYS_DIR', '/etc/opendkim/keys')
        standard_key_path = os.path.join(keys_dir, domain.domain_name, f"{domain.dkim_selector}.private")
        
        if os.path.exists(standard_key_path):
            print(f"   Ключ в OpenDKIM: ✅ {standard_key_path}")
        else:
            print(f"   Ключ в OpenDKIM: ❌ {standard_key_path}")

def check_campaign_from_domains():
    """Проверка доменов отправителей в кампаниях"""
    print("\n🔍 Проверка доменов отправителей в кампаниях...")
    
    try:
        from apps.campaigns.models import Campaign
        from apps.emails.models import SenderEmail
        
        # Получаем уникальные домены из SenderEmail
        sender_emails = SenderEmail.objects.all()
        
        if not sender_emails.exists():
            print("❌ Нет настроенных email отправителей")
            return
        
        sender_domains = set()
        for sender_email in sender_emails:
            if '@' in sender_email.email:
                domain = sender_email.email.split('@')[1]
                sender_domains.add(domain)
        
        print(f"Найдено доменов отправителей: {len(sender_domains)}")
        
        # Проверяем, есть ли DKIM для каждого домена
        for domain_name in sender_domains:
            try:
                domain = Domain.objects.get(domain_name=domain_name)
                if domain.dkim_verified:
                    print(f"✅ {domain_name} - DKIM настроен")
                else:
                    print(f"❌ {domain_name} - DKIM не подтвержден")
            except Domain.DoesNotExist:
                print(f"❌ {domain_name} - домен не найден в базе данных")
                
    except Exception as e:
        print(f"❌ Ошибка проверки кампаний: {e}")

def main():
    """Основная функция"""
    
    print("🔍 Проверка настроек Django для DKIM")
    print("=" * 50)
    
    check_email_settings()
    check_domains()
    check_campaign_from_domains()
    
    print("\n💡 Рекомендации:")
    print("1. Убедитесь, что EMAIL_HOST = 'localhost' и EMAIL_PORT = 25")
    print("2. Убедитесь, что EMAIL_USE_OPENDKIM = True")
    print("3. Все домены отправителей должны быть в базе данных с подтвержденным DKIM")
    print("4. Приватные ключи должны существовать в /etc/opendkim/keys/")

if __name__ == "__main__":
    main()
