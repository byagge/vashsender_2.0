from django.core.management.base import BaseCommand
from django.db import transaction
from apps.campaigns.models import Campaign, EmailTracking


class Command(BaseCommand):
    help = 'Переводит кампании из статуса failed в sent, если доставлено >= 70% от отправленных'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только показать изменения без сохранения')
        parser.add_argument('--limit', type=int, default=10000, help='Ограничить количество обрабатываемых кампаний')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = Campaign.objects.filter(status=Campaign.STATUS_FAILED)[:limit]
        total = qs.count()
        fixed = 0

        self.stdout.write(f"Найдено {total} кампаний со статусом 'failed' для проверки")

        for campaign in qs:
            sent = EmailTracking.objects.filter(campaign=campaign).count()
            if sent == 0:
                continue
            delivered = EmailTracking.objects.filter(campaign=campaign, delivered_at__isnull=False).count()

            ratio = delivered / sent if sent else 0
            if ratio >= 0.7:
                fixed += 1
                self.stdout.write(f"  -> {campaign.id} '{campaign.name}' delivered {delivered}/{sent} ({ratio:.0%}), меняем failed -> sent")
                if not dry_run:
                    with transaction.atomic():
                        campaign.status = Campaign.STATUS_SENT
                        campaign.failure_reason = None
                        campaign.save(update_fields=['status', 'failure_reason'])

        self.stdout.write(self.style.SUCCESS(f"Готово. Исправлено кампаний: {fixed}"))


