from django.db import migrations, models


def set_existing_dmarc_to_none(apps, schema_editor):
    Domain = apps.get_model('emails', 'Domain')
    Domain.objects.all().update(dmarc_policy='none')


class Migration(migrations.Migration):

    dependencies = [
        ('emails', '0011_domain_dmarc_policy'),
    ]

    operations = [
        migrations.AlterField(
            model_name='domain',
            name='dmarc_policy',
            field=models.CharField(
                choices=[('none', 'None'), ('quarantine', 'Quarantine'), ('reject', 'Reject')],
                default='none',
                max_length=20,
            ),
        ),
        migrations.RunPython(set_existing_dmarc_to_none, reverse_code=migrations.RunPython.noop),
    ]


