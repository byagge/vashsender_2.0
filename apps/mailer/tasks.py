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
    Может выполняться как через Celery (bind=True), так и синхронно
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Проверяем, выполняется ли задача через Celery
    is_celery_task = hasattr(self, 'update_state')
    
    try:
        logger.info(f"Starting import task {task_id} with file {file_path} (Celery: {is_celery_task})")
        
        # Получаем задачу импорта
        task = ImportTask.objects.get(id=task_id)
        logger.info(f"Found import task: {task.filename}, contact_list: {task.contact_list.id}")
        
        # Обновляем статус на "обрабатывается"
        task.status = ImportTask.PROCESSING
        task.started_at = timezone.now()
        task.save()
        logger.info(f"Task status updated to PROCESSING")
        
        # Проверяем, что файл существует
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            task.status = ImportTask.FAILED
            task.error_message = error_msg
            task.completed_at = timezone.now()
            task.save()
            return False
        
        logger.info(f"File exists: {file_path}, size: {os.path.getsize(file_path)} bytes")
        
        # Читаем email адреса из файла
        with open(file_path, 'rb') as f:
            emails = parse_emails(f, task.filename)
        
        total_emails = len(emails)
        logger.info(f"Parsed {total_emails} emails from file")
        task.total_emails = total_emails
        task.save()
        
        if total_emails == 0:
            logger.warning("No emails found in file")
            task.status = ImportTask.COMPLETED
            task.processed_emails = 0
            task.imported_count = 0
            task.completed_at = timezone.now()
            task.save()
            return True
        
        # Получаем все существующие email для быстрой проверки
        existing_emails = set(Contact.objects.filter(
            contact_list=task.contact_list
        ).values_list('email', flat=True))
        logger.info(f"Found {len(existing_emails)} existing emails in contact list")
        
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
        
        logger.info(f"Starting to process {total_emails} emails")
        
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
                    
                    # Обновляем прогресс Celery задачи (если выполняется через Celery)
                    if is_celery_task:
                        try:
                            self.update_state(
                                state='PROGRESS',
                                meta={
                                    'current': processed,
                                    'total': total_emails,
                                    'status': f'Обработано {processed} из {total_emails} email адресов'
                                }
                            )
                        except Exception:
                            pass  # Игнорируем ошибки обновления состояния
                
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
                                logger.info(f"Created batch of {len(new_contacts)} contacts (total added: {added})")
                            else:
                                logger.warning(f"All {len(contacts_to_create)} contacts in batch already exist")
                            
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
                        logger.error(f"Error in batch create: {e}", exc_info=True)
                        
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
                        logger.info(f"Created final batch of {len(new_contacts)} contacts (total added: {added})")
                    else:
                        logger.warning(f"All {len(contacts_to_create)} contacts in final batch already exist")
            except Exception as e:
                error_count += len(contacts_to_create)
                logger.error(f"Error in final batch create: {e}", exc_info=True)
        
        # Завершаем задачу
        logger.info(f"Import completed: processed={processed}, added={added}, invalid={invalid_count}, blacklisted={blacklisted_count}, errors={error_count}")
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
            logger.info(f"Temporary file removed: {file_path}")
        except Exception as e:
            logger.warning(f"Could not remove temporary file {file_path}: {e}")
        
        return True
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Fatal error in import task {task_id}: {e}", exc_info=True)
        
        # Обновляем задачу с ошибкой
        try:
            task = ImportTask.objects.get(id=task_id)
            task.status = ImportTask.FAILED
            task.error_message = f"{str(e)}: {type(e).__name__}"
            task.completed_at = timezone.now()
            task.save()
            logger.info(f"Task {task_id} marked as FAILED")
        except Exception as save_error:
            logger.error(f"Could not save failed task status: {save_error}", exc_info=True)
        
        # Удаляем временный файл
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Temporary file removed after error: {file_path}")
        except Exception as remove_error:
            logger.warning(f"Could not remove temporary file {file_path}: {remove_error}")
        
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