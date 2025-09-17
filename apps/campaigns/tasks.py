import uuid
import time
import smtplib
import threading
import os
from typing import List, Dict, Any
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import socket

from celery import shared_task, current_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

from .models import Campaign, EmailTracking, CampaignRecipient
from apps.mailer.models import Contact
from apps.mail_templates.models import EmailTemplate
from apps.emails.models import SenderEmail

# Добавляем импорт для DKIM подписи
try:
    import dkim
    DKIM_AVAILABLE = True
except ImportError:
    DKIM_AVAILABLE = False
    print("Warning: dkim library not available. DKIM signing will be disabled.")


class SMTPConnectionPool:
    """Пул SMTP соединений для эффективной отправки писем"""
    
    def __init__(self, max_connections=10):
        self.max_connections = max_connections
        self.connections = []
        self.lock = threading.Lock()
    
    def get_connection(self):
        """Получить SMTP соединение из пула"""
        with self.lock:
            if self.connections:
                return self.connections.pop()
            
            # Создать новое соединение, привязываем исходящий IP к 146.185.196.52
            connection = smtplib.SMTP(
                settings.EMAIL_HOST,
                settings.EMAIL_PORT,
                timeout=settings.EMAIL_CONNECTION_TIMEOUT,
                source_address=("146.185.196.52", 0)  # <-- Привязка исходящего IP (по запросу пользователя)
            )
            
            # Устанавливаем правильный HELO для улучшения доставляемости
            try:
                # Используем реальный домен вместо localhost
                helo_domain = settings.EMAIL_HOST if settings.EMAIL_HOST != 'localhost' else 'vashsender.ru'
                connection.helo(helo_domain)
                print(f"SMTP HELO set to: {helo_domain}")
                
                # Дополнительные настройки для лучшей доставляемости
                connection.ehlo(helo_domain)  # Также отправляем EHLO
                print(f"SMTP EHLO set to: {helo_domain}")
                
            except Exception as e:
                print(f"Failed to set HELO to {helo_domain}: {e}")
                try:
                    connection.helo('localhost')
                    connection.ehlo('localhost')
                    print(f"SMTP HELO/EHLO set to: localhost")
                except:
                    pass
            
            if settings.EMAIL_USE_TLS:
                connection.starttls()
                # Повторяем HELO и EHLO после STARTTLS для лучшей доставляемости
                try:
                    helo_domain = settings.EMAIL_HOST if settings.EMAIL_HOST != 'localhost' else 'vashsender.ru'
                    connection.helo(helo_domain)
                    connection.ehlo(helo_domain)
                    print(f"SMTP HELO/EHLO after STARTTLS set to: {helo_domain}")
                except Exception as e:
                    print(f"Failed to set HELO after STARTTLS: {e}")
                    try:
                        connection.helo('localhost')
                        connection.ehlo('localhost')
                        print(f"SMTP HELO/EHLO after STARTTLS set to: localhost")
                    except:
                        pass
            
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                connection.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            
            return connection
    
    def return_connection(self, connection):
        """Вернуть соединение в пул"""
        with self.lock:
            if len(self.connections) < self.max_connections:
                try:
                    # Проверить, что соединение еще живо
                    connection.noop()
                    self.connections.append(connection)
                except:
                    # Соединение мертво, закрыть его
                    try:
                        connection.quit()
                    except:
                        pass
    
    def close_all(self):
        """Закрыть все соединения"""
        with self.lock:
            for connection in self.connections:
                try:
                    connection.quit()
                except:
                    pass
            self.connections.clear()


# Глобальный пул соединений
smtp_pool = SMTPConnectionPool()


def sign_email_with_dkim(msg, domain_name):
    """
    Подписывает письмо DKIM подписью
    """
    if not DKIM_AVAILABLE:
        print("DKIM library not available, skipping DKIM signing")
        return msg
    
    try:
        # Получаем домен из базы данных
        from apps.emails.models import Domain
        try:
            domain = Domain.objects.get(domain_name=domain_name)
        except Domain.DoesNotExist:
            print(f"Domain {domain_name} not found in database, skipping DKIM signing")
            return msg
        
        # Проверяем наличие приватного ключа
        if not domain.private_key_path or not os.path.exists(domain.private_key_path):
            print(f"Private key not found for domain {domain_name}, skipping DKIM signing")
            return msg
        
        # Читаем приватный ключ
        with open(domain.private_key_path, 'rb') as f:
            private_key = f.read()
        
        # Подписываем письмо
        headers = ['From', 'To', 'Subject', 'Date', 'Message-ID']
        sig = dkim.sign(
            message=msg.as_bytes(),
            selector=domain.dkim_selector,
            domain=domain_name,
            privkey=private_key,
            include_headers=headers
        )
        
        # Добавляем подпись в заголовки
        msg['DKIM-Signature'] = sig[len('DKIM-Signature: '):]
        print(f"DKIM signature added for domain {domain_name}")
        
    except Exception as e:
        print(f"Error signing email with DKIM for domain {domain_name}: {e}")
    
    return msg


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='campaigns')
def test_celery():
    """Простая тестовая задача для проверки работы Celery"""
    print("Test Celery task is running!")
    return "Test task completed successfully"

@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='campaigns', 
            time_limit=14400, soft_time_limit=13800)  # 4 часа максимум, 3ч50м мягкий лимит
