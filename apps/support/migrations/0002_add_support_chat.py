# Generated manually

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportChat',
            fields=[
                ('chat_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('chat_status', models.CharField(choices=[('open', 'Открыт'), ('in_progress', 'В работе'), ('waiting', 'Ожидает ответа'), ('resolved', 'Решён'), ('closed', 'Закрыт')], default='open', max_length=20)),
                ('chat_created_at', models.DateTimeField(auto_now_add=True)),
                ('chat_updated_at', models.DateTimeField(auto_now=True)),
                ('chat_assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_support_chats', to='auth.user')),
                ('chat_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_chats', to='auth.user')),
            ],
            options={
                'ordering': ['-chat_updated_at'],
            },
        ),
        migrations.CreateModel(
            name='SupportChatMessage',
            fields=[
                ('message_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('message_text', models.TextField()),
                ('message_staff_reply', models.BooleanField(default=False)),
                ('message_created_at', models.DateTimeField(auto_now_add=True)),
                ('chat_message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_messages', to='support.supportchat')),
                ('message_author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_messages', to='auth.user')),
            ],
            options={
                'ordering': ['message_created_at'],
            },
        ),
    ] 