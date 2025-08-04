#!/usr/bin/env python
"""
Тестовый скрипт для проверки глубокой валидации email адресов
"""

import os
import sys
import django
import time

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from apps.mailer.utils import validate_email_production, classify_email, check_smtp_connection
from apps.mailer.models import Contact

def test_email_validation():
    """Тестирует валидацию различных email адресов"""
    
    test_emails = [
        # Существующие email (должны быть VALID)
        "test@gmail.com",
        "admin@yahoo.com", 
        "support@hotmail.com",
        "info@outlook.com",
        "contact@mail.ru",
        "help@yandex.ru",
        
        # Несуществующие email (должны быть INVALID)
        "nonexistent123456789@gmail.com",
        "fakeuser123456789@yahoo.com",
        "invalid123456789@hotmail.com",
        "wrong123456789@outlook.com",
        "bademail123456789@mail.ru",
        "fake123456789@yandex.ru",
        
        # Неправильный синтаксис (должны быть INVALID)
        "invalid-email",
        "test@",
        "@domain.com",
        "test..test@domain.com",
        "test@domain..com",
        
        # Зарезервированные домены (должны быть INVALID)
        "test@example.com",
        "user@test.com",
        "admin@localhost.com",
        
        # Disposable домены (должны быть BLACKLIST)
        "temp@10minutemail.com",
        "user@guerrillamail.com",
        "test@mailinator.com",
        "temp@yopmail.com",
        
        # Домены без MX записей (должны быть INVALID)
        "test@nonexistentdomain123456789.com",
        "user@invaliddomain123456789.org",
    ]
    
    print("=== Тест глубокой валидации email ===\n")
    
    results = {
        'valid': [],
        'invalid': [],
        'blacklist': [],
        'errors': []
    }
    
    for i, email in enumerate(test_emails, 1):
        print(f"[{i:2d}/{len(test_emails)}] Проверяем: {email}")
        
        try:
            start_time = time.time()
            
            # Полная валидация
            validation_result = validate_email_production(email)
            
            # Быстрая классификация
            classification = classify_email(email)
            
            elapsed_time = time.time() - start_time
            
            # Анализируем результат
            status = validation_result['status']
            confidence = validation_result.get('confidence', 'unknown')
            
            if status == Contact.VALID:
                results['valid'].append(email)
                print(f"    ✅ VALID ({confidence}) - {elapsed_time:.2f}с")
            elif status == Contact.INVALID:
                results['invalid'].append(email)
                errors = ', '.join(validation_result.get('errors', []))
                print(f"    ❌ INVALID - {errors} ({elapsed_time:.2f}с)")
            elif status == Contact.BLACKLIST:
                results['blacklist'].append(email)
                print(f"    ⚠️  BLACKLIST - {elapsed_time:.2f}с")
            
            # Проверяем соответствие классификации
            if classification != status:
                print(f"    ⚠️  ВНИМАНИЕ: classify_email() вернул {classification}, а validate_email_production() вернул {status}")
            
        except Exception as e:
            results['errors'].append(f"{email}: {str(e)}")
            print(f"    💥 ОШИБКА: {str(e)}")
        
        print()
    
    # Выводим статистику
    print("=== СТАТИСТИКА ===")
    print(f"Всего проверено: {len(test_emails)}")
    print(f"VALID: {len(results['valid'])}")
    print(f"INVALID: {len(results['invalid'])}")
    print(f"BLACKLIST: {len(results['blacklist'])}")
    print(f"Ошибки: {len(results['errors'])}")
    
    print("\n=== ДЕТАЛИ ===")
    
    if results['valid']:
        print(f"\n✅ Валидные email ({len(results['valid'])}):")
        for email in results['valid']:
            print(f"  - {email}")
    
    if results['invalid']:
        print(f"\n❌ Невалидные email ({len(results['invalid'])}):")
        for email in results['invalid']:
            print(f"  - {email}")
    
    if results['blacklist']:
        print(f"\n⚠️  Blacklist email ({len(results['blacklist'])}):")
        for email in results['blacklist']:
            print(f"  - {email}")
    
    if results['errors']:
        print(f"\n💥 Ошибки ({len(results['errors'])}):")
        for error in results['errors']:
            print(f"  - {error}")

def test_smtp_connection():
    """Тестирует SMTP подключение для конкретных email"""
    
    print("\n=== Тест SMTP подключения ===\n")
    
    test_cases = [
        ("test@gmail.com", "Должен существовать"),
        ("nonexistent123456789@gmail.com", "Не должен существовать"),
        ("admin@yahoo.com", "Должен существовать"),
        ("fakeuser123456789@yahoo.com", "Не должен существовать"),
    ]
    
    for email, description in test_cases:
        print(f"Проверяем: {email} ({description})")
        
        try:
            start_time = time.time()
            result = check_smtp_connection(email)
            elapsed_time = time.time() - start_time
            
            if result['valid']:
                print(f"  ✅ Существует - {elapsed_time:.2f}с")
            else:
                print(f"  ❌ Не существует: {result['error']} - {elapsed_time:.2f}с")
                
        except Exception as e:
            print(f"  💥 Ошибка: {str(e)}")
        
        print()

if __name__ == '__main__':
    test_email_validation()
    test_smtp_connection() 