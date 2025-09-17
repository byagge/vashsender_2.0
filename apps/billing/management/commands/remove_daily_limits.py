from django.core.management.base import BaseCommand
from apps.billing.models import Plan, BillingSettings


class Command(BaseCommand):
    help = 'Убирает дневные лимиты для тарифов с письмами и бесплатного тарифа'

    def handle(self, *args, **options):
        self.stdout.write('Убираем дневные лимиты...')
        
        # Обновляем бесплатные настройки
        settings = BillingSettings.get_settings()
        if settings.free_plan_daily_limit > 0:
            settings.free_plan_daily_limit = 0
            settings.save()
            self.stdout.write('✅ Обновлены настройки бесплатного тарифа: дневной лимит = 0 (неограниченно)')
        
        # Обновляем все тарифы с письмами
        letters_plans = Plan.objects.filter(plan_type__name='Letters')
        updated_count = 0
        
        for plan in letters_plans:
            if plan.max_emails_per_day > 0:
                plan.max_emails_per_day = 0
                plan.save()
                updated_count += 1
                self.stdout.write(f'✅ Обновлен тариф "{plan.title}": дневной лимит = 0 (неограниченно)')
        
        # Обновляем все тарифы с подписчиками, которые имеют дневные лимиты (оставляем их для контроля нагрузки)
        # Но убираем дневные лимиты для тарифов, которые имеют emails_per_month > 0
        mixed_plans = Plan.objects.filter(emails_per_month__gt=0, max_emails_per_day__gt=0)
        for plan in mixed_plans:
            plan.max_emails_per_day = 0
            plan.save()
            updated_count += 1
            self.stdout.write(f'✅ Обновлен смешанный тариф "{plan.title}": дневной лимит = 0 (неограниченно)')
        
        # Обновляем бесплатный тариф
        free_plans = Plan.objects.filter(price=0, is_active=True)
        for plan in free_plans:
            if plan.max_emails_per_day > 0:
                plan.max_emails_per_day = 0
                plan.save()
                updated_count += 1
                self.stdout.write(f'✅ Обновлен бесплатный тариф "{plan.title}": дневной лимит = 0 (неограниченно)')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n🎉 Готово! Обновлено {updated_count} тарифов.\n'
            f'Теперь пользователи могут отправлять все письма сразу без дневных ограничений.'
        ))
