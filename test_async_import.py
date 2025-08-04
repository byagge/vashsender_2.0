#!/usr/bin/env python
"""
Тестовый скрипт для проверки асинхронного импорта контактов
"""

import os
import sys
import django
import tempfile

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.dev')
django.setup()

from apps.mailer.tasks import import_contacts_async
from apps.mailer.models import ImportTask, ContactList, Contact
from django.contrib.auth import get_user_model

User = get_user_model()

def create_test_file():
    """Создает тестовый файл с email адресами"""
    test_emails = [
        "test1@gmail.com",
        "test2@yahoo.com", 
        "test3@hotmail.com",
        "invalid-email",
        "test4@example.com",
        "test5@mail.ru",
        "test6@yandex.ru",
        "test7@10minutemail.com",  # disposable
        "test8@guerrillamail.com", # disposable
        "test9@outlook.com",
        "test10@icloud.com"
    ]
    
    # Создаем временный файл
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    temp_file.write('\n'.join(test_emails))
    temp_file.close()
    
    return temp_file.name

def test_async_import():
    """Тестирует асинхронный импорт"""
    print("=== Тест асинхронного импорта ===")
    
    # Получаем или создаем тестового пользователя
    try:
        user = User.objects.get(username='test_user')
    except User.DoesNotExist:
        user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        print(f"Создан тестовый пользователь: {user.username}")
    
    # Получаем или создаем тестовый список контактов
    try:
        contact_list = ContactList.objects.get(owner=user, name='Test List')
    except ContactList.DoesNotExist:
        contact_list = ContactList.objects.create(
            owner=user,
            name='Test List'
        )
        print(f"Создан тестовый список: {contact_list.name}")
    
    # Создаем тестовый файл
    file_path = create_test_file()
    print(f"Создан тестовый файл: {file_path}")
    
    # Создаем задачу импорта
    import_task = ImportTask.objects.create(
        contact_list=contact_list,
        filename='test_emails.txt',
        status=ImportTask.PENDING
    )
    print(f"Создана задача импорта: {import_task.id}")
    
    try:
        # Запускаем асинхронную задачу
        print("Запускаем асинхронную задачу...")
        result = import_contacts_async.delay(str(import_task.id), file_path)
        
        print(f"Celery task ID: {result.id}")
        print("Задача запущена. Проверяем статус...")
        
        # Ждем завершения задачи
        task_result = result.get(timeout=60)  # Ждем максимум 60 секунд
        print(f"Задача завершена: {task_result}")
        
        # Проверяем результат
        import_task.refresh_from_db()
        print(f"Статус задачи: {import_task.status}")
        print(f"Обработано email: {import_task.processed_emails}")
        print(f"Импортировано: {import_task.imported_count}")
        print(f"Недействительных: {import_task.invalid_count}")
        print(f"В черном списке: {import_task.blacklisted_count}")
        print(f"Ошибок: {import_task.error_count}")
        
        # Проверяем созданные контакты
        contacts = Contact.objects.filter(contact_list=contact_list)
        print(f"\nВсего контактов в списке: {contacts.count()}")
        
        for status in ['valid', 'invalid', 'blacklist']:
            count = contacts.filter(status=status).count()
            print(f"Статус '{status}': {count}")
        
        print("\nДетали контактов:")
        for contact in contacts[:5]:  # Показываем первые 5
            print(f"  {contact.email} -> {contact.status}")
        
    except Exception as e:
        print(f"Ошибка при выполнении задачи: {e}")
        import_task.refresh_from_db()
        print(f"Статус задачи: {import_task.status}")
        print(f"Сообщение об ошибке: {import_task.error_message}")
    
    finally:
        # Удаляем временный файл
        try:
            os.unlink(file_path)
            print(f"Удален временный файл: {file_path}")
        except:
            pass

if __name__ == '__main__':
    test_async_import() 