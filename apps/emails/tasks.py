import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid

from celery import shared_task
from django.conf import settings

# Reuse the same SMTP pool and DKIM signing as campaigns
from apps.campaigns.tasks import smtp_pool, sign_email_with_dkim


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


def send_verification_email_sync(to_email: str, subject: str, plain_text: str, html: str) -> None:
    """
    Synchronous sender using the shared SMTP pool and DKIM, for fallback paths.
    Raises on failure so callers can handle/report errors.
    """
    smtp_connection = None
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')
    msg = _build_verification_message(to_email, subject, plain_text, html, from_email)
    smtp_connection = smtp_pool.get_connection()
    try:
        smtp_connection.send_message(msg)
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
        smtp_connection = smtp_pool.get_connection()
        smtp_connection.send_message(msg)
        if smtp_connection:
            smtp_pool.return_connection(smtp_connection)
        return {'success': True}
    except Exception as exc:
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass
        raise self.retry(exc=exc, countdown=60, max_retries=3)


