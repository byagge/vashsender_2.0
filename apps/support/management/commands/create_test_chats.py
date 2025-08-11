from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.support.models import SupportChat, SupportChatMessage
from django.utils import timezone
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Создает тестовые чаты поддержки для демонстрации'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='Количество чатов для создания'
        )

    def handle(self, *args, **options):
        count = options['count']
        
        # Получаем или создаем тестовых пользователей
        staff_user, created = User.objects.get_or_create(
            email='admin@example.com',
            defaults={
                'username': 'admin',
                'is_staff': True,
                'is_superuser': True
            }
        )
        
        if created:
            staff_user.set_password('admin123')
            staff_user.save()
            self.stdout.write(f'Создан администратор: {staff_user.email}')
        
        # Создаем тестовых пользователей
        test_users = []
        for i in range(count):
            user, created = User.objects.get_or_create(
                email=f'user{i+1}@example.com',
                defaults={
                    'username': f'user{i+1}',
                    'first_name': f'Пользователь {i+1}',
                    'last_name': f'Тестовый {i+1}'
                }
            )
            if created:
                user.set_password('user123')
                user.save()
                self.stdout.write(f'Создан пользователь: {user.email}')
            test_users.append(user)
        
        # Создаем чаты
        sample_messages = [
            "Здравствуйте! У меня проблема с отправкой писем",
            "Привет! Как настроить DKIM для домена?",
            "Добрый день! Не могу создать кампанию",
            "Помогите с настройкой SMTP",
            "Есть вопрос по тарифам",
            "Как увеличить лимиты отправки?",
            "Проблема с доставляемостью писем",
            "Нужна помощь с шаблонами",
            "Как добавить новый домен?",
            "Вопрос по API"
        ]
        
        statuses = ['open', 'in_progress', 'waiting', 'resolved', 'closed']
        
        for i, user in enumerate(test_users):
            # Создаем чат
            chat = SupportChat.objects.create(
                chat_user=user,
                chat_status=random.choice(statuses),
                chat_assigned_to=staff_user if random.choice([True, False]) else None
            )
            
            # Добавляем несколько сообщений в чат
            message_count = random.randint(1, 5)
            for j in range(message_count):
                is_staff = j % 2 == 1  # Чередуем пользователя и сотрудника
                author = staff_user if is_staff else user
                
                message = SupportChatMessage.objects.create(
                    chat_message=chat,
                    message_author=author,
                    message_text=random.choice(sample_messages),
                    message_staff_reply=is_staff
                )
                
                # Устанавливаем разные времена для сообщений
                message.message_created_at = timezone.now() - timezone.timedelta(
                    hours=random.randint(1, 48),
                    minutes=random.randint(0, 59)
                )
                message.save()
            
            # Обновляем время последнего сообщения в чате
            chat.chat_updated_at = timezone.now() - timezone.timedelta(
                hours=random.randint(0, 24)
            )
            chat.save()
            
            self.stdout.write(f'Создан чат {chat.chat_id.hex[:8]} для {user.email} с {message_count} сообщениями')
        
        self.stdout.write(
            self.style.SUCCESS(f'Успешно создано {count} тестовых чатов!')
        )
        self.stdout.write(f'Администратор: {staff_user.email} (пароль: admin123)')
        self.stdout.write(f'Тестовые пользователи: user1@example.com - user{count}@example.com (пароль: user123)') 