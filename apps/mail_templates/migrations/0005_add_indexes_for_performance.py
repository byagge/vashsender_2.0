# Generated migration for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mail_templates', '0004_templateimage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailtemplate',
            name='owner',
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name='email_templates',
                to='emails.customuser',
                db_index=True  # Добавляем индекс для быстрой фильтрации по владельцу
            ),
        ),
        migrations.AlterField(
            model_name='templateimage',
            name='owner',
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name='template_images',
                to='emails.customuser',
                db_index=True  # Добавляем индекс для быстрой фильтрации по владельцу
            ),
        ),
        # Добавляем составной индекс для owner + updated_at для быстрой сортировки
        migrations.AddIndex(
            model_name='emailtemplate',
            index=models.Index(fields=['owner', '-updated_at'], name='mail_templ_owner_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='emailtemplate',
            index=models.Index(fields=['owner', 'is_draft'], name='mail_templ_owner_draft_idx'),
        ),
    ]
