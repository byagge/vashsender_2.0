from django.contrib.auth.forms import PasswordResetForm
from django.template.loader import render_to_string


class CustomPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        subject = render_to_string(subject_template_name, context)
        subject = ''.join(subject.splitlines())

        text_message = render_to_string(email_template_name, context)
        html_message = render_to_string(html_email_template_name, context) if html_email_template_name else None

        # Надёжная отправка: общий SMTP пул с DKIM и фолбэк
        try:
            from apps.emails.tasks import send_verification_email_sync
            send_verification_email_sync(
                to_email=to_email,
                subject=subject,
                plain_text=text_message,
                html=html_message or '',
            )
        except Exception:
            from django.core.mail import EmailMultiAlternatives, get_connection
            connection = get_connection(fail_silently=False)
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=from_email,
                to=[to_email],
                connection=connection,
            )
            if html_message:
                email.attach_alternative(html_message, "text/html")
            email.send()


