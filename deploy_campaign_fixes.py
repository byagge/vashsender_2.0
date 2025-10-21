#!/usr/bin/env python
"""
Скрипт для деплоя исправлений кампаний на сервер.
Загружает исправленные файлы и перезапускает сервисы.
"""

import os
import sys

def deploy_fixes():
    """
    Деплой исправлений для кампаний.
    """
    print("=== Деплой исправлений кампаний ===")
    
    # Файлы для обновления
    files_to_update = [
        'apps/campaigns/views.py',
        'apps/campaigns/tasks.py',
    ]
    
    print("Файлы для обновления:")
    for file in files_to_update:
        if os.path.exists(file):
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - не найден")
    
    print("\n=== Инструкции для сервера ===")
    print("1. Загрузите обновленные файлы на сервер:")
    print("   scp apps/campaigns/views.py user@server:/var/www/vashsender/apps/campaigns/")
    print("   scp apps/campaigns/tasks.py user@server:/var/www/vashsender/apps/campaigns/")
    
    print("\n2. На сервере выполните:")
    print("   cd /var/www/vashsender")
    print("   sudo systemctl restart vashsender-celery-worker.service")
    print("   sudo systemctl restart gunicorn.service")
    
    print("\n3. Проверьте логи:")
    print("   sudo journalctl -u vashsender-celery-worker.service -f")
    
    print("\n4. Очистите зависшие задачи (если нужно):")
    print("   python cleanup_celery_queue.py")

if __name__ == '__main__':
    deploy_fixes()
