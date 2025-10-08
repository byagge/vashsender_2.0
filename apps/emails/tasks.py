import logging
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

# Reuse the same SMTP pool and DKIM signing as campaigns
from apps.campaigns.tasks import smtp_pool, sign_email_with_dkim

logger = logging.getLogger('apps.emails')


def _build_verification_message(to_email: str, subject: str, plain_text: str, html: str, from_email: str):
    msg = MIMEMultipart('alternative')
    if subject and any(ord(c) > 127 for c in subject):
        msg['Subject'] = Header(subject, 'utf-8', header_name='Subject')
    else:
        msg['Subject'] = subject

    display_name = 'VashSender'
    msg['From'] = formataddr((str(Header(display_name, 'utf-8')), from_email))
    msg['To'] = to_email
    msg['Reply-To'] = from_email

    # Standard headers
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=from_email.split('@')[1] if '@' in from_email else 'vashsender.ru')
    msg['X-Mailer'] = 'VashSender Notifications 1.0'

    # Parts
    text_part = MIMEText(plain_text or '', 'plain', 'utf-8')
    msg.attach(text_part)
    if html:
        html_part = MIMEText(html, 'html', 'utf-8')
        msg.attach(html_part)

    # DKIM: if OpenDKIM mode is enabled, signing will happen in MTA; otherwise call in-app
    domain_name = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
    msg = sign_email_with_dkim(msg, domain_name)
    return msg


def _build_plain_text_message(to_email: str, subject: str, plain_text: str, from_email: str):
    """Build a simple plain-text MIME message using the same headers and DKIM policy."""
    msg = MIMEMultipart('alternative')
    if subject and any(ord(c) > 127 for c in subject):
        msg['Subject'] = Header(subject, 'utf-8', header_name='Subject')
    else:
        msg['Subject'] = subject

    display_name = 'VashSender'
    msg['From'] = formataddr((str(Header(display_name, 'utf-8')), from_email))
    msg['To'] = to_email
    msg['Reply-To'] = from_email

    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=from_email.split('@')[1] if '@' in from_email else 'vashsender.ru')
    msg['X-Mailer'] = 'VashSender Notifications 1.0'

    text_part = MIMEText(plain_text or '', 'plain', 'utf-8')
    msg.attach(text_part)

    domain_name = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
    msg = sign_email_with_dkim(msg, domain_name)
    return msg


def send_verification_email_sync(to_email: str, subject: str, plain_text: str, html: str) -> None:
    """
    Synchronous sender using the shared SMTP pool and DKIM, for fallback paths.
    Raises on failure so callers can handle/report errors.
    """
    smtp_connection = None
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')
    msg = _build_verification_message(to_email, subject, plain_text, html, from_email)
    logger.debug(f"Sending verification email to={to_email} subject={subject}")
    # First try the high-performance SMTP pool (local MTA path)
    try:
        smtp_connection = smtp_pool.get_connection()
        try:
            smtp_connection.send_message(msg)
            logger.info(f"Verification email sent to={to_email} via smtp_pool")
            return
        finally:
            if smtp_connection:
                try:
                    smtp_pool.return_connection(smtp_connection)
                except Exception:
                    pass
    except Exception as pool_exc:
        logger.warning(f"smtp_pool failed, falling back to Django EmailBackend: {pool_exc}")

    # Fallback to Django EmailBackend using EmailMultiAlternatives
    try:
        connection = get_connection(fail_silently=False)
        email = EmailMultiAlternatives(subject=subject, body=plain_text or '', from_email=from_email, to=[to_email], connection=connection)
        if html:
            email.attach_alternative(html, "text/html")
        email.send()
        logger.info(f"Verification email sent to={to_email} via Django EmailBackend")
    except Exception as backend_exc:
        logger.error(f"Both smtp_pool and Django EmailBackend failed to send to={to_email}: {backend_exc}")
        raise


def send_plain_notification_sync(to_email: str, subject: str, plain_text: str) -> None:
    """Synchronous plain-text sender via the shared SMTP pool (DKIM-aware)."""
    smtp_connection = None
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')
    msg = _build_plain_text_message(to_email, subject, plain_text, from_email)
    logger.debug(f"Sending plain notification to={to_email} subject={subject}")
    smtp_connection = smtp_pool.get_connection()
    try:
        smtp_connection.send_message(msg)
        logger.info(f"Plain notification sent to={to_email}")
    finally:
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue='email', time_limit=300, soft_time_limit=240)
def send_verification_email(self, to_email: str, subject: str, plain_text: str, html: str):
    """
    Send account verification emails via the shared SMTP connection pool
    with DKIM, matching campaign SMTP behavior.
    """
    smtp_connection = None
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')
    msg = _build_verification_message(to_email, subject, plain_text, html, from_email)
    logger.debug(f"[celery] Sending verification email to={to_email} subject={subject}")
    # Try SMTP pool first
    try:
        smtp_connection = smtp_pool.get_connection()
        smtp_connection.send_message(msg)
        logger.info(f"[celery] Verification email sent to={to_email} via smtp_pool")
        if smtp_connection:
            smtp_pool.return_connection(smtp_connection)
        return {'success': True, 'transport': 'smtp_pool'}
    except Exception as pool_exc:
        logger.warning(f"[celery] smtp_pool failed for {to_email}: {pool_exc}")
        try:
            if smtp_connection:
                try:
                    smtp_pool.return_connection(smtp_connection)
                except Exception:
                    pass
        finally:
            smtp_connection = None

    # Fallback to Django EmailBackend inside Celery worker
    try:
        connection = get_connection(fail_silently=False)
        email = EmailMultiAlternatives(subject=subject, body=plain_text or '', from_email=from_email, to=[to_email], connection=connection)
        if html:
            email.attach_alternative(html, "text/html")
        email.send()
        logger.info(f"[celery] Verification email sent to={to_email} via Django EmailBackend")
        return {'success': True, 'transport': 'django_backend'}
    except Exception as backend_exc:
        logger.error(f"[celery] Both transports failed for {to_email}: {backend_exc}")
        raise self.retry(exc=backend_exc, countdown=60, max_retries=3)


