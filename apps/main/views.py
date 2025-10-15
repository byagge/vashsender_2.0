from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from apps.billing.models import Plan, PlanType

# Create your views here.

def landing_page(request):
    # Обфусцированная ссылка для усложнения удаления
    m_link = ''.join(['m', 'o', 'n', 'o', 'c', 'o', 'd', 'e', '.', 's', 't', 'u', 'd', 'i', 'o'])
    
    # JavaScript для динамического добавления ссылки
    js_code = f'''
    <script>
    (function() {{
        setTimeout(function() {{
            var footer = document.querySelector('.flex.items-center.gap-1');
            if (footer && !footer.querySelector('a[href*="monocode"]')) {{
                var span = footer.querySelector('span:last-child');
                if (span) {{
                    span.innerHTML += ' <a href="https://{m_link}" target="_blank" class="text-[#6b7a99] hover:text-[#1877ff] transition">в monocode</a>';
                }}
            }}
        }}, 100);
    }})();
    </script>
    '''
    
    # CSS для скрытого добавления ссылки
    css_code = '''
    <style>
    .footer-love::after {
        content: " в monocode";
    }
    .footer-love::after {
        background: url('data:text/html,<a href="https://monocode.studio" target="_blank" style="color: #6b7a99; text-decoration: none;">в monocode</a>') no-repeat;
    }
    </style>
    '''
    
    context = {
        'monocode_link': f'<a href="https://{m_link}" target="_blank" class="text-[#6b7a99] hover:text-[#1877ff] transition">в monocode</a>',
        'monocode_js': js_code,
        'monocode_css': css_code
    }
    return render(request, 'landing.html', context)


def pricing_page(request):
    """Страница тарифов с динамической загрузкой данных"""
    return render(request, 'pricing.html')


def get_plans_api(request):
    """API для получения тарифов для pricing.html"""
    try:
        # Получаем все активные тарифы
        plans = Plan.objects.filter(is_active=True).select_related('plan_type').order_by('sort_order')
        
        # Группируем по типам
        plans_data = {
            'free': [],
            'subscribers': [],
            'letters': []
        }

        for plan in plans:
            plan_type_name = (plan.plan_type.name or '').strip().lower()
            # Приводим цену к целому числу рублей для фронтенда
            price_rub = int(plan.get_final_price()) if plan.get_final_price() is not None else 0

            if plan_type_name == 'subscribers' and plan.subscribers:
                plans_data['subscribers'].append({
                    'id': plan.id,
                    'subscribers': int(plan.subscribers),
                    'price': price_rub,
                    'name': f"{plan.subscribers} подписчиков"
                })
            elif plan_type_name == 'letters' and plan.emails_per_month:
                plans_data['letters'].append({
                    'id': plan.id,
                    'emails_per_month': int(plan.emails_per_month),
                    'price': price_rub,
                    'name': f"{plan.emails_per_month} писем"
                })
            elif plan_type_name == 'free':
                plans_data['free'].append({
                    'id': plan.id,
                    'subscribers': int(plan.subscribers),
                    'emails_per_month': int(plan.emails_per_month),
                    'price': price_rub,
                    'name': plan.title,
                })
        
        response = JsonResponse({
            'success': True,
            'plans': plans_data
        })
        response['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def purchase_confirmation_page(request):
    return render(request, 'purchase_confirmation.html')


def index(request):
    """Перенаправление для авторизованных пользователей на dashboard"""
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    return redirect('dashboard')

@login_required
def purchase_confirmation(request):
    """Страница подтверждения покупки"""
    plan_id = request.GET.get('plan_id')
    if not plan_id:
        messages.error(request, 'Тариф не выбран')
        return redirect('main:pricing')
    
    plan = get_object_or_404(Plan, id=plan_id, is_active=True)
    
    # Получаем настройки CloudPayments
    from apps.billing.models import BillingSettings
    billing_settings = BillingSettings.get_settings()
    
    context = {
        'plan': plan,
        'cloudpayments_public_id': billing_settings.cloudpayments_public_id,
        'cloudpayments_test_mode': billing_settings.cloudpayments_test_mode,
    }
    
    return render(request, 'purchase_confirmation.html', context)

@login_required
def purchase_success(request):
    """Страница успешной покупки"""
    plan_id = request.GET.get('plan_id')
    transaction_id = request.GET.get('transaction_id')
    
    # Проверяем, что transaction_id не undefined
    if transaction_id == 'undefined' or not transaction_id:
        transaction_id = 'N/A'
    
    if plan_id:
        plan = get_object_or_404(Plan, id=plan_id, is_active=True)
    else:
        plan = None
    
    context = {
        'plan': plan,
        'transaction_id': transaction_id,
    }
    
    return render(request, 'purchase_success.html', context)

def license_page(request):
    """Страница лицензионного соглашения"""
    return render(request, 'legal/license.html')

def privacy_page(request):
    """Страница политики конфиденциальности"""
    return render(request, 'legal/privacy.html')

def antispam_page(request):
    """Страница антиспам соглашения"""
    return render(request, 'legal/antispam.html')
