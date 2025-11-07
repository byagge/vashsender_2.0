from django.db import migrations


def convert_message_id_to_uuid(apps, schema_editor):
    # Only run on PostgreSQL; SQLite doesn't support this syntax
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'support_supportchatmessage'
              AND column_name = 'message_id'
            """
        )
        row = cursor.fetchone()
        if not row:
            return
        data_type = row[0]
        if data_type in ('text', 'character varying'):
            cursor.execute(
                """
                ALTER TABLE support_supportchatmessage
                ALTER COLUMN message_id TYPE uuid USING message_id::uuid;
                """
            )


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0003_supportchat_supportchatmessage'),
    ]

    operations = [
        migrations.RunPython(convert_message_id_to_uuid, migrations.RunPython.noop),
    ]


