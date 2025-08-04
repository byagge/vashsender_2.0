#!/usr/bin/env python
"""
Скрипт для исправления дублированного CloudPayments Public ID
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

def fix_cloudpayments_public_id():
    """Исправляем дублированный Public ID"""
    print("🔧 Исправление дублированного CloudPayments Public ID...")
    
    try:
        settings = BillingSettings.get_settings()
        
        current_public_id = settings.cloudpayments_public_id
        print(f"📋 Текущий Public ID: {current_public_id}")
        
        if current_public_id and len(current_public_id) > 50:  # Слишком длинный - вероятно дублирован
            # Извлекаем первую половину
            half_length = len(current_public_id) // 2
            fixed_public_id = current_public_id[:half_length]
            
            print(f"🔧 Исправляем на: {fixed_public_id}")
            
            settings.cloudpayments_public_id = fixed_public_id
            settings.save()
            
            print("✅ Public ID исправлен!")
            return True
        else:
            print("ℹ️ Public ID выглядит корректно")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при исправлении: {e}")
        return False

if __name__ == "__main__":
    fix_cloudpayments_public_id() 