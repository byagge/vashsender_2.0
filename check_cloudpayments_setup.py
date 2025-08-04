#!/usr/bin/env python
"""
Скрипт для проверки и настройки CloudPayments
"""

import os
import sys
import django

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from apps.billing.models import BillingSettings

def check_cloudpayments_setup():
    """Проверяем настройки CloudPayments"""
    print("🔍 Проверка настроек CloudPayments...")
    
    try:
        settings = BillingSettings.get_settings()
        
        print(f"📋 Текущие настройки:")
        print(f"   Public ID: {settings.cloudpayments_public_id or 'НЕ УСТАНОВЛЕН'}")
        print(f"   API Secret: {'*' * len(settings.cloudpayments_api_secret) if settings.cloudpayments_api_secret else 'НЕ УСТАНОВЛЕН'}")
        print(f"   Тестовый режим: {'Да' if settings.cloudpayments_test_mode else 'Нет'}")
        
        if not settings.cloudpayments_public_id:
            print("\n❌ Public ID не настроен!")
            print("Для настройки используйте команду:")
            print("python manage.py init_cloudpayments_settings --public-id YOUR_PUBLIC_ID")
            return False
        
        print("\n✅ Настройки CloudPayments корректны")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при проверке настроек: {e}")
        return False

if __name__ == "__main__":
    check_cloudpayments_setup() 