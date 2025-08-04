#!/usr/bin/env python
"""
Скрипт для быстрой настройки CloudPayments
Использование: python setup_cloudpayments.py
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from apps.billing.models import BillingSettings


def setup_cloudpayments():
    """Настройка CloudPayments"""
    print("=== Настройка CloudPayments ===\n")
    
    # Получаем или создаем настройки
    settings, created = BillingSettings.objects.get_or_create(pk=1)
    
    if created:
        print("✅ Созданы новые настройки биллинга")
    else:
        print("ℹ️  Настройки биллинга уже существуют")
    
    print(f"\nТекущие настройки:")
    print(f"Public ID: {settings.cloudpayments_public_id or 'НЕ УСТАНОВЛЕН'}")
    print(f"API Secret: {'УСТАНОВЛЕН' if settings.cloudpayments_api_secret else 'НЕ УСТАНОВЛЕН'}")
    print(f"Тестовый режим: {'Да' if settings.cloudpayments_test_mode else 'Нет'}")
    
    # Запрашиваем настройки
    print("\n" + "="*50)
    
    # Public ID
    current_public_id = settings.cloudpayments_public_id
    if current_public_id:
        print(f"Текущий Public ID: {current_public_id}")
        change_public_id = input("Изменить Public ID? (y/N): ").lower().strip()
        if change_public_id == 'y':
            new_public_id = input("Введите новый Public ID: ").strip()
            if new_public_id:
                settings.cloudpayments_public_id = new_public_id
                print("✅ Public ID обновлен")
    else:
        new_public_id = input("Введите Public ID CloudPayments: ").strip()
        if new_public_id:
            settings.cloudpayments_public_id = new_public_id
            print("✅ Public ID установлен")
    
    # API Secret
    current_api_secret = settings.cloudpayments_api_secret
    if current_api_secret:
        print(f"API Secret: {'*' * len(current_api_secret)}")
        change_api_secret = input("Изменить API Secret? (y/N): ").lower().strip()
        if change_api_secret == 'y':
            new_api_secret = input("Введите новый API Secret: ").strip()
            if new_api_secret:
                settings.cloudpayments_api_secret = new_api_secret
                print("✅ API Secret обновлен")
    else:
        new_api_secret = input("Введите API Secret CloudPayments: ").strip()
        if new_api_secret:
            settings.cloudpayments_api_secret = new_api_secret
            print("✅ API Secret установлен")
    
    # Режим работы
    print(f"\nТекущий режим: {'Тестовый' if settings.cloudpayments_test_mode else 'Продакшн'}")
    change_mode = input("Изменить режим? (y/N): ").lower().strip()
    if change_mode == 'y':
        mode = input("Выберите режим (test/prod): ").lower().strip()
        if mode == 'prod':
            settings.cloudpayments_test_mode = False
            print("✅ Переключен в продакшн режим")
        elif mode == 'test':
            settings.cloudpayments_test_mode = True
            print("✅ Переключен в тестовый режим")
    
    # Сохраняем изменения
    if settings.pk:  # Если есть изменения
        settings.save()
        print("\n✅ Настройки сохранены")
    
    # Финальный вывод
    print("\n" + "="*50)
    print("ФИНАЛЬНЫЕ НАСТРОЙКИ:")
    print(f"Public ID: {settings.cloudpayments_public_id or 'НЕ УСТАНОВЛЕН'}")
    print(f"API Secret: {'УСТАНОВЛЕН' if settings.cloudpayments_api_secret else 'НЕ УСТАНОВЛЕН'}")
    print(f"Режим: {'Тестовый' if settings.cloudpayments_test_mode else 'Продакшн'}")
    
    # Проверки
    print("\nПРОВЕРКИ:")
    if not settings.cloudpayments_public_id:
        print("❌ Public ID не установлен!")
        print("   Это необходимо для работы виджета CloudPayments")
    else:
        print("✅ Public ID установлен")
    
    if not settings.cloudpayments_api_secret:
        print("❌ API Secret не установлен!")
        print("   Это необходимо для проверки webhook'ов")
    else:
        print("✅ API Secret установлен")
    
    if settings.cloudpayments_test_mode:
        print("ℹ️  Работает в тестовом режиме")
        print("   Для продакшна выполните: python manage.py init_cloudpayments_settings --production-mode")
    else:
        print("✅ Работает в продакшн режиме")
    
    print("\n" + "="*50)
    print("Следующие шаги:")
    print("1. Проверьте работу на странице покупки: /purchase/confirmation/?plan_id=1")
    print("2. Протестируйте оплату с тестовыми картами")
    print("3. Настройте webhook URL в личном кабинете CloudPayments")
    print("4. Для продакшна убедитесь, что используете продакшн ключи")


if __name__ == "__main__":
    try:
        setup_cloudpayments()
    except KeyboardInterrupt:
        print("\n\n❌ Настройка прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1) 