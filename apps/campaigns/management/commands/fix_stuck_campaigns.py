from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.tasks import auto_fix_stuck_campaigns, cleanup_stuck_campaigns


class Command(BaseCommand):
    help = 'Диагностика и исправление зависших кампаний'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно исправить все зависшие кампании',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет исправлено без внесения изменений',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=15,
            help='Таймаут в минутах для определения зависших кампаний (по умолчанию: 15)',
        )

    def handle(self, *args, **options):
        self.stdout.write('=== Диагностика зависших кампаний ===')
        
        timeout_minutes = options['timeout']
        cutoff_time = timezone.now() - timedelta(minutes=timeout_minutes)
        
        # Находим зависшие кампании
        stuck_campaigns = Campaign.objects.filter(
            status=Campaign.STATUS_SENDING,
            updated_at__lt=cutoff_time
        )
        
        self.stdout.write(f'Найдено {stuck_campaigns.count()} зависших кампаний (старше {timeout_minutes} минут)')
        
        if not stuck_campaigns.exists():
            self.stdout.write(self.style.SUCCESS('Зависших кампаний не найдено'))
            return
        
        # Показываем детали каждой кампании
        for campaign in stuck_campaigns:
            self.stdout.write(f'\nКампания: {campaign.name} (ID: {campaign.id})')
            self.stdout.write(f'  Статус: {campaign.status}')
            self.stdout.write(f'  Обновлена: {campaign.updated_at}')
            self.stdout.write(f'  Task ID: {campaign.celery_task_id}')
            
            # Проверяем статистику отправки
            sent_count = CampaignRecipient.objects.filter(
                campaign=campaign, 
                is_sent=True
            ).count()
            
            total_count = CampaignRecipient.objects.filter(campaign=campaign).count()
            
            self.stdout.write(f'  Отправлено: {sent_count}/{total_count}')
            
            # Проверяем контакты
            total_contacts = 0
            for contact_list in campaign.contact_lists.all():
                total_contacts += contact_list.contacts.count()
            
            self.stdout.write(f'  Контактов в списках: {total_contacts}')
        
        if options['dry_run']:
            self.stdout.write('\n' + self.style.WARNING('DRY RUN - изменения не будут внесены'))
            return
        
        if not options['force']:
            response = input('\nИсправить зависшие кампании? (y/N): ')
            if response.lower() != 'y':
                self.stdout.write('Операция отменена')
                return
        
        # Запускаем автоматическое исправление
        self.stdout.write('\nЗапуск автоматического исправления...')
        
        try:
            # Запускаем задачу исправления
            result = auto_fix_stuck_campaigns.delay()
            self.stdout.write(f'Задача исправления запущена: {result.id}')
            
            # Ждем завершения
            result.get(timeout=60)
            
            self.stdout.write(self.style.SUCCESS('Исправление завершено'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при исправлении: {e}'))
        
        # Показываем финальную статистику
        self.stdout.write('\n=== Финальная статистика ===')
        
        # Проверяем оставшиеся зависшие кампании
        remaining_stuck = Campaign.objects.filter(
            status=Campaign.STATUS_SENDING,
            updated_at__lt=cutoff_time
        ).count()
        
        self.stdout.write(f'Оставшихся зависших кампаний: {remaining_stuck}')
        
        # Показываем статистику по статусам
        status_stats = Campaign.objects.values('status').annotate(
            count=models.Count('id')
        )
        
        self.stdout.write('\nСтатистика по статусам:')
        for stat in status_stats:
            self.stdout.write(f'  {stat["status"]}: {stat["count"]}')