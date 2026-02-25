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

# Centralized queue names with safe fallbacks.
CAMPAIGN_QUEUE = getattr(settings, 'CAMPAIGN_QUEUE', 'default')
EMAIL_QUEUE = getattr(settings, 'EMAIL_QUEUE', 'default')

# Добавляем импорт для DKIM подписи
try:
    import dkim
    DKIM_AVAILABLE = True
except ImportError:
    DKIM_AVAILABLE = False
    if getattr(settings, 'EMAIL_DEBUG', False):
        print("Warning: dkim library not available. DKIM signing will be disabled.")


PROGRESS_CACHE_TIMEOUT = 60 * 60  # 1 hour


def update_campaign_progress_cache(campaign_id, *, total=None, sent=None, delta_sent=0, lock: bool = False, force: bool = False):
    """
    Обновляет кэш прогресса кампании для быстрого отображения на фронте.
    """
    cache_key = f'campaign_progress_{campaign_id}'
    progress = cache.get(cache_key) or {'total': 0, 'sent': 0, 'locked': False}

    # Если кэш зафиксирован (кампания уже завершена), не меняем значения,
    # кроме случая явного принудительного обновления.
    if progress.get('locked') and not force:
        return progress
    
    if total is not None:
        progress['total'] = max(int(total), 0)
    if sent is not None:
        progress['sent'] = max(int(sent), 0)
    if delta_sent:
        progress['sent'] = max(progress.get('sent', 0) + int(delta_sent), 0)

    if lock:
        progress['locked'] = True
    
    cache.set(cache_key, progress, PROGRESS_CACHE_TIMEOUT)
    return progress


def finalize_campaign_if_complete(campaign_id: str) -> None:
    """
    Финализирует кампанию, если прогресс в кэше достиг total.
    Вызывается из send_single_email, чтобы не держать долгоживущие оркестраторы.
    """
    try:
        cache_key = f'campaign_progress_{campaign_id}'
        progress = cache.get(cache_key) or {}
        total = int(progress.get('total') or 0)
        sent = int(progress.get('sent') or 0)

        if total <= 0 or sent < total:
            return

        with transaction.atomic():
            campaign = Campaign.objects.select_for_update().get(id=campaign_id)
            if campaign.status != Campaign.STATUS_SENT:
                campaign.status = Campaign.STATUS_SENT
                campaign.sent_at = campaign.sent_at or timezone.now()
                campaign.celery_task_id = None
                campaign.failure_reason = None
                campaign.save(update_fields=['status', 'sent_at', 'celery_task_id', 'failure_reason'])

        update_campaign_progress_cache(
            campaign_id,
            total=total,
            sent=sent,
            lock=True,
            force=True
        )
        cache.delete(f"campaign_{campaign_id}")
    except Exception as exc:
        # не валим отправку из-за проблем финализации
        print(f"finalize_campaign_if_complete({campaign_id}) failed: {exc}")


def mark_contact_as_invalid(contact, reason: str = ''):
    """
    Переводит контакт в статус INVALID, чтобы больше не пытаться отправлять на него письма.
    """
    try:
        from apps.mailer.models import Contact as MailerContact
        if contact.status != MailerContact.INVALID:
            contact.status = MailerContact.INVALID
            contact.save(update_fields=['status'])
            if getattr(settings, 'EMAIL_DEBUG', False):
                print(f"Contact {contact.email} marked as INVALID. Reason: {reason}")
    except Exception as exc:
        print(f"Could not mark contact {getattr(contact, 'email', 'unknown')} as invalid: {exc}")


