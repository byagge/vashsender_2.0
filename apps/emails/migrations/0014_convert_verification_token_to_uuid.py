# Generated migration to convert verification_token from TEXT to UUID

from django.db import migrations, models
import uuid


def convert_text_to_uuid(apps, schema_editor):
    """
    Преобразует существующие текстовые токены в UUID формат
    """
    SenderEmail = apps.get_model('emails', 'SenderEmail')
    
    for sender in SenderEmail.objects.all():
        token_str = str(sender.verification_token)
        
        # Если токен в формате без дефисов (32 символа)
        if len(token_str) == 32 and '-' not in token_str:
            # Форматируем в стандартный UUID
            formatted_token = f"{token_str[:8]}-{token_str[8:12]}-{token_str[12:16]}-{token_str[16:20]}-{token_str[20:]}"
            sender.verification_token = formatted_token
            sender.save(update_fields=['verification_token'])


def reverse_conversion(apps, schema_editor):
    """
    Обратная конвертация (на случай отката миграции)
    """
    SenderEmail = apps.get_model('emails', 'SenderEmail')
    
    for sender in SenderEmail.objects.all():
        token_str = str(sender.verification_token).replace('-', '')
        sender.verification_token = token_str
        sender.save(update_fields=['verification_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('emails', '0013_alter_domain_dkim_selector'),
    ]

    operations = [
        # Шаг 1: Преобразуем существующие данные
        migrations.RunPython(convert_text_to_uuid, reverse_conversion),
        
        # Шаг 2: Изменяем тип поля с использованием USING для приведения типов
        migrations.RunSQL(
            sql='ALTER TABLE emails_senderemail ALTER COLUMN verification_token TYPE UUID USING verification_token::uuid;',
            reverse_sql='ALTER TABLE emails_senderemail ALTER COLUMN verification_token TYPE TEXT;'
        ),
    ]
