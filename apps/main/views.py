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
        
        print(f"DEBUG: Found {plans.count()} plans")
        
        # Группируем по типам
        plans_data = {
            'free': [],
            'subscribers': [],
            'letters': []
        }
        
        for plan in plans:
            print(f"DEBUG: Processing plan {plan.id}: {plan.title} ({plan.plan_type.name})")
            plan_data = {
                'id': plan.id,
                'title': plan.title,
                'price': float(plan.get_final_price()),
                'subscribers': plan.subscribers,
                'emails_per_month': plan.emails_per_month,
                'max_emails_per_day': plan.max_emails_per_day,
                'is_featured': plan.is_featured,
                'sort_order': plan.sort_order
            }
            
            if plan.plan_type.name == 'Free':
                plans_data['free'].append(plan_data)
            elif plan.plan_type.name == 'Subscribers':
                plans_data['subscribers'].append(plan_data)
            elif plan.plan_type.name == 'Letters':
                plans_data['letters'].append(plan_data)
        
        print(f"DEBUG: Final data - Free: {len(plans_data['free'])}, Subscribers: {len(plans_data['subscribers'])}, Letters: {len(plans_data['letters'])}")
        
        response = JsonResponse({
            'success': True,
            'plans': plans_data
        })
        response['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        print(f"DEBUG: Error in get_plans_api: {e}")
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
