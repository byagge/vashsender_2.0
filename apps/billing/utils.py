from django.utils import timezone
from django.db.models import Sum
from .models import PurchasedPlan, Plan, BillingSettings
from apps.campaigns.models import EmailTracking


def get_user_active_plan(user):
    """Получить активный тариф пользователя"""
    return PurchasedPlan.objects.filter(
        user=user,
        is_active=True,
        end_date__gt=timezone.now()
    ).order_by('-start_date').first()


def get_user_emails_remaining(user):
    """Получить количество оставшихся писем для пользователя"""
    active_plan = get_user_active_plan(user)
    if not active_plan:
        return 0
    
    return active_plan.get_emails_remaining()


def get_user_emails_sent(user):
    """Получить количество отправленных писем пользователя в текущем тарифе"""
    active_plan = get_user_active_plan(user)
    if not active_plan:
        return 0
    
    return active_plan.emails_sent


def get_user_emails_sent_today(user):
    """Получить количество писем, отправленных пользователем сегодня"""
    from datetime import datetime, time
    today_start = datetime.combine(datetime.now().date(), time.min)
    today_end = datetime.combine(datetime.now().date(), time.max)
    
    return EmailTracking.objects.filter(
        campaign__user=user,
        sent_at__gte=today_start,
        sent_at__lte=today_end
    ).count()


def _get_last_subscribers_purchase(user):
    """Последняя покупка тарифа типа Subscribers (не обязательно активная)."""
    return (
        PurchasedPlan.objects
        .filter(user=user, plan__plan_type__name='Subscribers')
        .order_by('-start_date')
        .first()
    )


def _get_letters_pool(user):
    """Рассчитать общий пул писем по всем покупкам Letters после последнего тарифа Subscribers.

    Возвращает словарь: {
        'total_purchased': int,      # сумма купленных писем
        'period_start': datetime,    # начало периода накопления
        'sent_in_period': int,       # фактически отправлено за период
        'remaining': int             # остаток писем
    }
    """
    last_sub = _get_last_subscribers_purchase(user)
    letters_qs = PurchasedPlan.objects.filter(user=user, plan__plan_type__name='Letters')
    if last_sub:
        letters_qs = letters_qs.filter(start_date__gt=last_sub.start_date)

    letters_qs = letters_qs.order_by('start_date')
    first_letters = letters_qs.first()
    if not first_letters:
        return {
            'total_purchased': 0,
            'period_start': None,
            'sent_in_period': 0,
            'remaining': 0,
        }

    total_purchased = (
        letters_qs.values('plan__emails_per_month')
        .aggregate(total=Sum('plan__emails_per_month'))['total'] or 0
    )

    period_start = first_letters.start_date
    sent_in_period = EmailTracking.objects.filter(
        campaign__user=user,
        sent_at__gte=period_start,
    ).count()

    remaining = max(0, int(total_purchased) - int(sent_in_period))
    return {
        'total_purchased': int(total_purchased),
        'period_start': period_start,
        'sent_in_period': int(sent_in_period),
        'remaining': remaining,
    }


def update_plan_emails_sent(user):
    """Синхронизировать счётчики отправленных писем.

    - Для Subscribers: считаем в рамках активного плана (месяц)
    - Для Letters: считаем от начала периода накопления (после последнего Subscribers)
    """
    active_plan = get_user_active_plan(user)
    if active_plan and active_plan.plan.plan_type.name in ('Subscribers', 'Free'):
        actual_sent = EmailTracking.objects.filter(
            campaign__user=user,
            sent_at__gte=active_plan.start_date,
            sent_at__lte=active_plan.end_date,
        ).count()
        if active_plan.emails_sent != actual_sent:
            active_plan.emails_sent = actual_sent
            active_plan.save(update_fields=['emails_sent'])
        return actual_sent

    # Если активный план отсутствует или сейчас Letters, применяем логику накопления
    letters_pool = _get_letters_pool(user)
    return letters_pool['sent_in_period']


def _ensure_monthly_free_if_needed(user):
    """Гарантировать, что у пользователя есть активный бесплатный месячный план,
    если нет активного Subscribers и нет пула Letters."""
    now = timezone.now()
    active = get_user_active_plan(user)
    if active:
        return active
    # Есть ли покупки Letters? Если да — бесплатный не нужен
    letters_pool = _get_letters_pool(user)
    if letters_pool['total_purchased'] > 0 and letters_pool['remaining'] > 0:
        return None

    settings = BillingSettings.get_settings()
    free_plan = Plan.objects.filter(price=0, is_active=True).order_by('id').first()
    if not free_plan:
        return None

    last_free = (
        PurchasedPlan.objects
        .filter(user=user, plan=free_plan)
        .order_by('-start_date')
        .first()
    )
    if last_free and last_free.end_date > now:
        return last_free

    # Создаем новый бесплатный период на ~30 дней
    new_free = PurchasedPlan.objects.create(
        user=user,
        plan=free_plan,
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        is_active=True,
        amount_paid=0,
        payment_method='free',
    )
    return new_free