def decrement_campaign_total_if_needed(campaign_id: str):
    """
    Уменьшаем общее количество писем в кэше прогресса, если какой-то адрес пришлось исключить.
    """
    cache_key = f'campaign_progress_{campaign_id}'
    progress = cache.get(cache_key)
    if progress and progress.get('total') is not None:
        new_total = max(int(progress.get('total', 0)) - 1, 0)
        update_campaign_progress_cache(campaign_id, total=new_total)


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

            # Подготовка кандидатов для подключения (failover)
            primary_host = getattr(settings, 'EMAIL_HOST', 'localhost')
            fallback_hosts = list(getattr(settings, 'EMAIL_FALLBACK_HOSTS', []))
            host_candidates = []
            if primary_host:
                host_candidates.append(primary_host)
            host_candidates.extend(h for h in fallback_hosts if h and h not in host_candidates)
            # Добавляем 127.0.0.1 как запасной, если не равен текущему
            if '127.0.0.1' not in host_candidates:
                host_candidates.append('127.0.0.1')

            port = getattr(settings, 'EMAIL_PORT', 25)
            timeout = getattr(settings, 'EMAIL_CONNECTION_TIMEOUT', 30)
            use_tls = getattr(settings, 'EMAIL_USE_TLS', False)
            use_ssl = getattr(settings, 'EMAIL_USE_SSL', False)
            source_ip = getattr(settings, 'EMAIL_SOURCE_IP', '146.185.196.52')

            last_error = None
            connection = None
            for host in host_candidates:
                # Пытаемся с привязкой исходящего IP
                for bind_source in [(source_ip, 0), None]:
                    try:
                        connect_start = time.time()
                        if getattr(settings, 'EMAIL_DEBUG', False):
                            print(f"[SMTP] connect start host={host} ssl={use_ssl} tls={use_tls} bind={bind_source}")

                        if use_ssl:
                            connection = smtplib.SMTP_SSL(host=host, port=port, timeout=timeout)
                        else:
                            connection = smtplib.SMTP(host=host, port=port, timeout=timeout, source_address=bind_source) if bind_source else smtplib.SMTP(host=host, port=port, timeout=timeout)

                        if getattr(settings, 'EMAIL_DEBUG', False):
                            connect_duration = time.time() - connect_start
                            print(f"[SMTP] connect end host={host} duration={connect_duration:.3f}s")

                        # Устанавливаем правильный HELO/EHLO
                        helo_domain = primary_host if primary_host != 'localhost' else 'vashsender.ru'
                        try:
                            connection.helo(helo_domain)
                            connection.ehlo(helo_domain)
                        except Exception:
                            try:
                                connection.helo('localhost')
                                connection.ehlo('localhost')
                            except Exception:
                                pass

                        if use_tls and not use_ssl:
                            try:
                                # Используем STARTTLS только если сервер его поддерживает
                                try:
                                    supports_starttls = connection.has_extn('starttls')
                                except Exception:
                                    supports_starttls = False
                                if supports_starttls:
                                    tls_start = time.time()
                                    if getattr(settings, 'EMAIL_DEBUG', False):
                                        print(f"[SMTP] TLS start host={host}")
                                    connection.starttls()
                                    if getattr(settings, 'EMAIL_DEBUG', False):
                                        tls_duration = time.time() - tls_start
                                        print(f"[SMTP] TLS end host={host} duration={tls_duration:.3f}s")

                                    # Повторяем HELO/EHLO после STARTTLS
                                    try:
                                        connection.helo(helo_domain)
                                        connection.ehlo(helo_domain)
                                    except Exception:
                                        try:
                                            connection.helo('localhost')
                                            connection.ehlo('localhost')
                                        except Exception:
                                            pass
                                else:
                                    if getattr(settings, 'EMAIL_DEBUG', False):
                                        print("STARTTLS not supported by server — continuing without TLS")
                            except Exception as e:
                                last_error = e
                                try:
                                    if getattr(settings, 'EMAIL_DEBUG', False):
                                        print(f"[SMTP] TLS error on host={host}: {e}")
                                    connection.quit()
                                except Exception:
                                    pass
                                connection = None
                                continue

                        if getattr(settings, 'EMAIL_HOST_USER', '') and getattr(settings, 'EMAIL_HOST_PASSWORD', ''):
                            connection.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)

                        # Успех
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        # Закрываем, если частично инициализировался
                        try:
                            if connection:
                                connection.quit()
                        except Exception:
                            pass
                        connection = None
                        continue
                if connection:
                    break

            if not connection:
                # Не удалось установить соединение ни с одним хостом
                raise last_error or ConnectionError('Failed to connect to any SMTP host')
            
            # Устанавливаем правильный HELO для улучшения доставляемости
            try:
                # Используем реальный домен вместо localhost
                helo_domain = getattr(settings, 'EMAIL_HOST', 'localhost')
                helo_domain = helo_domain if helo_domain != 'localhost' else 'vashsender.ru'
                connection.helo(helo_domain)
                if getattr(settings, 'EMAIL_DEBUG', False):
                    print(f"SMTP HELO set to: {helo_domain}")
                
                # Дополнительные настройки для лучшей доставляемости
                connection.ehlo(helo_domain)  # Также отправляем EHLO
                if getattr(settings, 'EMAIL_DEBUG', False):
                    print(f"SMTP EHLO set to: {helo_domain}")
                
            except Exception as e:
                if getattr(settings, 'EMAIL_DEBUG', False):
                    print(f"Failed to set HELO to {helo_domain}: {e}")
                try:
                    connection.helo('localhost')
                    connection.ehlo('localhost')
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        print(f"SMTP HELO/EHLO set to: localhost")
                except:
                    pass
            
            if settings.EMAIL_USE_TLS:
                try:
                    supports_starttls = connection.has_extn('starttls')
                except Exception:
                    supports_starttls = False
                if supports_starttls:
                    tls_start = time.time()
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        print(f"[SMTP] TLS start (post-connect) host={host}")
                    connection.starttls()
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        tls_duration = time.time() - tls_start
                        print(f"[SMTP] TLS end (post-connect) host={host} duration={tls_duration:.3f}s")

                    # Повторяем HELO и EHLO после STARTTLS для лучшей доставляемости
                    try:
                        helo_domain = settings.EMAIL_HOST if settings.EMAIL_HOST != 'localhost' else 'vashsender.ru'
                        connection.helo(helo_domain)
                        connection.ehlo(helo_domain)
                        if getattr(settings, 'EMAIL_DEBUG', False):
                            print(f"SMTP HELO/EHLO after STARTTLS set to: {helo_domain}")
                    except Exception as e:
                        if getattr(settings, 'EMAIL_DEBUG', False):
                            print(f"Failed to set HELO after STARTTLS: {e}")
                        try:
                            connection.helo('localhost')
                            connection.ehlo('localhost')
                            if getattr(settings, 'EMAIL_DEBUG', False):
                                print(f"SMTP HELO/EHLO after STARTTLS set to: localhost")
                        except:
                            pass
                else:
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        print("STARTTLS not supported by server — continuing without TLS")
            
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                auth_start = time.time()
                if getattr(settings, 'EMAIL_DEBUG', False):
                    print(f"[SMTP] AUTH start user={settings.EMAIL_HOST_USER}")
                connection.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                if getattr(settings, 'EMAIL_DEBUG', False):
                    auth_duration = time.time() - auth_start
                    print(f"[SMTP] AUTH end user={settings.EMAIL_HOST_USER} duration={auth_duration:.3f}s")
            
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
                        if getattr(settings, 'EMAIL_DEBUG', False):
                            quit_start = time.time()
                            print("[SMTP] quit start (dead connection)")
                        connection.quit()
                        if getattr(settings, 'EMAIL_DEBUG', False):
                            quit_duration = time.time() - quit_start
                            print(f"[SMTP] quit end (dead connection) duration={quit_duration:.3f}s")
                    except:
                        pass
    
    def close_all(self):
        """Закрыть все соединения"""
        with self.lock:
            for connection in self.connections:
                try:
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        quit_start = time.time()
                        print("[SMTP] quit start (close_all)")
                    connection.quit()
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        quit_duration = time.time() - quit_start
                        print(f"[SMTP] quit end (close_all) duration={quit_duration:.3f}s")
                except:
                    pass
            self.connections.clear()


