import os
import time
from celery import shared_task
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction

from .models import ContactList, Contact, ImportTask
from .utils import parse_emails, validate_email_production


@shared_task(bind=True)
def import_contacts_async(self, task_id, file_path):
    """
    Асинхронная задача для импорта контактов с полной валидацией
    """
    try:
        # Получаем задачу импорта
        task = ImportTask.objects.get(id=task_id)
        
        # Обновляем статус на "обрабатывается"
        task.status = ImportTask.PROCESSING
        task.started_at = timezone.now()
        task.save()
        
        # Проверяем, что файл существует
        if not os.path.exists(file_path):
            task.status = ImportTask.FAILED
            task.error_message = f"File not found: {file_path}"
            task.completed_at = timezone.now()
            task.save()
            return False
        
        # Читаем email адреса из файла
        with open(file_path, 'rb') as f:
            emails = parse_emails(f, task.filename)
        
        total_emails = len(emails)
        task.total_emails = total_emails
        task.save()
        
        # Получаем все существующие email для быстрой проверки
        existing_emails = set(Contact.objects.filter(
            contact_list=task.contact_list
        ).values_list('email', flat=True))
        
        # Счетчики
        added = 0
        invalid_count = 0
        blacklisted_count = 0
        error_count = 0
        processed = 0
        skipped_count = 0
        
        # Батчинг для оптимизации
        contacts_to_create = []
        batch_size = 100  # Размер батча для создания контактов
        
        # Обрабатываем email адреса
        for i, email in enumerate(emails):
            try:
                processed += 1
                
                # Нормализуем email (lower, strip)
                email = email.lower().strip() if email else ''
                if not email:
                    skipped_count += 1
                    continue
                
                # Обновляем прогресс каждые 100 email
                if processed % 100 == 0:
                    task.processed_emails = processed
                    task.save()
                    
                    # Обновляем прогресс Celery задачи
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': processed,
                            'total': total_emails,
                            'status': f'Обработано {processed} из {total_emails} email адресов'
                        }
                    )
                
                # Быстрая проверка существования
                if email in existing_emails:
                    skipped_count += 1
                    continue
                
                # Полная валидация email
                validation_result = validate_email_production(email)
                
                if validation_result['is_valid']:
                    status_code = validation_result['status']
                    
                    # Создаем новый контакт
                    new_contact = Contact(
                        contact_list=task.contact_list,
                        email=email,
                        status=status_code
                    )
                    contacts_to_create.append(new_contact)
                    # Добавляем email в existing_emails, чтобы избежать дубликатов в батче
                    existing_emails.add(email)
                    
                    if status_code == Contact.BLACKLIST:
                        blacklisted_count += 1
                else:
                    # Добавляем невалидные email как INVALID
                    new_contact = Contact(
                        contact_list=task.contact_list,
                        email=email,
                        status=Contact.INVALID
                    )
                    contacts_to_create.append(new_contact)
                    # Добавляем email в existing_emails, чтобы избежать дубликатов в батче
                    existing_emails.add(email)
                    invalid_count += 1
                
                # Батчинг: сохраняем каждые batch_size контактов
                if len(contacts_to_create) >= batch_size:
                    try:
                        with transaction.atomic():
                            # Получаем email из батча для проверки
                            batch_emails = [c.email for c in contacts_to_create]
                            
                            # Проверяем, какие email уже существуют в базе
                            existing_in_batch = set(Contact.objects.filter(
                                contact_list=task.contact_list,
                                email__in=batch_emails
                            ).values_list('email', flat=True))
                            
                            # Фильтруем контакты, которые еще не существуют
                            new_contacts = [c for c in contacts_to_create if c.email not in existing_in_batch]
                            
                            if new_contacts:
                                # Используем bulk_create только для новых контактов
                                Contact.objects.bulk_create(new_contacts, ignore_conflicts=True)
                                added += len(new_contacts)
                            
                            # Обновляем existing_emails с новыми email из батча
                            for c in contacts_to_create:
                                existing_emails.add(c.email)
                        
                        contacts_to_create = []
                    except Exception as e:
                        error_count += len(contacts_to_create)
                        # Удаляем email из existing_emails, если батч не был создан
                        for c in contacts_to_create:
                            existing_emails.discard(c.email)
                        contacts_to_create = []
                        print(f"Error in batch create: {e}")
                        
            except Exception as e:
                error_count += 1
                print(f"Error processing email {email if 'email' in locals() else 'unknown'}: {e}")
                continue
        
        # Сохраняем оставшиеся контакты
        if contacts_to_create:
            try:
                with transaction.atomic():
                    # Получаем email из батча для проверки
                    batch_emails = [c.email for c in contacts_to_create]
                    
                    # Проверяем, какие email уже существуют в базе
                    existing_in_batch = set(Contact.objects.filter(
                        contact_list=task.contact_list,
                        email__in=batch_emails
                    ).values_list('email', flat=True))
                    
                    # Фильтруем контакты, которые еще не существуют
                    new_contacts = [c for c in contacts_to_create if c.email not in existing_in_batch]
                    
                    if new_contacts:
                        # Используем bulk_create только для новых контактов
                        Contact.objects.bulk_create(new_contacts, ignore_conflicts=True)
                        added += len(new_contacts)
            except Exception as e:
                error_count += len(contacts_to_create)
                print(f"Error in final batch create: {e}")
        
        # Завершаем задачу
        task.status = ImportTask.COMPLETED
        task.processed_emails = processed
        task.imported_count = added
        task.invalid_count = invalid_count
        task.blacklisted_count = blacklisted_count
        task.error_count = error_count
        task.completed_at = timezone.now()
        task.save()
        
        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass
        
        return True
        
    except Exception as e:
        # Обновляем задачу с ошибкой
        try:
            task = ImportTask.objects.get(id=task_id)
            task.status = ImportTask.FAILED
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save()
        except:
            pass
        
        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass
        
        return False


@shared_task
def validate_contact_batch(contact_ids):
    """
    Валидация батча контактов (для перевалидации существующих)
    """
    contacts = Contact.objects.filter(id__in=contact_ids)
    
    for contact in contacts:
        try:
            validation_result = validate_email_production(contact.email)
            if validation_result['is_valid']:
                contact.status = validation_result['status']
            else:
                contact.status = Contact.INVALID
            contact.save()
        except Exception:
            contact.status = Contact.INVALID
            contact.save()
    
    return len(contacts) 