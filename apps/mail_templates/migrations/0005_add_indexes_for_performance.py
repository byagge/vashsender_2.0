# Generated migration for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mail_templates', '0004_templateimage'),
    ]

    operations = [
        # Оставляем только добавление индексов.
        # Изменение ForeignKey на owner убрано, чтобы избежать проблем с
        # ссылками на кастомную модель пользователя в разных БД.
        migrations.AddIndex(
            model_name='emailtemplate',
            index=models.Index(fields=['owner', '-updated_at'], name='mail_templ_owner_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='emailtemplate',
            index=models.Index(fields=['owner', 'is_draft'], name='mail_templ_owner_draft_idx'),
        ),
    ]