# Глобальный пул соединений
smtp_pool = SMTPConnectionPool()


def sign_email_with_dkim(msg, domain_name):
    """
    Подписывает письмо DKIM подписью
    """
    # If configured to use OpenDKIM milter via local MTA, skip in-app signing
    try:
        from django.conf import settings as dj_settings
        if getattr(dj_settings, 'EMAIL_USE_OPENDKIM', False):
            if getattr(dj_settings, 'EMAIL_DEBUG', False):
                print("OpenDKIM mode enabled, skipping in-app DKIM signing")
            return msg
    except Exception:
        pass

    if not DKIM_AVAILABLE:
        if getattr(settings, 'EMAIL_DEBUG', False):
            print("DKIM library not available, skipping DKIM signing")
        return msg
    
    try:
        # Получаем домен из базы данных
        from apps.emails.models import Domain
        try:
            domain = Domain.objects.get(domain_name=domain_name)
        except Domain.DoesNotExist:
            if getattr(settings, 'EMAIL_DEBUG', False):
                print(f"Domain {domain_name} not found in database, skipping DKIM signing")
            return msg
        
        # Получаем приватный ключ: сначала по сохраненному пути, иначе пробуем стандартный путь из DKIM_KEYS_DIR
        private_key = None
        if domain.private_key_path and os.path.exists(domain.private_key_path):
            with open(domain.private_key_path, 'rb') as f:
                private_key = f.read()
        else:
            from django.conf import settings as dj_settings
            keys_dir = getattr(dj_settings, 'DKIM_KEYS_DIR', '/etc/opendkim/keys')
            selector = domain.dkim_selector
            candidate_path = os.path.join(keys_dir, domain_name, f"{selector}.private")
            if os.path.exists(candidate_path):
                try:
                    with open(candidate_path, 'rb') as f:
                        private_key = f.read()
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        print(f"Loaded DKIM private key from fallback path: {candidate_path}")
                except Exception as e:
                    if getattr(settings, 'EMAIL_DEBUG', False):
                        print(f"Failed to read fallback DKIM key {candidate_path}: {e}")
        if not private_key:
            if getattr(settings, 'EMAIL_DEBUG', False):
                print(f"Private key not found for domain {domain_name}, skipping DKIM signing")
            return msg
        
        # Подписываем письмо
        headers = [h.lower() for h in ['From', 'To', 'Subject', 'Date', 'Message-ID']]
        sig = dkim.sign(
            message=msg.as_bytes(),
            selector=domain.dkim_selector.encode('utf-8'),
            domain=domain_name.encode('utf-8'),
            privkey=private_key,
            include_headers=headers,
            canonicalize=(b'relaxed', b'relaxed')
        )
        
        # Добавляем подпись в заголовки (bytes -> str)
        signature_value = sig[len('DKIM-Signature: '):]
        if isinstance(signature_value, bytes):
            signature_value = signature_value.decode('ascii')
        msg['DKIM-Signature'] = signature_value
        if getattr(settings, 'EMAIL_DEBUG', False):
            print(f"DKIM signature added for domain {domain_name}")
        
    except Exception as e:
        if getattr(settings, 'EMAIL_DEBUG', False):
            print(f"Error signing email with DKIM for domain {domain_name}: {e}")
    
    return msg


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='campaigns')
def test_celery():
    """Простая тестовая задача для проверки работы Celery"""
    if getattr(settings, 'EMAIL_DEBUG', False):
        print("Test Celery task is running!")
    return "Test task completed successfully"

