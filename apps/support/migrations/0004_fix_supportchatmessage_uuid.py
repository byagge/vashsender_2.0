from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0003_supportchat_supportchatmessage'),
    ]

    operations = [
        migrations.RunSQL(
            sql=r"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'support_supportchatmessage'
                      AND column_name = 'message_id'
                      AND data_type IN ('text', 'character varying')
                ) THEN
                    ALTER TABLE support_supportchatmessage
                    ALTER COLUMN message_id TYPE uuid USING message_id::uuid;
                END IF;
            END
            $$;
            """,
            reverse_sql=r"""
            -- No reverse operation; keeping UUID type
            SELECT 1;
            """,
        ),
    ]