def send_campaign(self, campaign_id: str, skip_moderation: bool = False) -> Dict[str, Any]:
    """
    Основная задача для отправки кампании
    Разбивает кампанию на батчи и отправляет их асинхронно
    """
    start_time = time.time()
    print(f"Starting send_campaign task for campaign {campaign_id}")
    print(f"Task ID: {self.request.id}")
    print(f"Worker: {self.request.hostname}")
    print(f"Queue: {self.request.delivery_info.get('routing_key', 'unknown')}")
    
    try:
        # Проверяем таймаут
        if time.time() - start_time > 13800:  # 3ч50м
            raise TimeoutError("Task timeout approaching")
        
        # Принудительно обновляем состояние задачи
        self.update_state(
            state='STARTED',
            meta={
                'campaign_id': campaign_id,
                'status': 'Initializing campaign',
                'timestamp': time.time()
            }
        )
        
        # Получаем кампанию с обработкой ошибок
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            print(f"Found campaign: {campaign.name}, status: {campaign.status}")
        except Campaign.DoesNotExist:
            print(f"Campaign {campaign_id} not found in database")
            raise self.retry(countdown=60, max_retries=2)
        except Exception as e:
            print(f"Error getting campaign {campaign_id}: {e}")
            raise self.retry(countdown=120, max_retries=3)
        
        # Проверяем, что кампания не уже отправляется (только если не пропускаем модерацию)
        if not skip_moderation and campaign.status == Campaign.STATUS_SENDING:
            print(f"Кампания {campaign_id} уже отправляется")
            return {'error': 'Campaign already sending'}
        
        # Проверяем, нужна ли модерация
        user = campaign.user
        if not user.is_trusted_user and not skip_moderation:
            print(f"Пользователь {user.email} не является доверенным, отправляем на модерацию")
            
            # Создаем запись модерации
            from apps.moderation.models import CampaignModeration
            moderation, created = CampaignModeration.objects.get_or_create(
                campaign=campaign,
                defaults={'status': 'pending'}
            )
            
            # Обновляем статус кампании на pending
            campaign.status = Campaign.STATUS_PENDING
            campaign.save(update_fields=['status'])

            # Уведомляем поддержку о новой кампании на модерации
            try:
                support_email = 'support@vashsender.ru'
                subject = f"[Moderation] Новая кампания на модерации: {campaign.name or campaign.id}"
                body = (
                    f"Пользователь: {user.email}\n"
                    f"Кампания: {campaign.name or ''}\n"
                    f"Тема: {campaign.subject or ''}\n"
                    f"ID кампании: {campaign.id}\n"
                    f"Статус: {campaign.get_status_display()}\n"
                )
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@vashsender.ru'),
                    to=[support_email]
                )
                msg.send(fail_silently=True)
            except Exception:
                pass
            
            return {
                'campaign_id': campaign_id,
                'status': 'pending_moderation',
                'message': 'Кампания отправлена на модерацию'
            }
        
        # Получаем все контакты с обработкой ошибок
        try:
            contacts = set()
            from apps.mailer.models import Contact as MailerContact
            for contact_list in campaign.contact_lists.all():
                list_contacts = contact_list.contacts.filter(status=MailerContact.VALID)
                print(f"Found {list_contacts.count()} contacts in list {contact_list.name}")
                contacts.update(list_contacts)
            
            total_contacts = len(contacts)
            contacts_list = list(contacts)
            print(f"Total unique contacts: {total_contacts}")
            
            if total_contacts == 0:
                print(f"Нет контактов для кампании {campaign.name}")
                campaign.status = Campaign.STATUS_FAILED
                campaign.celery_task_id = None
                campaign.save(update_fields=['status', 'celery_task_id'])
                return {'error': 'No contacts found'}
                
        except Exception as e:
            print(f"Error getting contacts for campaign {campaign_id}: {e}")
            campaign.status = Campaign.STATUS_FAILED
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'celery_task_id'])
            raise self.retry(countdown=60, max_retries=2)
        
        # Проверяем лимиты тарифа перед отправкой
        try:
            from apps.billing.utils import can_user_send_emails, get_user_plan_info
            plan_info = get_user_plan_info(user)
            
            if plan_info['has_plan'] and plan_info['plan_type'] == 'Letters':
                # Для тарифов с письмами проверяем остаток
                if not can_user_send_emails(user, total_contacts):
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'celery_task_id'])
                    return {
                        'error': f'Недостаточно писем в тарифе. Доступно: {plan_info["emails_remaining"]}, требуется: {total_contacts}'
                    }
            elif plan_info['has_plan'] and plan_info['plan_type'] == 'Subscribers':
                # Для тарифов с подписчиками проверяем только срок действия
                if plan_info['is_expired']:
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'celery_task_id'])
                    return {
                        'error': 'Тариф истёк. Пожалуйста, продлите тариф для отправки кампаний.'
                    }
        except Exception as e:
            print(f"Error checking plan limits: {e}")
            # Продолжаем отправку, если не удалось проверить лимиты
        
        # Обновляем статус кампании на отправляется
        campaign.status = Campaign.STATUS_SENDING
        campaign.celery_task_id = self.request.id
        campaign.save(update_fields=['status', 'celery_task_id'])
        
        # Обновляем состояние задачи
        self.update_state(
            state='PROGRESS',
            meta={
                'campaign_id': campaign_id,
                'status': 'Campaign status updated to sending',
                'timestamp': time.time()
            }
        )
        
        # Обновляем прогресс
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': total_contacts,
                'status': f'Подготовка к отправке {total_contacts} писем',
                'timestamp': time.time()
            }
        )
        
        # Разбиваем на батчи (можно отправлять все сразу)
        batch_size = len(contacts_list)
        batches = [contacts_list]
        
        print(f"Кампания {campaign.name}: {total_contacts} писем, {len(batches)} батчей")
        
        # Отправляем письма напрямую через send_email_batch
        batch_tasks = []
        for i, batch in enumerate(batches):
            print(f"Launching batch {i + 1}/{len(batches)} with {len(batch)} contacts")
            
            # Проверяем таймаут перед запуском каждого батча
            if time.time() - start_time > 3300:
                raise TimeoutError("Task timeout approaching before launching all batches")
            
            try:
                # Без искусственных задержек между батчами
                
                result = send_email_batch.apply_async(
                    args=[campaign_id, [c.id for c in batch], i + 1, len(batches)],
                    countdown=0,
                    expires=1800,  # 30 минут
                    retry=True,
                    retry_policy={
                        'max_retries': 3,
                        'interval_start': 0,
                        'interval_step': 0.2,
                        'interval_max': 0.2,
                    }
                )
                batch_tasks.append(result)
                print(f"Batch {i + 1} task ID: {result.id}")
                print(f"Batch {i + 1} status: {result.status}")
            
                # Обновляем прогресс
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': i + 1,
                        'total': len(batches),
                        'status': f'Запущен батч {i + 1}/{len(batches)}',
                        'timestamp': time.time()
                    }
                )
                
            except Exception as e:
                print(f"Error launching batch {i + 1}: {e}")
                # Продолжаем с другими батчами
                continue
        
        # Ждем завершения всех батчей с увеличенным таймаутом
        max_wait_time = 14400  # 4 часа максимум ожидания
        wait_start = time.time()
        
        while time.time() - wait_start < max_wait_time:
            completed_batches = sum(1 for task in batch_tasks if task.ready())
            if completed_batches == len(batch_tasks):
                print(f"All {len(batch_tasks)} batches completed")
                break
            
            print(f"Waiting for batches: {completed_batches}/{len(batch_tasks)} completed")
            
            # Обновляем прогресс ожидания
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': completed_batches,
                    'total': len(batch_tasks),
                    'status': f'Ожидание завершения батчей: {completed_batches}/{len(batch_tasks)}',
                    'timestamp': time.time()
                }
            )
            
            time.sleep(10)  # Проверяем каждые 10 секунд
        else:
            print(f"Timeout waiting for batches after {max_wait_time} seconds")
            # Продолжаем выполнение, даже если не все батчи завершились
        
        # Финальная проверка статуса кампании
        try:
            campaign.refresh_from_db()
            print(f"Final campaign status: {campaign.status}")
            
            # Проверяем, нужно ли обновить статус на "sent"
            total_sent = CampaignRecipient.objects.filter(
                campaign_id=campaign_id, 
                is_sent=True
            ).count()
            total_recipients = CampaignRecipient.objects.filter(
                campaign_id=campaign_id
            ).count()
            
            print(f"Final statistics: total_recipients={total_recipients}, total_sent={total_sent}")
            
            if total_recipients > 0:
                if total_sent == total_recipients and campaign.status == Campaign.STATUS_SENDING:
                    print(f"All emails sent, updating campaign status to SENT")
                    campaign.status = Campaign.STATUS_SENT
                    campaign.sent_at = timezone.now()
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'sent_at', 'celery_task_id'])
                elif total_sent > 0 and total_sent < total_recipients:
                    print(f"Some emails sent: {total_sent}/{total_recipients}, marking as SENT")
                    campaign.status = Campaign.STATUS_SENT
                    campaign.sent_at = timezone.now()
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'sent_at', 'celery_task_id'])
                elif total_sent == 0:
                    print(f"No emails sent, marking as FAILED")
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'celery_task_id'])
            
            # Очищаем кэш для этой кампании
            cache_key = f"campaign_{campaign_id}"
            cache.delete(cache_key)
            
        except Exception as e:
            print(f"Error in final status check: {e}")
        
        execution_time = time.time() - start_time
        print(f"Campaign {campaign_id} processing completed in {execution_time:.2f} seconds")
        
        return {
            'campaign_id': campaign_id,
            'total_contacts': total_contacts,
            'batches_launched': len(batches),
            'status': 'batches_launched',
            'execution_time': execution_time,
            'worker': self.request.hostname
        }
        
    except TimeoutError as e:
        print(f"Timeout error in send_campaign task: {e}")
        # Обновляем статус кампании на failed при таймауте
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            campaign.status = Campaign.STATUS_FAILED
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'celery_task_id'])
        except:
            pass
        raise self.retry(countdown=300, max_retries=1)  # Повторяем через 5 минут
        
    except Campaign.DoesNotExist:
        print(f"Campaign {campaign_id} not found")
        raise self.retry(countdown=60, max_retries=2)
        
    except Exception as exc:
        print(f"Error in send_campaign task: {exc}")
        import traceback
        traceback.print_exc()
        
        # Обновляем статус кампании на failed
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            campaign.status = Campaign.STATUS_FAILED
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'celery_task_id'])
        except:
            pass
        
        print(f"Критическая ошибка в кампании {campaign_id}: {exc}")
        raise self.retry(exc=exc, countdown=120, max_retries=3)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue='email',
            time_limit=5400, soft_time_limit=4800)  # 90 минут максимум, 80 минут мягкий лимит
