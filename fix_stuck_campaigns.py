#!/usr/bin/env python3
"""
Скрипт для быстрого исправления зависших кампаний
Запуск: python fix_stuck_campaigns.py
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from django.utils import timezone
from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.tasks import auto_fix_stuck_campaigns


def main():
    print("=== Исправление зависших кампаний ===")
    print(f"Время: {datetime.now()}")
    
    # Находим зависшие кампании (старше 15 минут)
    timeout_minutes = 15
    cutoff_time = timezone.now() - timedelta(minutes=timeout_minutes)
    
    stuck_campaigns = Campaign.objects.filter(
        status=Campaign.STATUS_SENDING,
        updated_at__lt=cutoff_time
    )
    
    print(f"Найдено {stuck_campaigns.count()} зависших кампаний")
    
    if not stuck_campaigns.exists():
        print("✅ Зависших кампаний не найдено")
        return
    
    # Показываем детали
    for campaign in stuck_campaigns:
        print(f"\n📧 {campaign.name}")
        print(f"   ID: {campaign.id}")
        print(f"   Обновлена: {campaign.updated_at}")
        print(f"   Task ID: {campaign.celery_task_id}")
        
        # Статистика отправки
        sent_count = CampaignRecipient.objects.filter(
            campaign=campaign, 
            is_sent=True
        ).count()
        
        total_count = CampaignRecipient.objects.filter(campaign=campaign).count()
        
        print(f"   Отправлено: {sent_count}/{total_count}")
        
        # Контакты
        total_contacts = 0
        for contact_list in campaign.contact_lists.all():
            total_contacts += contact_list.contacts.count()
        
        print(f"   Контактов: {total_contacts}")
    
    # Запускаем исправление
    print(f"\n🚀 Запуск автоматического исправления...")
    
    try:
        result = auto_fix_stuck_campaigns.delay()
        print(f"Задача запущена: {result.id}")
        
        # Ждем завершения
        result.get(timeout=120)
        print("✅ Исправление завершено")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return 1
    
    # Финальная проверка
    remaining_stuck = Campaign.objects.filter(
        status=Campaign.STATUS_SENDING,
        updated_at__lt=cutoff_time
    ).count()
    
    print(f"\n📊 Результат:")
    print(f"   Оставшихся зависших: {remaining_stuck}")
    
    if remaining_stuck == 0:
        print("✅ Все зависшие кампании исправлены!")
        return 0
    else:
        print("⚠️  Некоторые кампании все еще зависли")
        return 1


if __name__ == '__main__':
    exit(main()) 