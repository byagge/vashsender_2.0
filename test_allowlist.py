#!/usr/bin/env python3
"""
Тест для проверки функциональности allowlist доменов
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apps.mailer.utils import (
    is_allowlist_domain, 
    validate_email_production, 
    classify_email,
    validate_email_fast,
    validate_email_strict
)

def test_allowlist_functionality():
    """Тестирует работу allowlist доменов"""
    
    print("=== Тест функциональности allowlist доменов ===\n")
    
    # Тестовые email адреса
    test_emails = [
        # Allowlist домены (должны проходить валидацию, но не попадать в черный список)
        "test@gmail.com",
        "user@yahoo.com", 
        "example@mail.ru",
        "sample@yandex.ru",
        "test@outlook.com",
        "user@hotmail.com",
        
        # Обычные домены (должны работать как обычно)
        "test@example.com",
        "user@company.org",
        "sample@business.net"
    ]
    
    print("1. Проверка функции is_allowlist_domain:")
    for email in test_emails:
        domain = email.split('@')[1]
        is_allowlist = is_allowlist_domain(domain)
        print(f"   {domain}: {'✓ Allowlist' if is_allowlist else '✗ Не allowlist'}")
    
    print("\n2. Проверка validate_email_fast:")
    for email in test_emails:
        result = validate_email_fast(email)
        status = result.get('status', 'UNKNOWN')
        reason = result.get('reason', 'No reason')
        print(f"   {email}: {status} - {reason}")
    
    print("\n3. Проверка classify_email:")
    for email in test_emails:
        status = classify_email(email)
        print(f"   {email}: {status}")
    
    print("\n4. Проверка validate_email_production:")
    for email in test_emails:
        result = validate_email_production(email)
        is_valid = result.get('is_valid', False)
        status = result.get('status', 'UNKNOWN')
        confidence = result.get('confidence', 'unknown')
        errors = result.get('errors', [])
        warnings = result.get('warnings', [])
        
        print(f"   {email}:")
        print(f"     Valid: {is_valid}, Status: {status}, Confidence: {confidence}")
        if errors:
            print(f"     Errors: {', '.join(errors)}")
        if warnings:
            print(f"     Warnings: {', '.join(warnings)}")
    
    print("\n=== Тест завершен ===")

if __name__ == "__main__":
    test_allowlist_functionality()
