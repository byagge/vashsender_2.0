from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _
from apps.billing.models import BillingSettings


class Command(BaseCommand):
    help = 'Инициализация настроек CloudPayments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--public-id',
            type=str,
            help='Public ID CloudPayments'
        )
        parser.add_argument(
            '--api-secret',
            type=str,
            help='API Secret CloudPayments'
        )
        parser.add_argument(
            '--test-mode',
            action='store_true',
            default=True,
            help='Тестовый режим (по умолчанию включен)'
        )
        parser.add_argument(
            '--production-mode',
            action='store_true',
            help='Продакшн режим (отключает тестовый режим)'
        )

    def handle(self, *args, **options):
        try:
            # Получаем или создаем настройки
            settings, created = BillingSettings.objects.get_or_create(pk=1)
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS('Созданы новые настройки биллинга')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Настройки биллинга уже существуют')
                )

            # Обновляем настройки CloudPayments
            updated = False
            
            if options['public_id']:
                settings.cloudpayments_public_id = options['public_id']
                updated = True
                self.stdout.write(f'Установлен Public ID: {options["public_id"]}')
            
            if options['api_secret']:
                settings.cloudpayments_api_secret = options['api_secret']
                updated = True
                self.stdout.write('Установлен API Secret')
            
            if options['production_mode']:
                settings.cloudpayments_test_mode = False
                updated = True
                self.stdout.write('Включен продакшн режим')
            elif options['test_mode']:
                settings.cloudpayments_test_mode = True
                updated = True
                self.stdout.write('Включен тестовый режим')

            if updated:
                settings.save()
                self.stdout.write(
                    self.style.SUCCESS('Настройки CloudPayments обновлены')
                )
            
            # Показываем текущие настройки
            self.stdout.write('\nТекущие настройки CloudPayments:')
            self.stdout.write(f'Public ID: {settings.cloudpayments_public_id or "НЕ УСТАНОВЛЕН"}')
            self.stdout.write(f'API Secret: {"УСТАНОВЛЕН" if settings.cloudpayments_api_secret else "НЕ УСТАНОВЛЕН"}')
            self.stdout.write(f'Тестовый режим: {"Да" if settings.cloudpayments_test_mode else "Нет"}')
            
            if not settings.cloudpayments_public_id:
                self.stdout.write(
                    self.style.WARNING('\nВНИМАНИЕ: Public ID не установлен!')
                )
                self.stdout.write(
                    'Для установки выполните: python manage.py init_cloudpayments_settings --public-id YOUR_PUBLIC_ID'
                )
            
            if not settings.cloudpayments_api_secret:
                self.stdout.write(
                    self.style.WARNING('\nВНИМАНИЕ: API Secret не установлен!')
                )
                self.stdout.write(
                    'Для установки выполните: python manage.py init_cloudpayments_settings --api-secret YOUR_API_SECRET'
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при инициализации настроек: {e}')
            ) 