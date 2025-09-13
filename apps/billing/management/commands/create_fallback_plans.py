from django.core.management.base import BaseCommand
from apps.billing.models import Plan, PlanType


class Command(BaseCommand):
    help = 'Создает базовые fallback планы в базе данных'

    def handle(self, *args, **options):
        # Создаем типы планов если их нет
        subscribers_type, created = PlanType.objects.get_or_create(
            name='subscribers',
            defaults={'display_name': 'Подписчики'}
        )
        if created:
            self.stdout.write(f'Создан тип плана: {subscribers_type.name}')

        letters_type, created = PlanType.objects.get_or_create(
            name='letters',
            defaults={'display_name': 'Письма'}
        )
        if created:
            self.stdout.write(f'Создан тип плана: {letters_type.name}')

        # Fallback цены для подписчиков
        subscribers_prices = {
            1000: 590,
            5000: 1990,
            10000: 2940,
            20000: 4680,
            25000: 5490,
            50000: 9900,
            100000: 18000,
            500000: 75000,
            1000000: 140000
        }

        # Fallback цены для писем
        letters_prices = {
            1000: 380,
            5000: 1190,
            10000: 1760,
            20000: 2900,
            25000: 3400,
            50000: 6500,
            100000: 12000,
            500000: 55000,
            1000000: 100000
        }

        # Создаем планы для подписчиков
        for count, price in subscribers_prices.items():
            plan, created = Plan.objects.get_or_create(
                id=1000 + list(subscribers_prices.keys()).index(count),
                defaults={
                    'title': f'{count} подписчиков',
                    'plan_type': subscribers_type,
                    'subscribers': count,
                    'price': price,
                    'is_active': True,
                    'sort_order': count
                }
            )
            if created:
                self.stdout.write(f'Создан план подписчиков: {plan.title} (ID: {plan.id})')
            else:
                self.stdout.write(f'План подписчиков уже существует: {plan.title} (ID: {plan.id})')

        # Создаем планы для писем
        for count, price in letters_prices.items():
            plan, created = Plan.objects.get_or_create(
                id=2000 + list(letters_prices.keys()).index(count),
                defaults={
                    'title': f'{count} писем',
                    'plan_type': letters_type,
                    'emails_per_month': count,
                    'price': price,
                    'is_active': True,
                    'sort_order': count
                }
            )
            if created:
                self.stdout.write(f'Создан план писем: {plan.title} (ID: {plan.id})')
            else:
                self.stdout.write(f'План писем уже существует: {plan.title} (ID: {plan.id})')

        self.stdout.write(
            self.style.SUCCESS('Базовые планы успешно созданы!')
        )