@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue=CAMPAIGN_QUEUE)
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

        # Сбрасываем прогресс в кэше: иначе возможны "залипания" (locked) при повторных запусках
        try:
            cache.delete(f'campaign_progress_{campaign_id}')
            cache.delete(f'campaign_{campaign_id}')
        except Exception:
            pass

        except Campaign.DoesNotExist:
            print(f"Campaign {campaign_id} not found in database - likely deleted by user")
            # Не ретраим если кампания удалена - это нормальная ситуация
            return {
                'success': False,
                'error': 'Campaign was deleted',
                'campaign_id': str(campaign_id)
            }
        except Exception as e:
            print(f"Error getting campaign {campaign_id}: {e}")
            raise self.retry(countdown=120, max_retries=3)
        
        # Проверяем, что нет параллельных запусков той же кампании
        if campaign.status == Campaign.STATUS_SENDING and campaign.celery_task_id:
            if campaign.celery_task_id != self.request.id:
                print(f"Кампания {campaign_id} уже отправляется (task {campaign.celery_task_id})")
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
                support_email = getattr(settings, 'SUPPORT_NOTIFICATIONS_EMAIL', 'support@vashsender.ru')
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
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@regvshsndr.ru'),
                    to=[support_email]
                )
                msg.send(fail_silently=not getattr(settings, 'EMAIL_DEBUG', False))
            except Exception:
                pass
            
            return {
                'campaign_id': campaign_id,
                'status': 'pending_moderation',
                'message': 'Кампания отправлена на модерацию'
            }
        
        # Получаем все контакты с обработкой ошибок
        try:
            # Дедупликация контактов по ID (устойчиво к разным queryset/инстансам)
            contact_ids_set = set()
            from apps.mailer.models import Contact as MailerContact
            for contact_list in campaign.contact_lists.all():
                list_contacts = contact_list.contacts.filter(status=MailerContact.VALID).values_list('id', flat=True)
                count = list_contacts.count()
                print(f"Found {count} contacts in list {contact_list.name}")
                contact_ids_set.update(list(list_contacts))
            
            total_contacts = len(contact_ids_set)
            contacts_list = list(contact_ids_set)
            print(f"Total unique contacts: {total_contacts}")
            
            if total_contacts == 0:
                print(f"Нет контактов для кампании {campaign.name}")
                campaign.status = Campaign.STATUS_FAILED
                campaign.failure_reason = campaign.failure_reason or 'no contacts in selected lists'
                campaign.celery_task_id = None
                campaign.save(update_fields=['status', 'failure_reason', 'celery_task_id'])
                return {'error': 'No contacts found'}
        except Exception as e:
            print(f"Error getting contacts for campaign {campaign_id}: {e}")
            campaign.status = Campaign.STATUS_FAILED
            campaign.failure_reason = campaign.failure_reason or f'error retrieving contacts: {e}'
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'failure_reason', 'celery_task_id'])
            raise self.retry(countdown=60, max_retries=2)
        
        existing_sent = CampaignRecipient.objects.filter(
            campaign_id=campaign_id,
            is_sent=True
        ).count()
        update_campaign_progress_cache(
            campaign_id,
            total=total_contacts,
            sent=existing_sent
        )
        
        # Проверяем лимиты тарифа перед отправкой
        try:
            from apps.billing.utils import can_user_send_emails, get_user_plan_info
            plan_info = get_user_plan_info(user)
            
            if plan_info['has_plan'] and plan_info['plan_type'] == 'Letters':
                # Для тарифов с письмами проверяем остаток
                if not can_user_send_emails(user, total_contacts):
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.failure_reason = campaign.failure_reason or 'recipients exceed plan limits'
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'failure_reason', 'celery_task_id'])
                    return {
                        'error': 'Количество получателей больше, чем предусмотрено тарифом'
                    }
            elif plan_info['has_plan'] and plan_info['plan_type'] == 'Subscribers':
                # Для тарифов с подписчиками проверяем только срок действия
                if plan_info['is_expired']:
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.failure_reason = campaign.failure_reason or 'plan expired'
                    campaign.celery_task_id = None
                    campaign.save(update_fields=['status', 'failure_reason', 'celery_task_id'])
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
        
        # Для небольших рассылок отправляем синхронно в рамках этой задачи,
        # чтобы не зависеть от очереди 'email'.
        # Важно: даже для маленьких кампаний мы больше НЕ выполняем отправку синхронно,
        # а только ставим подзадачи в очередь, чтобы оркестратор не блокировал воркер.

        # Разбиваем на батчи для больших объемов
        # Для больших кампаний разбиваем на батчи по 1000 контактов для лучшей обработки
        if total_contacts > 1000:
            batch_size = 1000
            batches = [contacts_list[i:i + batch_size] for i in range(0, len(contacts_list), batch_size)]
            print(f"Кампания {campaign.name}: {total_contacts} писем разбито на {len(batches)} батчей по {batch_size} контактов")
        else:
            # Для небольших кампаний отправляем все сразу
            batch_size = len(contacts_list)
            batches = [contacts_list]
            print(f"Кампания {campaign.name}: {total_contacts} писем, {len(batches)} батчей")
        
        # Отправляем письма напрямую через send_email_batch
        batch_tasks = []
        for i, batch in enumerate(batches):
            print(f"Launching batch {i + 1}/{len(batches)} with {len(batch)} contacts")
            
            try:
                # Без искусственных задержек между батчами
                
                result = send_email_batch.apply_async(
                    args=[campaign_id, [int(c_id) for c_id in batch], i + 1, len(batches)],
                    queue=EMAIL_QUEUE,
                    countdown=0,
                    expires=getattr(settings, 'CAMPAIGN_BATCH_TASK_EXPIRES', 6 * 60 * 60),  # default 6 hours
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
            campaign.failure_reason = campaign.failure_reason or 'send_campaign timeout'
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'failure_reason', 'celery_task_id'])
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
        
        # Для всех ошибок, включая SoftTimeLimitExceeded, обновляем статус кампании на failed
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            campaign.status = Campaign.STATUS_FAILED
            campaign.failure_reason = campaign.failure_reason or f'send_campaign exception: {exc}'
            campaign.celery_task_id = None
            campaign.save(update_fields=['status', 'failure_reason', 'celery_task_id'])
        except:
            pass
        
        print(f"Критическая ошибка в кампании {campaign_id}: {exc}")
        raise self.retry(exc=exc, countdown=120, max_retries=3)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue=EMAIL_QUEUE)
