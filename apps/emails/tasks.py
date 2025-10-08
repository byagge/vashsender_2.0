import logging
import idna
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid

from celery import shared_task
from django.conf import settings

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
    smtp_connection = smtp_pool.get_connection()
    try:
        # Envelope normalization
        def _normalize_envelope(addr: str):
            if '@' not in addr:
                return None
            local, domain = addr.split('@', 1)
            try:
                local.encode('ascii')
                domain_ascii = idna.encode(domain).decode('ascii')
                return f"{local}@{domain_ascii}"
            except Exception:
                return None

        from_addr = _normalize_envelope(from_email) or from_email
        to_addr = _normalize_envelope(to_email) or to_email

        supports_smtputf8 = False
        try:
            supports_smtputf8 = bool(getattr(smtp_connection, 'has_extn', lambda *_: False)('smtputf8'))
        except Exception:
            supports_smtputf8 = False

        if supports_smtputf8:
            smtp_connection.send_message(msg, from_addr=from_addr, to_addrs=[to_addr], mail_options=['SMTPUTF8'])
        else:
            # Require ASCII-only in envelope
            if from_addr is None:
                from_addr = _normalize_envelope(getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')) or 'noreply@vashsender.ru'
            if to_addr is None:
                raise Exception('Recipient address requires SMTPUTF8 but server does not support it')
            smtp_connection.send_message(msg, from_addr=from_addr, to_addrs=[to_addr])
        logger.info(f"Verification email sent to={to_email}")
    finally:
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass


def send_plain_notification_sync(to_email: str, subject: str, plain_text: str) -> None:
    """Synchronous plain-text sender via the shared SMTP pool (DKIM-aware)."""
    smtp_connection = None
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')
    msg = _build_plain_text_message(to_email, subject, plain_text, from_email)
    logger.debug(f"Sending plain notification to={to_email} subject={subject}")
    smtp_connection = smtp_pool.get_connection()
    try:
        def _normalize_envelope(addr: str):
            if '@' not in addr:
                return None
            local, domain = addr.split('@', 1)
            try:
                local.encode('ascii')
                domain_ascii = idna.encode(domain).decode('ascii')
                return f"{local}@{domain_ascii}"
            except Exception:
                return None

        from_addr = _normalize_envelope(from_email) or from_email
        to_addr = _normalize_envelope(to_email) or to_email

        supports_smtputf8 = False
        try:
            supports_smtputf8 = bool(getattr(smtp_connection, 'has_extn', lambda *_: False)('smtputf8'))
        except Exception:
            supports_smtputf8 = False

        if supports_smtputf8:
            smtp_connection.send_message(msg, from_addr=from_addr, to_addrs=[to_addr], mail_options=['SMTPUTF8'])
        else:
            if from_addr is None:
                from_addr = _normalize_envelope(getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')) or 'noreply@vashsender.ru'
            if to_addr is None:
                raise Exception('Recipient address requires SMTPUTF8 but server does not support it')
            smtp_connection.send_message(msg, from_addr=from_addr, to_addrs=[to_addr])
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
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')
        msg = _build_verification_message(to_email, subject, plain_text, html, from_email)
        logger.debug(f"[celery] Sending verification email to={to_email} subject={subject}")
        smtp_connection = smtp_pool.get_connection()
        # Envelope normalization and SMTPUTF8 handling
        def _normalize_envelope(addr: str):
            if '@' not in addr:
                return None
            local, domain = addr.split('@', 1)
            try:
                local.encode('ascii')
                domain_ascii = idna.encode(domain).decode('ascii')
                return f"{local}@{domain_ascii}"
            except Exception:
                return None

        from_addr = _normalize_envelope(from_email) or from_email
        to_addr = _normalize_envelope(to_email) or to_email

        supports_smtputf8 = False
        try:
            supports_smtputf8 = bool(getattr(smtp_connection, 'has_extn', lambda *_: False)('smtputf8'))
        except Exception:
            supports_smtputf8 = False

        if supports_smtputf8:
            smtp_connection.send_message(msg, from_addr=from_addr, to_addrs=[to_addr], mail_options=['SMTPUTF8'])
        else:
            if from_addr is None:
                from_addr = _normalize_envelope(getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')) or 'noreply@vashsender.ru'
            if to_addr is None:
                raise Exception('Recipient address requires SMTPUTF8 but server does not support it')
            smtp_connection.send_message(msg, from_addr=from_addr, to_addrs=[to_addr])
        logger.info(f"[celery] Verification email sent to={to_email}")
        if smtp_connection:
            smtp_pool.return_connection(smtp_connection)
        return {'success': True}
    except Exception as exc:
        logger.error(f"[celery] Failed to send verification email to={to_email}: {exc}")
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass
        raise self.retry(exc=exc, countdown=60, max_retries=3)