def can_user_send_emails(user, count=1):
    """Проверить, может ли пользователь отправить указанное количество писем по правилам тарифов."""
    active_plan = get_user_active_plan(user)
    if active_plan and active_plan.plan.plan_type.name in ('Subscribers', 'Free'):
        limit = active_plan.plan.subscribers or BillingSettings.get_settings().free_plan_subscribers or 0
        remaining = max(0, limit - (update_plan_emails_sent(user) or 0))
        return remaining >= count and not active_plan.is_expired()

    # Letters-пул: суммируем покупки после последнего Subscribers
    letters_pool = _get_letters_pool(user)
    if letters_pool['total_purchased'] > 0:
        return letters_pool['remaining'] >= count

    # Иначе — бесплатный месячный тариф
    free_plan = _ensure_monthly_free_if_needed(user)
    if free_plan:
        remaining = max(0, (BillingSettings.get_settings().free_plan_subscribers or 0) - (update_plan_emails_sent(user) or 0))
        return remaining >= count

    return False


def add_emails_sent_to_plan(user, count=1):
    """Добавить количество отправленных писем к тарифу пользователя"""
    active_plan = get_user_active_plan(user)
    if not active_plan:
        return False
    
    active_plan.add_emails_sent(count)
    return True


def get_user_plan_info(user):
    """Получить полную информацию о тарифе пользователя с учетом описанных правил."""
    # 1) Активный Subscribers-план (месячный лимит и дата окончания)
    active_plan = get_user_active_plan(user)
    if active_plan and active_plan.plan.plan_type.name in ('Subscribers', 'Free'):
        actual_sent = update_plan_emails_sent(user)
        emails_sent_today = get_user_emails_sent_today(user)
        limit = active_plan.plan.subscribers or (BillingSettings.get_settings().free_plan_subscribers or 0)
        remaining = max(0, limit - (actual_sent or 0))
        return {
            'has_plan': True,
            'plan_name': active_plan.plan.title,
            'plan_type': 'Subscribers',
            'plan_price': float(active_plan.plan.get_final_price()),
            'emails_limit': None,
            'subscribers_limit': limit,
            'emails_sent': actual_sent or 0,
            'emails_remaining': None,
            'days_remaining': active_plan.days_remaining(),
            'is_expired': active_plan.is_expired(),
            'start_date': active_plan.start_date,
            'end_date': active_plan.end_date,
            'emails_sent_today': emails_sent_today,
        }

    # 2) Пул Letters (бессрочно суммируем покупки после последнего Subscribers)
    letters_pool = _get_letters_pool(user)
    if letters_pool['total_purchased'] > 0:
        emails_sent_today = get_user_emails_sent_today(user)
        return {
            'has_plan': True,
            'plan_name': 'Письма',
            'plan_type': 'Letters',
            'plan_price': None,
            'emails_limit': letters_pool['total_purchased'],
            'subscribers_limit': None,
            'emails_sent': letters_pool['sent_in_period'],
            'emails_remaining': letters_pool['remaining'],
            'days_remaining': 0,
            'is_expired': False,
            'start_date': letters_pool['period_start'],
            'end_date': None,
            'emails_sent_today': emails_sent_today,
        }

    # 3) Бесплатный месячный тариф как Subscribers  (200 по умолчанию)
    free_active = _ensure_monthly_free_if_needed(user)
    if free_active:
        actual_sent = update_plan_emails_sent(user)
        emails_sent_today = get_user_emails_sent_today(user)
        limit = BillingSettings.get_settings().free_plan_subscribers or 0
        remaining = max(0, limit - (actual_sent or 0))
        return {
            'has_plan': True,
            'plan_name': free_active.plan.title,
            'plan_type': 'Subscribers',
            'plan_price': 0.0,
            'emails_limit': None,
            'subscribers_limit': limit,
            'emails_sent': actual_sent or 0,
            'emails_remaining': None,
            'days_remaining': free_active.days_remaining(),
            'is_expired': free_active.is_expired(),
            'start_date': free_active.start_date,
            'end_date': free_active.end_date,
            'emails_sent_today': emails_sent_today,
        }

    # 4) Нет данных — считаем, что плана нет
    return {
        'has_plan': False,
        'plan_name': None,
        'plan_type': None,
        'plan_price': None,
        'emails_limit': 0,
        'emails_sent': 0,
        'emails_remaining': 0,
        'days_remaining': 0,
        'is_expired': True,
        'emails_sent_today': 0,
    }