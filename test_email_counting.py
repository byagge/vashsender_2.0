#!/usr/bin/env python
"""
Тестовый скрипт для проверки подсчета отправленных писем
"""

import os
import sys
import django

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from apps.billing.utils import get_user_plan_info, update_plan_emails_sent, get_user_emails_sent_today
from apps.accounts.models import User
from apps.campaigns.models import EmailTracking, Campaign
from apps.mailer.models import Contact
from django.utils import timezone
from datetime import timedelta

def test_email_counting():
    """Тестируем подсчет отправленных писем"""
    print("🧪 Тестирование подсчета отправленных писем...")
    
    try:
        # Получаем тестового пользователя
        user = User.objects.filter(email='admin@vashsender.ru').first()
        if not user:
            print("❌ Пользователь admin@vashsender.ru не найден")
            return False
        
        print(f"✅ Найден пользователь: {user.email}")
        
        # Подсчитываем общее количество писем пользователя
        total_emails = EmailTracking.objects.filter(campaign__user=user).count()
        print(f"📧 Общее количество писем пользователя: {total_emails}")
        
        # Подсчитываем письма за сегодня
        emails_today = get_user_emails_sent_today(user)
        print(f"📧 Писем отправлено сегодня: {emails_today}")
        
        # Получаем информацию о плане
        plan_info = get_user_plan_info(user)
        print(f"📋 Информация о плане:")
        print(f"   - Есть план: {plan_info.get('has_plan', False)}")
        if plan_info.get('has_plan'):
            print(f"   - Название плана: {plan_info.get('plan_name')}")
            print(f"   - Тип плана: {plan_info.get('plan_type')}")
            print(f"   - Отправлено писем: {plan_info.get('emails_sent', 0)}")
            print(f"   - Отправлено сегодня: {plan_info.get('emails_sent_today', 0)}")
            print(f"   - Осталось писем: {plan_info.get('emails_remaining', 0)}")
            print(f"   - Дней до истечения: {plan_info.get('days_remaining', 0)}")
        
        # Проверяем кампании пользователя
        campaigns = Campaign.objects.filter(user=user)
        print(f"📧 Количество кампаний пользователя: {campaigns.count()}")
        
        for campaign in campaigns:
            campaign_emails = EmailTracking.objects.filter(campaign=campaign).count()
            print(f"   - Кампания '{campaign.name}': {campaign_emails} писем")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_email_counting() 