import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

from celery import shared_task
from django.conf import settings

# Reuse the same SMTP pool and headers logic as campaigns
from apps.campaigns.tasks import smtp_pool


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue='email', time_limit=300, soft_time_limit=240)
def send_verification_email(self, to_email: str, subject: str, plain_text: str, html: str):
    """
    Send account verification emails via the shared SMTP connection pool
    to ensure identical SMTP settings/behavior as campaigns.
    """
    smtp_connection = None
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@vashsender.ru')

        # Build MIME message
        msg = MIMEMultipart('alternative')
        if subject and any(ord(c) > 127 for c in subject):
            msg['Subject'] = Header(subject, 'utf-8', header_name='Subject')
        else:
            msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        text_part = MIMEText(plain_text or '', 'plain', 'utf-8')
        msg.attach(text_part)
        if html:
            html_part = MIMEText(html, 'html', 'utf-8')
            msg.attach(html_part)

        # Message-ID and Date
        timestamp = int(time.time())
        domain = from_email.split('@')[1] if '@' in from_email else 'vashsender.ru'
        msg['Message-ID'] = f"<{timestamp}.{int(time.time()*1000)}@{domain}>"

        # Send via shared SMTP pool
        smtp_connection = smtp_pool.get_connection()
        smtp_connection.send_message(msg)
        if smtp_connection:
            smtp_pool.return_connection(smtp_connection)
        return {'success': True}

    except Exception as exc:
        # Return connection to pool on errors too
        if smtp_connection:
            try:
                smtp_pool.return_connection(smtp_connection)
            except Exception:
                pass
        raise self.retry(exc=exc, countdown=60, max_retries=3)