def send_email_batch(self, campaign_id: str, contact_ids: List[int], 
                    batch_number: int, total_batches: int) -> Dict[str, Any]:
    """
    Планирует отправку батча писем.

    ВАЖНО:
    - Никаких долгих while/sleep циклов тут быть не должно (иначе ловите SoftTimeLimitExceeded и "зависания").
    - Прогресс/финализацию делает send_single_email через кэш (sent/total) и finalize_campaign_if_complete().
    """
    start_time = time.time()

    try:
        print(f"Starting send_email_batch for campaign {campaign_id}, batch {batch_number}/{total_batches}")

        try:
            Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            print(f"Campaign {campaign_id} not found - batch skipped")
            return {'success': False, 'skipped': True, 'reason': 'campaign_deleted', 'campaign_id': str(campaign_id)}

        # Отправляем только валидным контактам
        from apps.mailer.models import Contact as MailerContact
        contacts_qs = Contact.objects.filter(
            id__in=contact_ids,
            status=MailerContact.VALID
        ).only('id').order_by('id')

        # Не планируем повторно тем, кого уже обработали (is_sent=True у нас означает "попытка завершена")
        already_done = set(
            CampaignRecipient.objects.filter(
                campaign_id=campaign_id,
                contact_id__in=contact_ids,
                is_sent=True
            ).values_list('contact_id', flat=True)
        )

        # Убедимся, что total в кэше есть (и не уменьшаем его здесь)
        progress = cache.get(f'campaign_progress_{campaign_id}') or {}
        total_existing = int(progress.get('total') or 0)
        if total_existing <= 0:
            update_campaign_progress_cache(campaign_id, total=len(contact_ids), sent=int(progress.get('sent') or 0))

        scheduled = 0
        skipped = 0
        errors = 0
        total_candidates = contacts_qs.count()

        for contact in contacts_qs.iterator(chunk_size=500):
            if contact.id in already_done:
                skipped += 1
                continue

            try:
                send_single_email.apply_async(
                    args=[campaign_id, int(contact.id)],
                    queue=EMAIL_QUEUE,
                    countdown=0
                )
                scheduled += 1
            except Exception as e:
                errors += 1
                print(f"Ошибка планирования письма для контакта {contact.id}: {e}")

            # минимальный state update, чтобы не убивать Redis/backend
            if scheduled and (scheduled % 250 == 0):
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'campaign_id': campaign_id,
                        'batch': batch_number,
                        'total_batches': total_batches,
                        'scheduled': scheduled,
                        'skipped': skipped,
                        'errors': errors,
                        'total_candidates': total_candidates
                    }
                )

        execution_time = time.time() - start_time
        print(f"Batch {batch_number} scheduled in {execution_time:.2f}s; scheduled={scheduled}, skipped={skipped}, errors={errors}")

        return {
            'success': True,
            'campaign_id': campaign_id,
            'batch_number': batch_number,
            'total_batches': total_batches,
            'scheduled': scheduled,
            'skipped': skipped,
            'errors': errors,
            'execution_time': execution_time,
            'worker': self.request.hostname
        }

    except Exception as exc:
        print(f"Error in send_email_batch task: {exc}")
        raise self.retry(exc=exc, countdown=60, max_retries=3)

