from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mailer', '0004_importtask_celery_task_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importtask',
            name='id',
            field=models.CharField(primary_key=True, max_length=36, serialize=False),
        ),
    ]