def send_email_batch(self, campaign_id: str, contact_ids: List[int], 
                    batch_number: int, total_batches: int) -> Dict[str, Any]:
    """
    Отправка батча писем с rate limiting и retry механизмом
    """
    start_time = time.time()
    smtp_connection = None
    
    try:
        print(f"Starting send_email_batch for campaign {campaign_id}, batch {batch_number}/{total_batches}")
        
        # Проверяем таймаут
        if time.time() - start_time > 4800:  # 80 минут
            raise TimeoutError("Batch task timeout approaching")
        
        campaign = Campaign.objects.get(id=campaign_id)
        # Отправляем только валидным контактам
        from apps.mailer.models import Contact as MailerContact
        contacts = Contact.objects.filter(id__in=contact_ids, status=MailerContact.VALID)
        
        # Получаем SMTP соединение из пула
        smtp_connection = smtp_pool.get_connection()
        print("Got SMTP connection")
        
        sent_count = 0
        failed_count = 0
        # Без искусственного rate limiting — все письма планируются сразу
         
        # Рассчитываем шаг задержки на основе настраиваемой скорости
        delay_step_seconds = 0
        try:
            from .models import SendingSettings
            emails_per_minute = SendingSettings.get_current_rate()
            if emails_per_minute and emails_per_minute > 0:
                delay_step_seconds = 60.0 / float(emails_per_minute)
        except Exception:
            delay_step_seconds = 0

        for i, contact in enumerate(contacts):
            try:
                # Проверяем таймаут в цикле
                if time.time() - start_time > 4800:
                    raise TimeoutError("Batch task timeout approaching during email sending")
                
                # Планируем отправку письма с учётом настраиваемой скорости
                countdown = int(i * delay_step_seconds) if delay_step_seconds > 0 else 0
                send_single_email.apply_async(args=[campaign_id, contact.id], countdown=countdown)
                # Не ждем результат, просто планируем задачу; обработка результата в send_single_email
                sent_count += 1  # Предполагаем успех, так как не ждем результат
                # Обновляем прогресс
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'batch': batch_number,
                        'total_batches': total_batches,
                        'current': i + 1,
                        'total': len(contacts),
                        'sent': sent_count,
                        'failed': failed_count
                    }
                )
            except Exception as e:
                failed_count += 1
                print(f"Ошибка отправки письма {contact.email}: {str(e)}")
                continue
        
        # Возвращаем соединение в пул
        if smtp_connection:
            smtp_pool.return_connection(smtp_connection)
        
        # Обновляем статус кампании на основе результатов этого батча
        campaign = Campaign.objects.get(id=campaign_id)
        print(f"Current campaign status before update: {campaign.status}")
        
        # Проверяем статистику по всем получателям кампании
        total_sent = CampaignRecipient.objects.filter(
            campaign_id=campaign_id, 
            is_sent=True
        ).count()
        total_failed = CampaignRecipient.objects.filter(
            campaign_id=campaign_id, 
            is_sent=False
        ).count()
        total_recipients = CampaignRecipient.objects.filter(
            campaign_id=campaign_id
        ).count()
        
        print(f"Campaign statistics: total_recipients={total_recipients}, total_sent={total_sent}, total_failed={total_failed}")
        
        # Обновляем статус кампании только если все получатели обработаны
        if total_recipients > 0 and (total_sent + total_failed) >= total_recipients:
            if total_sent > 0:
                campaign.status = Campaign.STATUS_SENT
                print(f"Setting campaign status to SENT ({total_sent}/{total_recipients} sent)")
            else:
                campaign.status = Campaign.STATUS_FAILED
                print(f"Setting campaign status to FAILED (no emails sent)")
            
            campaign.sent_at = timezone.now()
            print(f"Saving campaign with status: {campaign.status}")
            
            # Принудительно обновляем статус в базе данных
            from django.db import transaction
            with transaction.atomic():
                Campaign.objects.filter(id=campaign_id).update(
                    status=campaign.status,
                    sent_at=campaign.sent_at
                )
            
            # Очищаем кэш для этой кампании
            cache_key = f"campaign_{campaign_id}"
            cache.delete(cache_key)
            
            # Проверяем, что статус действительно сохранился
            try:
                campaign.refresh_from_db()
                print(f"Campaign {campaign.name} status after save: {campaign.status}")
            except Campaign.DoesNotExist:
                print(f"Campaign {campaign_id} not found after refresh")
        else:
            print(f"Not all recipients processed yet: {total_sent + total_failed}/{total_recipients}")
            print(f"Keeping campaign status as SENDING")
        
        print(f"Batch {batch_number} completed: {sent_count} sent, {failed_count} failed")
        
        # Финальная проверка и обновление статуса кампании
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            print(f"Final campaign status after batch {batch_number}: {campaign.status}")
            
            # Очищаем кэш для этой кампании
            cache_key = f"campaign_{campaign_id}"
            cache.delete(cache_key)
            
        except Exception as e:
            print(f"Error in final campaign status check: {e}")
        
        execution_time = time.time() - start_time
        print(f"Batch {batch_number} processing completed in {execution_time:.2f} seconds")
        
        return {
            'batch_number': batch_number,
            'sent': sent_count,
            'failed': failed_count,
            'total': len(contacts),
            'execution_time': execution_time
        }
        
    except TimeoutError as e:
        print(f"Timeout error in send_email_batch task: {e}")
        # Возвращаем соединение в пул в случае ошибки
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except:
                pass
        raise self.retry(countdown=60, max_retries=2)
        
    except Exception as exc:
        print(f"Error in send_email_batch task: {exc}")
        # Возвращаем соединение в пул в случае ошибки
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except:
                pass
        
        raise self.retry(exc=exc, countdown=60, max_retries=3)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue='email',
            time_limit=3600, soft_time_limit=3000)  # до 60 минут на письмо
