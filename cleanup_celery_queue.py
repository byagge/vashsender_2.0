#!/usr/bin/env python
"""
Скрипт для очистки зависших задач Celery в очереди campaigns.
Используйте если в очереди накопились задачи от удалённых кампаний.
"""

import os
import sys
import django
from django.conf import settings

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')
django.setup()

from celery import Celery
from apps.campaigns.models import Campaign

def cleanup_campaign_queue():
    """
    Очищает очередь campaigns от задач для несуществующих кампаний.
    """
    app = Celery('vashsender')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    
    # Получаем инспектор Celery
    inspect = app.control.inspect()
    
    # Проверяем активные задачи
    active_tasks = inspect.active()
    if not active_tasks:
        print("Нет активных задач Celery")
        return
    
    print("Проверяем активные задачи...")
    
    total_cleaned = 0
    
    for worker, tasks in active_tasks.items():
        print(f"\nВоркер: {worker}")
        
        for task in tasks:
            task_name = task.get('name', '')
            task_args = task.get('args', [])
            task_id = task.get('id', '')
            
            # Проверяем только задачи send_campaign
            if 'send_campaign' in task_name and task_args:
                campaign_id = task_args[0]
                print(f"  Задача: {task_id} для кампании: {campaign_id}")
                
                # Проверяем существует ли кампания
                try:
                    campaign = Campaign.objects.get(id=campaign_id)
                    print(f"    ✓ Кампания существует: {campaign.name} ({campaign.status})")
                except Campaign.DoesNotExist:
                    print(f"    ✗ Кампания удалена - отменяем задачу")
                    
                    # Отменяем задачу
                    app.control.revoke(task_id, terminate=True)
                    total_cleaned += 1
    
    print(f"\nОтменено задач: {total_cleaned}")
    
    # Проверяем очередь Redis
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        
        # Проверяем длину очереди campaigns
        queue_length = r.llen('celery')
        print(f"Задач в основной очереди: {queue_length}")
        
        campaigns_queue_length = r.llen('campaigns')
        print(f"Задач в очереди campaigns: {campaigns_queue_length}")
        
        if campaigns_queue_length > 0:
            print("В очереди campaigns есть задачи. Проверьте их вручную.")
        
    except ImportError:
        print("Redis не установлен - не могу проверить длину очереди")
    except Exception as e:
        print(f"Ошибка при проверке Redis: {e}")

if __name__ == '__main__':
    cleanup_campaign_queue()
