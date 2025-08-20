from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.billing.models import PlanType, Plan, BillingSettings


class Command(BaseCommand):
    help = 'Инициализация тарифных планов согласно pricing.html'

    def handle(self, *args, **options):
        self.stdout.write('Создание типов тарифов...')
        
        # Создаем типы тарифов
        plan_types = {
            'Free': {
                'name': 'Free',
                'description': 'Бесплатный тариф для начала работы'
            },
            'Subscribers': {
                'name': 'Subscribers', 
                'description': 'Тариф по количеству подписчиков'
            },
            'Letters': {
                'name': 'Letters',
                'description': 'Тариф по количеству писем'
            }
        }
        
        for plan_type_data in plan_types.values():
            plan_type, created = PlanType.objects.get_or_create(
                name=plan_type_data['name'],
                defaults=plan_type_data
            )
            if created:
                self.stdout.write(f'Создан тип тарифа: {plan_type.name}')
            else:
                self.stdout.write(f'Тип тарифа уже существует: {plan_type.name}')
        
        self.stdout.write('Создание тарифных планов...')
        
        # Получаем типы тарифов
        free_type = PlanType.objects.get(name='Free')
        subscribers_type = PlanType.objects.get(name='Subscribers')
        letters_type = PlanType.objects.get(name='Letters')
        
        # Создаем базовые тарифные планы
        base_plans_data = [
            # Бесплатный тариф
            {
                'title': 'Бесплатный',
                'plan_type': free_type,
                'subscribers': 200,
                'emails_per_month': 0,  # неограниченно
                'max_emails_per_day': 50,
                'price': 0.00,
                'discount': 0,
                'is_active': True,
                'is_featured': False,
                'sort_order': 1
            }
        ]
        
        for plan_data in base_plans_data:
            plan, created = Plan.objects.get_or_create(
                title=plan_data['title'],
                plan_type=plan_data['plan_type'],
                defaults=plan_data
            )
            if created:
                self.stdout.write(f'Создан тариф: {plan.title} - {plan.price}₽')
            else:
                # Обновляем существующий тариф
                for key, value in plan_data.items():
                    setattr(plan, key, value)
                plan.save()
                self.stdout.write(f'Обновлен тариф: {plan.title} - {plan.price}₽')
        
        # Генерируем тарифы по подписчикам согласно новым ценам
        self.stdout.write('Создание тарифов по подписчикам...')
        
        # Новые тарифы по подписчикам
        subscribers_steps = [
            (1000, 590), (1500, 840), (2000, 1090), (3000, 1490), (4000, 1780),
            (5000, 1990), (7500, 2470), (10000, 2940), (15000, 3830), (20000, 4680),
            (25000, 5490), (30000, 6260), (40000, 7760), (50000, 8990), (60000, 10220),
            (70000, 11450), (80000, 12680), (90000, 13900), (100000, 14900), (125000, 18250),
            (150000, 21490), (200000, 27180), (250000, 32375), (300000, 36700),
            (400000, 43500), (500000, 47400), (750000, 66750), (1000000, 82950)
        ]
        
        for idx, (subs, price) in enumerate(subscribers_steps, start=2):
            plan, created = Plan.objects.get_or_create(
                title=f'Подписчики {subs:,}'.replace(",", " "),
                plan_type=subscribers_type,
                defaults={
                    'subscribers': subs,
                    'emails_per_month': 0,
                    'max_emails_per_day': self._get_daily_limit(subs),
                    'price': price,
                    'discount': 0,
                    'is_active': True,
                    'is_featured': subs == 1000,  # Только 1000 подписчиков как популярный
                    'sort_order': idx
                }
            )
            if created:
                self.stdout.write(f'Создан тариф подписчиков: {subs:,} - {price}₽')
            else:
                # Обновляем существующий тариф
                plan.subscribers = subs
                plan.price = price
                plan.max_emails_per_day = self._get_daily_limit(subs)
                plan.is_featured = (subs == 1000)
                plan.sort_order = idx
                plan.save()
                self.stdout.write(f'Обновлен тариф подписчиков: {subs:,} - {price}₽')

        # Генерируем тарифы по письмам согласно новым ценам
        self.stdout.write('Создание тарифов по письмам...')
        
        # Новые тарифы по письмам
        letters_steps = [
            (1000, 380), (1500, 540), (2000, 690), (3000, 890), (4000, 1050),
            (5000, 1190), (7500, 1480), (10000, 1760), (15000, 2290), (20000, 2900),
            (25000, 3400), (30000, 3880), (40000, 4890), (50000, 5850), (60000, 6640),
            (70000, 7440), (80000, 8250), (90000, 9030), (100000, 9690), (125000, 11870),
            (150000, 13960), (200000, 17650), (250000, 21040), (300000, 23850),
            (400000, 28280), (500000, 30810), (750000, 43390), (1000000, 53900)
        ]
        
        for idx, (emails, price) in enumerate(letters_steps, start=len(subscribers_steps) + 2):
            plan, created = Plan.objects.get_or_create(
                title=f'Письма {emails:,}'.replace(",", " "),
                plan_type=letters_type,
                defaults={
                    'subscribers': 0,
                    'emails_per_month': emails,
                    'max_emails_per_day': 0,  # Не применяется для тарифов с письмами
                    'price': price,
                    'discount': 0,
                    'is_active': True,
                    'is_featured': False,
                    'sort_order': idx
                }
            )
            if created:
                self.stdout.write(f'Создан тариф писем: {emails:,} - {price}₽')
            else:
                # Обновляем существующий тариф
                plan.emails_per_month = emails
                plan.price = price
                plan.sort_order = idx
                plan.save()
                self.stdout.write(f'Обновлен тариф писем: {emails:,} - {price}₽')
        
        # Создаем настройки биллинга
        self.stdout.write('Создание настроек биллинга...')
        settings, created = BillingSettings.objects.get_or_create(
            pk=1,
            defaults={
                'free_plan_subscribers': 200,
                'free_plan_emails': 0,  # неограниченно
                'free_plan_daily_limit': 50,
                'cloudpayments_test_mode': True,
                'auto_renewal_enabled': True,
                'auto_renewal_days_before': 3
            }
        )
        
        if created:
            self.stdout.write('Созданы настройки биллинга')
        else:
            self.stdout.write('Настройки биллинга уже существуют')
        
        # Выводим статистику
        total_plans = Plan.objects.count()
        subscribers_plans = Plan.objects.filter(plan_type=subscribers_type).count()
        letters_plans = Plan.objects.filter(plan_type=letters_type).count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Тарифы успешно инициализированы!\n'
                f'Всего тарифов: {total_plans}\n'
                f'Тарифов по подписчикам: {subscribers_plans}\n'
                f'Тарифов по письмам: {letters_plans}'
            )
        )
    
    def _get_daily_limit(self, subscribers):
        """Определяет дневной лимит писем на основе количества подписчиков"""
        if subscribers <= 1000:
            return 200
        elif subscribers <= 5000:
            return 500
        elif subscribers <= 10000:
            return 1000
        elif subscribers <= 50000:
            return 2000
        elif subscribers <= 100000:
            return 5000
        elif subscribers <= 500000:
            return 10000
        else:
            return 20000 