def send_single_email(self, campaign_id: str, contact_id: int) -> Dict[str, Any]:
    """
    Отправка одного письма с полным retry механизмом
    """
    start_time = time.time()
    smtp_connection = None
    
    try:
        print(f"Starting send_single_email for campaign {campaign_id}, contact {contact_id}")
        
        # Проверяем таймаут
        if time.time() - start_time > 3000:  # 50 минут
            raise TimeoutError("Single email task timeout approaching")
        
        campaign = Campaign.objects.get(id=campaign_id)
        contact = Contact.objects.get(id=contact_id)
        # Пропускаем невалидные адреса
        try:
            from apps.mailer.models import Contact as MailerContact
            if contact.status != MailerContact.VALID:
                
                return {
                    'success': False,
                    'skipped': True,
                    'reason': 'invalid_contact',
                    'email': contact.email
                }
        except Exception:
            pass
        print(f"Sending to: {contact.email}")
        
        # Создаем tracking_id для трекинга
        tracking_id = f"{campaign_id}_{contact_id}_{int(time.time())}"
        
        # Подготавливаем контент письма
        html_content = campaign.template.html_content
        if campaign.content:
            html_content = html_content.replace('{{content}}', campaign.content)
        
        # Добавляем трекинг-пиксель для отслеживания открытий
        tracking_pixel = f'<img src="https://vashsender.ru/campaigns/{campaign_id}/track-open/?tracking_id={tracking_id}" width="1" height="1" style="display:none;" alt="" />'
        html_content += tracking_pixel
        
        # Обрабатываем ссылки для отслеживания кликов
        import re
        def replace_links(match):
            original_url = match.group(1)
            # Заменяем ссылки на трекинг-ссылки с полным доменом
            return f'href="https://vashsender.ru/campaigns/{campaign_id}/track-click/?tracking_id={tracking_id}&url={original_url}"'
        
        # Заменяем все href в ссылках
        html_content = re.sub(r'href="([^"]*)"', replace_links, html_content)

        # Формируем ссылку для отписки
        unsubscribe_url = f"https://vashsender.ru/campaigns/{campaign_id}/unsubscribe/?tracking_id={tracking_id}"
        
        # Подготавливаем отправителя - используем имя из кампании
        sender_name = campaign.sender_name
        if not sender_name or sender_name.strip() == '':
            # Если имя не задано в кампании, используем имя из email
            sender_name = campaign.sender_email.sender_name
            if not sender_name or sender_name.strip() == '':
                # Если и там нет, используем домен
                if '@' in campaign.sender_email.email:
                    domain = campaign.sender_email.email.split('@')[1]
                    sender_name = domain.split('.')[0].title()
                else:
                    sender_name = "Sender"
        
        # Очищаем имя от лишних символов и проблемных символов
        sender_name = sender_name.strip()
        
        # Убираем проблемные символы для email заголовков
        import re
        sender_name = re.sub(r'[^\w\s\-\.]', '', sender_name)  # Оставляем только буквы, цифры, пробелы, дефисы и точки
        sender_name = re.sub(r'\s+', ' ', sender_name)  # Убираем множественные пробелы
        
        if not sender_name:
            sender_name = "Sender"
        
        # Делаем максимально простой текст как у обычного письма
        import re
        
        # Простое извлечение текста без HTML
        plain_text = re.sub(r'<[^>]+>', '', html_content)
        
        # Добавляем переносы строк для лучшего форматирования
        # Заменяем <br>, <br/>, <br /> на переносы строк
        plain_text = re.sub(r'<br\s*/?>', '\n', plain_text, flags=re.IGNORECASE)
        
        # Заменяем <p> и </p> на двойные переносы строк
        plain_text = re.sub(r'</?p[^>]*>', '\n\n', plain_text, flags=re.IGNORECASE)
        
        # Убираем множественные пробелы и переносы строк
        plain_text = re.sub(r'\s+', ' ', plain_text)
        plain_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', plain_text)
        
        # Убираем лишние пробелы в начале и конце
        plain_text = plain_text.strip()
        
        # Если текст слишком короткий, добавляем простую подпись
        if len(plain_text) < 100:
            plain_text += f"\n\nС уважением,\n{sender_name}"
        
        # Добавляем блок отписки в текстовую версию
        plain_text += f"\n\nЕсли вы больше не хотите получать письма, вы можете отписаться по ссылке: {unsubscribe_url}"

        # Ограничиваем длину текста (без удаления блока отписки)
        if len(plain_text) > 2000:
            plain_text = plain_text[:2000] + "..."
        
        # Подготавливаем email отправителя
        from_email = campaign.sender_email.email
        
        # Убираем все возможные варианты двойного @ для любых доменов
        if from_email.count('@') > 1:
            # Если больше одного @, берем только первую часть до первого @
            parts = from_email.split('@')
            username = parts[0]
            domain = parts[1]  # Берем первый домен после @
            from_email = f"{username}@{domain}"
        
        # Дополнительная проверка на корректность email
        if not '@' in from_email:
            # Если email некорректный, используем домен из настроек
            from_email = settings.DEFAULT_FROM_EMAIL
        
        # Логируем для отладки
        print(f"Sender name: '{sender_name}'")
        print(f"From email: '{from_email}'")
        
        # Получаем SMTP соединение
        smtp_connection = smtp_pool.get_connection()
        
        # Создаем максимально простое сообщение как обычное письмо
        msg = MIMEMultipart('alternative')
        # Кодируем тему письма правильно
        if campaign.subject and any(ord(c) > 127 for c in campaign.subject):
            msg['Subject'] = Header(campaign.subject, 'utf-8', header_name='Subject')
        else:
            msg['Subject'] = campaign.subject
        
        # Устанавливаем корректный заголовок From без транслитерации имени отправителя
        from email.utils import formataddr
        encoded_display_name = str(Header(sender_name or '', 'utf-8'))
        msg['From'] = formataddr((encoded_display_name, from_email))
        msg['To'] = contact.email
        
        # Настраиваем Reply-To для лучшей доставляемости
        reply_to = campaign.sender_email.reply_to or from_email
        # Убираем двойные @ в Reply-To
        if reply_to.count('@') > 1:
            parts = reply_to.split('@')
            username = parts[0]
            domain = parts[1]
            reply_to = f"{username}@{domain}"
        
        msg['Reply-To'] = reply_to
        
        # Добавляем только необходимые заголовки для Mail.ru и Yandex
        import uuid
        # import time  # Удалено для предотвращения UnboundLocalError
        
        # Создаем уникальный Message-ID с временной меткой для лучшей доставляемости
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4()).replace('-', '')[:16]
        domain = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
        msg['Message-ID'] = f"<{timestamp}.{unique_id}@{domain}>"
        
        # Правильное форматирование даты для лучшей совместимости
        msg['Date'] = timezone.now().strftime('%a, %d %b %Y %H:%M:%S %z')
        msg['MIME-Version'] = '1.0'
        
        # Заголовки для улучшения доставляемости
        msg['X-Mailer'] = 'VashSender Mailer 1.0'  # Реальный X-Mailer сервиса
        msg['X-Priority'] = '3'
        msg['X-MSMail-Priority'] = 'Normal'
        msg['Importance'] = 'normal'
        
        # Mail.ru требует правильный Content-Type
        msg['Content-Type'] = 'multipart/alternative; boundary="boundary"'
        
        # Добавляем заголовки для предотвращения спама и улучшения доставляемости
        msg['List-Unsubscribe'] = f'<mailto:unsubscribe@{from_email.split("@")[1] if "@" in from_email else "vashsender.ru"}>'
        msg['Precedence'] = 'bulk'
        
        # Дополнительные заголовки для улучшения доставляемости
        msg['X-Auto-Response-Suppress'] = 'OOF, AutoReply'
        msg['Auto-Submitted'] = 'auto-generated'
        msg['X-Report-Abuse'] = f'Please report abuse here: abuse@{from_email.split("@")[1] if "@" in from_email else "vashsender.ru"}'
        
        # Заголовки для лучшей совместимости с почтовыми сервисами
        msg['X-Originating-IP'] = '146.185.196.52'  # Указываем реальный IP сервера
        msg['X-Sender'] = from_email
        msg['X-Envelope-From'] = from_email
        
        # Добавляем текстовую часть
        text_part = MIMEText(plain_text, 'plain', 'utf-8')
        msg.attach(text_part)
        
        # Добавляем HTML часть (осторожно для доставляемости)
        # Используем простой HTML без сложных стилей для лучшей доставляемости
        # Очищаем HTML от потенциально проблемных элементов
        import re
        
        # Убираем потенциально проблемные теги и атрибуты
        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
        html_content = re.sub(r'<iframe[^>]*>.*?</iframe>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
        html_content = re.sub(r'<object[^>]*>.*?</object>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
        
        # Убираем потенциально проблемные атрибуты
        html_content = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'\s+javascript:', '', html_content, flags=re.IGNORECASE)
        
        # Добавляем базовую структуру HTML если её нет
        if not html_content.strip().startswith('<html'):
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{campaign.subject or 'Письмо'}</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                {html_content}
            </body>
            </html>
            """
        
        # Добавляем блок отписки в HTML низ письма
        unsubscribe_block = f"""
        <div style=\"margin-top:24px; padding-top:12px; border-top:1px solid #e5e7eb; font-size:12px; color:#6b7280;\">
            Это письмо отправлено сервисом VashSender. 
            Если вы больше не хотите получать подобные письма, 
            <a href=\"{unsubscribe_url}\" style=\"color:#2563eb;\">отпишитесь по ссылке</a>.
        </div>
        """
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', f'{unsubscribe_block}</body>')
        else:
            html_content += unsubscribe_block

        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        # ВКЛЮЧАЕМ DKIM подпись для улучшения доставляемости в Mail.ru и Yandex
        domain_name = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
        msg = sign_email_with_dkim(msg, domain_name)
        
        # Отправляем письмо
        smtp_connection.send_message(msg)
        print(f"Email sent successfully to {contact.email}")
        
        # Создаем запись получателя и tracking с транзакцией
        from django.db import transaction
        with transaction.atomic():
            # Создаем CampaignRecipient
            recipient, created = CampaignRecipient.objects.get_or_create(
                campaign=campaign,
                contact=contact,
                defaults={'is_sent': True, 'sent_at': timezone.now()}
            )
            
            if not created:
                recipient.is_sent = True
                recipient.sent_at = timezone.now()
                recipient.save(update_fields=['is_sent', 'sent_at'])
            
            # Создаем EmailTracking для статистики
            tracking, tracking_created = EmailTracking.objects.get_or_create(
                campaign=campaign,
                contact=contact,
                defaults={
                    'tracking_id': tracking_id,
                    'delivered_at': timezone.now()  # Помечаем как доставленное
                }
            )
            
            if not tracking_created:
                # Если запись уже существует, обновляем время доставки
                tracking.delivered_at = timezone.now()
                tracking.save(update_fields=['delivered_at'])
        
        print(f"Created CampaignRecipient and EmailTracking: campaign_id={campaign_id}, contact_id={contact_id}, is_sent=True")
        
        # Обновляем счётчик отправленных писем в тарифе
        try:
            from apps.billing.utils import add_emails_sent_to_plan
            add_emails_sent_to_plan(campaign.user, 1)
            print(f"Updated email count for user {campaign.user.email}")
        except Exception as e:
            print(f"Error updating email count: {e}")
        
        # Возвращаем соединение в пул
        smtp_pool.return_connection(smtp_connection)
        
        execution_time = time.time() - start_time
        print(f"Single email to {contact.email} completed in {execution_time:.2f} seconds")
        
        return {
            'success': True,
            'email': contact.email,
            'execution_time': execution_time
        }
        
    except TimeoutError as e:
        print(f"Timeout error in send_single_email task: {e}")
        # Возвращаем соединение в пул в случае ошибки
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except:
                pass
        raise self.retry(countdown=30, max_retries=2)
        
    except Exception as exc:
        print(f"Error sending email to {contact.email if 'contact' in locals() else 'unknown'}: {exc}")
        
        # Возвращаем соединение в пул в случае ошибки
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except:
                pass
        
        # Создаем запись об ошибке
        try:
            if 'campaign' in locals() and 'contact' in locals():
                with transaction.atomic():
                    # Создаем CampaignRecipient
                    recipient, created = CampaignRecipient.objects.get_or_create(
                        campaign=campaign,
                        contact=contact,
                        defaults={'is_sent': False}
                    )
                    
                    if not created:
                        recipient.is_sent = False
                        recipient.save(update_fields=['is_sent'])
                    
                    # Создаем EmailTracking для статистики (помечаем как отказ)
                    tracking, tracking_created = EmailTracking.objects.get_or_create(
                        campaign=campaign,
                        contact=contact,
                        defaults={
                            'tracking_id': tracking_id if 'tracking_id' in locals() else f"{campaign_id}_{contact_id}_{int(time.time())}",
                            'bounced_at': timezone.now(),
                            'bounce_reason': str(exc)
                        }
                    )
                    
                    if not tracking_created:
                        # Если запись уже существует, обновляем время отказа
                        tracking.bounced_at = timezone.now()
                        tracking.bounce_reason = str(exc)
                        tracking.save(update_fields=['bounced_at', 'bounce_reason'])
                
                print(f"Created CampaignRecipient and EmailTracking: campaign_id={campaign_id}, contact_id={contact_id}, is_sent=False")
        except Exception as e:
            print(f"Error creating CampaignRecipient record: {e}")
        
        raise self.retry(exc=exc, countdown=60, max_retries=3)


@shared_task(bind=True, time_limit=300, soft_time_limit=240)
def auto_fix_stuck_campaigns(self):
    """
    Автоматическое исправление зависших кампаний.
    Запускается каждые 5 минут через Celery Beat.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.core.cache import cache
    from celery.result import AsyncResult
    
    print(f"[{timezone.now()}] Starting automatic fix of stuck campaigns...")
    
    # Таймаут для зависших кампаний (15 минут)
    timeout_minutes = 15
    cutoff_time = timezone.now() - timedelta(minutes=timeout_minutes)
    
    # Находим зависшие кампании
    stuck_campaigns = Campaign.objects.filter(
        status=Campaign.STATUS_SENDING,
        updated_at__lt=cutoff_time
    )
    
    fixed_count = 0
    for campaign in stuck_campaigns:
        try:
            print(f"Fixing stuck campaign: {campaign.name} (ID: {campaign.id})")
            
            # Проверяем task_id
            if campaign.celery_task_id:
                task_result = AsyncResult(campaign.celery_task_id)
                
                if task_result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                    print(f"  Task completed with state: {task_result.state}")
                elif task_result.state == 'PENDING':
                    print(f"  Task stuck in PENDING, revoking...")
                    task_result.revoke(terminate=True)
                else:
                    print(f"  Task in state: {task_result.state}")
            
            # Проверяем, сколько писем было отправлено
            sent_count = CampaignRecipient.objects.filter(
                campaign=campaign, 
                is_sent=True
            ).count()
            
            total_count = CampaignRecipient.objects.filter(campaign=campaign).count()
            
            print(f"  Statistics: {sent_count}/{total_count} emails sent")
            
            # Определяем финальный статус
            if sent_count > 0:
                if sent_count == total_count:
                    campaign.status = Campaign.STATUS_SENT
                    print(f"  Campaign marked as SENT ({sent_count}/{total_count} emails sent)")
                else:
                    campaign.status = Campaign.STATUS_SENT  # Помечаем как отправленную, если хоть что-то отправилось
                    print(f"  Campaign marked as SENT ({sent_count}/{total_count} emails sent)")
            else:
                # Если ничего не отправилось, проверяем, есть ли контакты
                total_contacts = 0
                for contact_list in campaign.contact_lists.all():
                    total_contacts += contact_list.contacts.count()
                
                if total_contacts == 0:
                    campaign.status = Campaign.STATUS_FAILED
                    print(f"  Campaign marked as FAILED (no contacts)")
                else:
                    campaign.status = Campaign.STATUS_FAILED
                    print(f"  Campaign marked as FAILED (no emails sent despite {total_contacts} contacts)")
            
            # Очищаем task_id
            campaign.celery_task_id = None
            campaign.sent_at = timezone.now()
            campaign.save(update_fields=['status', 'celery_task_id', 'sent_at'])
            
            # Очищаем кэш
            cache.delete(f'campaign_progress_{campaign.id}')
            cache.delete(f'campaign_{campaign.id}')
            
            fixed_count += 1
            
        except Exception as e:
            print(f"Error fixing campaign {campaign.id}: {e}")
            continue
    
    print(f"[{timezone.now()}] Auto-fix completed: {fixed_count} campaigns fixed")
    return {
        'fixed_campaigns': fixed_count,
        'timestamp': timezone.now().isoformat()
    }


@shared_task(bind=True, time_limit=300, soft_time_limit=240)
def cleanup_stuck_campaigns(self):
    """
    Автоматическая очистка зависших кампаний.
    Запускается каждые 10 минут через Celery Beat.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.core.cache import cache
    
    print(f"[{timezone.now()}] Starting automatic cleanup of stuck campaigns...")
    
    # Таймаут для зависших кампаний (30 минут)
    timeout_minutes = 30
    cutoff_time = timezone.now() - timedelta(minutes=timeout_minutes)
    
    # Находим зависшие кампании
    stuck_campaigns = Campaign.objects.filter(
        status=Campaign.STATUS_SENDING,
        updated_at__lt=cutoff_time
    )
    
    cleaned_count = 0
    for campaign in stuck_campaigns:
        try:
            print(f"Cleaning up stuck campaign: {campaign.name} (ID: {campaign.id})")
            
            # Проверяем, сколько писем было отправлено
            sent_count = CampaignRecipient.objects.filter(
                campaign=campaign, 
                is_sent=True
            ).count()
            
            total_count = CampaignRecipient.objects.filter(campaign=campaign).count()
            
            # Определяем финальный статус
            if sent_count > 0:
                if sent_count == total_count:
                    campaign.status = Campaign.STATUS_SENT
                    print(f"  Campaign marked as SENT ({sent_count}/{total_count} emails sent)")
                else:
                    campaign.status = Campaign.STATUS_SENT
                    print(f"  Campaign marked as SENT ({sent_count}/{total_count} emails sent)")
            else:
                campaign.status = Campaign.STATUS_DRAFT
                print(f"  Campaign reset to DRAFT (no emails sent)")
            
            # Очищаем task_id
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'celery_task_id'])
            
            # Очищаем кэш
            cache.delete(f'campaign_progress_{campaign.id}')
            
            cleaned_count += 1
            
        except Exception as e:
            print(f"Error cleaning up campaign {campaign.id}: {e}")
            continue
    
    print(f"[{timezone.now()}] Cleanup completed: {cleaned_count} campaigns cleaned")
    return {
        'cleaned_campaigns': cleaned_count,
        'timestamp': timezone.now().isoformat()
    }


@shared_task(bind=True, time_limit=300, soft_time_limit=240)
def monitor_campaign_progress(self):
    """
    Мониторинг прогресса кампаний и автоматическое исправление проблем.
    Запускается каждые 5 минут через Celery Beat.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.core.cache import cache
    from celery.result import AsyncResult
    
    print(f"[{timezone.now()}] Starting campaign progress monitoring...")
    
    # Проверяем кампании в статусе "sending"
    sending_campaigns = Campaign.objects.filter(status=Campaign.STATUS_SENDING)
    
    monitored_count = 0
    for campaign in sending_campaigns:
        try:
            monitored_count += 1
            
            # Проверяем task_id
            if not campaign.celery_task_id:
                print(f"Campaign {campaign.id} has no task_id, marking as failed")
                campaign.status = Campaign.STATUS_FAILED
                campaign.save(update_fields=['status'])
                continue
            
            # Проверяем статус задачи Celery
            task_result = AsyncResult(campaign.celery_task_id)
            
            if task_result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                # Задача завершена, но статус кампании не обновлен
                print(f"Campaign {campaign.id} task completed with state: {task_result.state}")
                
                # Проверяем количество отправленных писем
                sent_count = CampaignRecipient.objects.filter(
                    campaign=campaign, 
                    is_sent=True
                ).count()
        
                total_count = CampaignRecipient.objects.filter(campaign=campaign).count()
                
                if sent_count > 0:
                    if sent_count == total_count:
                        campaign.status = Campaign.STATUS_SENT
                        print(f"  Campaign marked as SENT ({sent_count}/{total_count})")
                    else:
                        campaign.status = Campaign.STATUS_FAILED
                        print(f"  Campaign marked as FAILED ({sent_count}/{total_count})")
                else:
                    campaign.status = Campaign.STATUS_FAILED
                    print(f"  Campaign marked as FAILED (no emails sent)")
                
                campaign.save(update_fields=['status'])
            
            elif task_result.state == 'PENDING':
                # Задача в очереди слишком долго
                task_age = timezone.now() - campaign.updated_at
                if task_age > timedelta(minutes=15):
                    print(f"Campaign {campaign.id} task stuck in PENDING for {task_age}")
                    # Можно добавить логику для перезапуска задачи
            
        except Exception as e:
            print(f"Error monitoring campaign {campaign.id}: {e}")
            continue
    
    print(f"[{timezone.now()}] Monitoring completed: {monitored_count} campaigns checked")
    return {
        'monitored_campaigns': monitored_count,
        'timestamp': timezone.now().isoformat()
    }


@shared_task(bind=True, time_limit=300, soft_time_limit=240)
def cleanup_smtp_connections(self):
    """
    Очистка SMTP соединений и проверка их состояния.
    Запускается каждые 10 минут через Celery Beat.
    """
    from django.core.cache import cache
    
    print(f"[{timezone.now()}] Starting SMTP connections cleanup...")
    
    try:
        # Очищаем старые SMTP соединения из кэша
        smtp_keys = cache.keys('smtp_connection_*')
        cleaned_connections = 0
        
        for key in smtp_keys:
            connection_data = cache.get(key)
            if connection_data:
                # Проверяем возраст соединения (старше 30 минут)
                from django.utils import timezone
                from datetime import timedelta
                
                if 'created_at' in connection_data:
                    created_at = connection_data['created_at']
                    if isinstance(created_at, str):
                        from datetime import datetime
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    
                    if timezone.now() - created_at > timedelta(minutes=30):
                        cache.delete(key)
                        cleaned_connections += 1
        
        print(f"[{timezone.now()}] SMTP cleanup completed: {cleaned_connections} connections cleaned")
        
        return {
            'cleaned_connections': cleaned_connections,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error during SMTP cleanup: {e}")
        return {
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        } 