@shared_task(bind=True, max_retries=10, default_retry_delay=60, queue=EMAIL_QUEUE)
def send_single_email(self, campaign_id: str, contact_id: int) -> Dict[str, Any]:
    """
    Отправка одного письма с полным retry механизмом
    """
    start_time = time.time()
    smtp_connection = None
    
    try:
        print(f"Starting send_single_email for campaign {campaign_id}, contact {contact_id}")
        
        campaign = Campaign.objects.get(id=campaign_id)
        contact = Contact.objects.get(id=contact_id)
        
        def record_failure(reason: str = '', mark_invalid: bool = False):
            """
            Фиксируем неудачную отправку и при необходимости помечаем контакт как недействительный.
            ВАЖНО: попытка отправки считается выполненной (для прогресса кампании),
            даже если произошла ошибка доставки (bounce / hard fail).
            """
            try:
                with transaction.atomic():
                    recipient, created = CampaignRecipient.objects.get_or_create(
                        campaign=campaign,
                        contact=contact,
                        # Даже при ошибке помечаем как "отправлено" для прогресса кампании
                        defaults={'is_sent': True, 'sent_at': timezone.now()}
                    )
                    increment_progress = False
                    if not created:
                        # Если по этому контакту ещё не было успешной/неуспешной отправки,
                        # или он помечен как неотправленный — фиксируем факт попытки.
                        if not recipient.is_sent or recipient.sent_at is None:
                            recipient.is_sent = True
                            recipient.sent_at = timezone.now()
                            recipient.save(update_fields=['is_sent', 'sent_at'])
                            increment_progress = True
                    else:
                        increment_progress = True
                    
                    tracking, tracking_created = EmailTracking.objects.get_or_create(
                        campaign=campaign,
                        contact=contact,
                        defaults={
                            'tracking_id': f"{campaign_id}_{contact_id}_{int(time.time())}",
                            'bounced_at': timezone.now(),
                            'bounce_reason': reason
                        }
                    )
                    if not tracking_created:
                        tracking.bounced_at = timezone.now()
                        tracking.bounce_reason = reason
                        tracking.save(update_fields=['bounced_at', 'bounce_reason'])
                
                # Обновляем прогресс кампании: увеличиваем счётчик "sent",
                # чтобы такие контакты учитывались как обработанные.
                if increment_progress:
                    update_campaign_progress_cache(str(campaign.id), delta_sent=1)

                finalize_campaign_if_complete(str(campaign.id))
                
                if mark_invalid:
                    mark_contact_as_invalid(contact, reason)
            except Exception as exc:
                print(f"Error recording failed delivery for {getattr(contact, 'email', 'unknown')}: {exc}")
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
        # ВРЕМЕННО ОТКЛЮЧЕНО
        # plain_text += f"\n\nЕсли вы больше не хотите получать письма, вы можете отписаться по ссылке: {unsubscribe_url}"

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
        connect_stage_start = time.time()
        print(f"[SMTP] connect (pool.get_connection) start for {contact.email}")
        smtp_connection = smtp_pool.get_connection()
        connect_stage_duration = time.time() - connect_stage_start
        print(f"[SMTP] connect (pool.get_connection) end for {contact.email} duration={connect_stage_duration:.3f}s")
        
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
        msg['X-Mailer'] = 'Vash Sender Mailer 1.0'  # Реальный X-Mailer сервиса
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
        # ВРЕМЕННО ОТКЛЮЧЕНО
        # unsubscribe_block = f"""
        # <div style=\"margin-top:24px; padding-top:12px; border-top:1px solid #e5e7eb; font-size:12px; color:#6b7280;\">
        #     Если вы больше не хотите получать подобные письма, 
        #     <a href=\"{unsubscribe_url}\" style=\"color:#2563eb;\">отпишитесь по ссылке</a>.
        # </div>
        # """
        # if '</body>' in html_content:
        #     html_content = html_content.replace('</body>', f'{unsubscribe_block}</body>')
        # else:
        #     html_content += unsubscribe_block

        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        # ВКЛЮЧАЕМ DKIM подпись для улучшения доставляемости в Mail.ru и Yandex
        domain_name = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
        msg = sign_email_with_dkim(msg, domain_name)
        
        # Отправляем письмо (SMTP DATA)
        data_start = time.time()
        print(f"[SMTP] sendmail (DATA) start to {contact.email}")
        smtp_connection.send_message(msg)
        data_duration = time.time() - data_start
        print(f"[SMTP] sendmail (DATA) end to {contact.email} duration={data_duration:.3f}s")
        print(f"Email sent successfully to {contact.email}")
        
        # Создаем запись получателя и tracking с транзакцией (DB update)
        db_start = time.time()
        print(f"[DB] update start for campaign_id={campaign_id}, contact_id={contact_id}")
        increment_progress = False
        with transaction.atomic():
            # Создаем CampaignRecipient
            recipient, created = CampaignRecipient.objects.get_or_create(
                campaign=campaign,
                contact=contact,
                defaults={'is_sent': True, 'sent_at': timezone.now()}
            )
            
            if not created:
                if not recipient.is_sent:
                    recipient.is_sent = True
                    recipient.sent_at = timezone.now()
                    recipient.save(update_fields=['is_sent', 'sent_at'])
                    increment_progress = True
            else:
                increment_progress = True
            
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
        db_duration = time.time() - db_start
        print(f"[DB] update end for campaign_id={campaign_id}, contact_id={contact_id} duration={db_duration:.3f}s")
        
        if increment_progress:
            update_campaign_progress_cache(campaign_id, delta_sent=1)
        
        finalize_campaign_if_complete(campaign_id)

        print(f"Created CampaignRecipient and EmailTracking: campaign_id={campaign_id}, contact_id={contact_id}, is_sent=True")
        
        # Обновляем счётчик отправленных писем в тарифе
        try:
            from apps.billing.utils import add_emails_sent_to_plan
            add_emails_sent_to_plan(campaign.user, 1)
            print(f"Updated email count for user {campaign.user.email}")
        except Exception as e:
            print(f"Error updating email count: {e}")
        
        # Возвращаем соединение в пул (может вызвать NOOP/QUIT)
        quit_stage_start = time.time()
        print(f"[SMTP] quit/return start for {contact.email}")
        smtp_pool.return_connection(smtp_connection)
        quit_stage_duration = time.time() - quit_stage_start
        print(f"[SMTP] quit/return end for {contact.email} duration={quit_stage_duration:.3f}s")
        
        execution_time = time.time() - start_time
        print(f"Single email to {contact.email} completed in {execution_time:.2f} seconds")
        
        return {
            'success': True,
            'email': contact.email,
            'execution_time': execution_time
        }
        
    except smtplib.SMTPRecipientsRefused as exc:
        # Может быть как временная (4xx), так и постоянная (5xx) ошибка.
        code = None
        try:
            recips = getattr(exc, 'recipients', None) or {}
            info = next(iter(recips.values())) if recips else None
            if isinstance(info, (tuple, list)) and len(info) >= 1:
                code = int(info[0])
        except Exception:
            code = None

        reason = f"SMTP recipients refused ({code}): {exc}"
        print(reason)

        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass

        # 4xx (или неизвестно) — считаем временным и ретраим.
        if (code is None) or (400 <= code < 500):
            from celery.exceptions import MaxRetriesExceededError
            countdown = min(600, 30 * (2 ** self.request.retries))
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                record_failure(reason, mark_invalid=False)
                return {
                    'success': False,
                    'retry_exhausted': True,
                    'reason': str(exc),
                    'email': contact.email if 'contact' in locals() else None
                }

        # 5xx — постоянная ошибка, помечаем INVALID и не ретраим.
        record_failure(reason, mark_invalid=True)
        return {
            'success': False,
            'invalidated': True,
            'reason': str(exc),
            'email': contact.email if 'contact' in locals() else None
        }

    except (smtplib.SMTPDataError, smtplib.SMTPResponseException) as exc:
        # SMTPDataError/SMTPResponseException содержат smtp_code/smtp_error.
        code = None
        try:
            code = int(getattr(exc, 'smtp_code', None))
        except Exception:
            code = None

        reason = f"SMTP response error ({code}): {exc}"
        print(reason)

        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass

        # 4xx (например 421/450/451/452) — временно, нужен retry/backoff.
        if (code is None) or (400 <= code < 500):
            from celery.exceptions import MaxRetriesExceededError
            countdown = min(900, 30 * (2 ** self.request.retries))
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                record_failure(reason, mark_invalid=False)
                return {
                    'success': False,
                    'retry_exhausted': True,
                    'reason': str(exc),
                    'email': contact.email if 'contact' in locals() else None
                }

        # 5xx — постоянная ошибка, помечаем INVALID.
        if 500 <= (code or 0) < 600:
            record_failure(reason, mark_invalid=True)
            return {
                'success': False,
                'invalidated': True,
                'reason': str(exc),
                'email': contact.email if 'contact' in locals() else None
            }

        # Всё остальное — ретраим как временное.
        from celery.exceptions import MaxRetriesExceededError
        countdown = min(900, 30 * (2 ** self.request.retries))
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            record_failure(reason, mark_invalid=False)
            return {
                'success': False,
                'retry_exhausted': True,
                'reason': str(exc),
                'email': contact.email if 'contact' in locals() else None
            }

    except (Campaign.DoesNotExist, Contact.DoesNotExist) as exc:
        # Кампания или контакт удалены/не существуют — ретраи бессмысленны.
        print(f"send_single_email skipped: {exc}")
        return {
            'success': False,
            'skipped': True,
            'reason': 'object_not_found',
            'details': str(exc),
            'campaign_id': campaign_id,
            'contact_id': contact_id
        }

    except TimeoutError as e:
        print(f"Timeout error in send_single_email task: {e}")
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass

        from celery.exceptions import MaxRetriesExceededError
        countdown = min(900, 30 * (2 ** self.request.retries))
        try:
            raise self.retry(exc=e, countdown=countdown)
        except MaxRetriesExceededError:
            record_failure(f"Timeout: {e}", mark_invalid=False)
            return {
                'success': False,
                'retry_exhausted': True,
                'reason': str(e),
                'email': contact.email if 'contact' in locals() else None
            }

    except Exception as exc:
        print(f"Error sending email to {contact.email if 'contact' in locals() else 'unknown'}: {exc}")

        # Возвращаем соединение в пул в случае ошибки
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass

        # По умолчанию считаем ошибку временной: делаем retry/backoff.
        # Контакт НЕ помечаем INVALID на сетевых/SMTP transient ошибках.
        from celery.exceptions import MaxRetriesExceededError
        countdown = min(900, 30 * (2 ** self.request.retries))
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            # Ретраи исчерпаны — фиксируем финальный фейл, но не инвалидируем контакт.
            record_failure(str(exc), mark_invalid=False)
            return {
                'success': False,
                'retry_exhausted': True,
                'reason': str(exc),
                'email': contact.email if 'contact' in locals() else None
            }


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
    from apps.mailer.models import Contact as MailerContact
    
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
            if campaign.status == Campaign.STATUS_SENT:
                continue
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
                is_sent=True,
                contact__status=MailerContact.VALID
            ).count()
            
            total_count = CampaignRecipient.objects.filter(
                campaign=campaign,
                contact__status=MailerContact.VALID
            ).count()
            
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
    from apps.mailer.models import Contact as MailerContact
    
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
            if campaign.status == Campaign.STATUS_SENT:
                continue
            print(f"Cleaning up stuck campaign: {campaign.name} (ID: {campaign.id})")
            
            # Проверяем, сколько писем было отправлено
            sent_count = CampaignRecipient.objects.filter(
                campaign=campaign, 
                is_sent=True,
                contact__status=MailerContact.VALID
            ).count()
            
            total_count = CampaignRecipient.objects.filter(
                campaign=campaign,
                contact__status=MailerContact.VALID
            ).count()
            
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
    from apps.mailer.models import Contact as MailerContact
    
    print(f"[{timezone.now()}] Starting campaign progress monitoring...")
    
    # Проверяем кампании в статусе "sending"
    sending_campaigns = Campaign.objects.filter(status=Campaign.STATUS_SENDING)
    
    monitored_count = 0
    for campaign in sending_campaigns:
        try:
            monitored_count += 1
            if campaign.status == Campaign.STATUS_SENT:
                continue
            
            # Проверяем task_id. Не помечаем как failed, если есть отправленные письма
            if not campaign.celery_task_id:
                print(f"Campaign {campaign.id} has no task_id, evaluating delivery stats before marking status")
                sent_count = CampaignRecipient.objects.filter(
                    campaign=campaign,
                    is_sent=True,
                    contact__status=MailerContact.VALID
                ).count()
                total_count = CampaignRecipient.objects.filter(
                    campaign=campaign,
                    contact__status=MailerContact.VALID
                ).count()
                if sent_count > 0:
                    campaign.status = Campaign.STATUS_SENT
                    campaign.save(update_fields=['status'])
                else:
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.failure_reason = campaign.failure_reason or 'celery_task_id missing and no emails sent'
                    campaign.save(update_fields=['status', 'failure_reason'])
                continue
            
            # Проверяем статус задачи Celery
            task_result = AsyncResult(campaign.celery_task_id)
            
            if task_result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                # Задача завершена, но статус кампании не обновлен
                print(f"Campaign {campaign.id} task completed with state: {task_result.state}")
                
                # Проверяем количество отправленных писем
                sent_count = CampaignRecipient.objects.filter(
                    campaign=campaign, 
                    is_sent=True,
                    contact__status=MailerContact.VALID
                ).count()
        
                total_count = CampaignRecipient.objects.filter(
                    campaign=campaign,
                    contact__status=MailerContact.VALID
                ).count()
                
                if sent_count > 0:
                    # Если хоть что-то доставлено/отправлено — это SENT, не FAILED
                    # Дополнительно проверяем доставку >= 70% от отправленных
                    delivered_count = EmailTracking.objects.filter(campaign=campaign, delivered_at__isnull=False).count()
                    delivery_ratio = (delivered_count / sent_count) if sent_count else 0
                    campaign.status = Campaign.STATUS_SENT
                    print(f"  Campaign marked as SENT ({sent_count}/{total_count}), delivered {delivered_count}/{sent_count} ({delivery_ratio:.0%})")
                else:
                    campaign.status = Campaign.STATUS_FAILED
                    campaign.failure_reason = campaign.failure_reason or 'no emails sent'
                    print(f"  Campaign marked as FAILED (no emails sent)")
                
                campaign.save(update_fields=['status', 'failure_reason'])
            
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
