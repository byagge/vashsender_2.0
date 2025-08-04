#!/usr/bin/env python
"""
Тестовый скрипт для проверки работы activate_payment
"""

import os
import sys
import django
import json

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from apps.billing.models import Plan, PurchasedPlan, BillingSettings
from apps.accounts.models import User
from django.utils import timezone
from datetime import timedelta

def test_activation():
    """Тестируем создание PurchasedPlan"""
    print("🧪 Тестирование активации тарифа...")
    
    try:
        # Получаем тестового пользователя
        user = User.objects.filter(email='admin@vashsender.ru').first()
        if not user:
            print("❌ Пользователь admin@vashsender.ru не найден")
            return False
        
        # Получаем план
        plan = Plan.objects.filter(id=69).first()
        if not plan:
            print("❌ План с ID 69 не найден")
            return False
        
        print(f"✅ Найден пользователь: {user.email}")
        print(f"✅ Найден план: {plan.title}")
        
        # Тестовые данные платежа
        test_payment_data = {
            'transactionId': 'TEST-' + str(int(timezone.now().timestamp())),
            'status': 'success',
            'amount': float(plan.get_final_price()),
            'currency': 'RUB'
        }
        
        print(f"📋 Тестовые данные платежа: {test_payment_data}")
        
        # Создаем PurchasedPlan
        purchased_plan = PurchasedPlan.objects.create(
            user=user,
            plan=plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            is_active=True,
            amount_paid=plan.get_final_price(),
            payment_method='cloudpayments',
            transaction_id=test_payment_data['transactionId'],
            cloudpayments_data=test_payment_data
        )
        
        print(f"✅ PurchasedPlan создан успешно!")
        print(f"   ID: {purchased_plan.id}")
        print(f"   Transaction ID: {purchased_plan.transaction_id}")
        print(f"   Amount: {purchased_plan.amount_paid}")
        print(f"   End date: {purchased_plan.end_date}")
        
        # Обновляем текущий план пользователя
        user.current_plan = plan
        user.plan_expiry = purchased_plan.end_date
        user.save()
        
        print(f"✅ План пользователя обновлен: {user.current_plan.title}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_activation() 