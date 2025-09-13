from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
import json
from .models import PlanType, Plan, PurchasedPlan, BillingSettings, CloudPaymentsTransaction
from .serializers import (
    PlanTypeSerializer, PlanSerializer, PurchasedPlanSerializer,
    BillingSettingsSerializer, UserPlanInfoSerializer
    # CloudPaymentsTransactionSerializer  # Временно отключено до применения миграций
)
from .cloudpayments import cloudpayments_service


class PlanTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """API для типов тарифов"""
    queryset = PlanType.objects.filter(is_active=True)
    serializer_class = PlanTypeSerializer
    permission_classes = [permissions.AllowAny]


class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    """API для тарифных планов"""
    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Фильтрация по типу плана
        plan_type = self.request.query_params.get('plan_type', None)
        if plan_type:
            queryset = queryset.filter(plan_type__name=plan_type)
        
        # Фильтрация по цене
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)
        
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        return queryset.select_related('plan_type')
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Получить рекомендуемые тарифы"""
        plans = self.get_queryset().filter(is_featured=True)
        serializer = self.get_serializer(plans, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pricing_data(self, request):
        """Получить данные для калькулятора цен"""
        plans = self.get_queryset()
        
        # Группируем планы по типам
        pricing_data = {}
        for plan in plans:
            plan_type = plan.plan_type.name
            if plan_type not in pricing_data:
                pricing_data[plan_type] = []
            
            pricing_data[plan_type].append({
                'subscribers': plan.subscribers,
                'emails': plan.emails_per_month,
                'price': float(plan.get_final_price())
            })
        
        return Response(pricing_data)


class PurchasedPlanViewSet(viewsets.ModelViewSet):
    """API для купленных тарифов"""
    serializer_class = PurchasedPlanSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PurchasedPlan.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Получить текущий активный тариф"""
        current_plan = self.get_queryset().filter(
            is_active=True,
            end_date__gt=timezone.now()
        ).first()
        
        if current_plan:
            serializer = self.get_serializer(current_plan)
            return Response(serializer.data)
        else:
            return Response({'detail': 'Активный тариф не найден'}, status=404)
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """Получить историю тарифов"""
        plans = self.get_queryset().order_by('-start_date')
        serializer = self.get_serializer(plans, many=True)
        return Response(serializer.data)


# class CloudPaymentsViewSet(viewsets.ViewSet):
#     """API для работы с CloudPayments"""
#     permission_classes = [permissions.IsAuthenticated]
#     
#     @action(detail=False, methods=['post'])
#     def create_payment(self, request):
#         """Создать платеж"""
#         plan_id = request.data.get('plan_id')
#         amount = request.data.get('amount')
#         description = request.data.get('description')
#         
#         try:
#             plan = Plan.objects.get(id=plan_id, is_active=True)
#         except Plan.DoesNotExist:
#             return Response(
#                 {'error': 'Тариф не найден'}, 
#                 status=status.HTTP_404_NOT_FOUND
#             )
#         
#         # Создаем платеж
#         payment_data = cloudpayments_service.create_payment(
#             user=request.user,
#             plan=plan,
#             amount=amount,
#             description=description
#         )
#         
#         return Response(payment_data)
#     
#     @action(detail=False, methods=['get'])
#     def transaction_status(self, request):
#         """Получить статус транзакции"""
#         transaction_id = request.query_params.get('transaction_id')
#         
#         if not transaction_id:
#             return Response(
#                 {'error': 'ID транзакции не указан'}, 
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#         
#         try:
#             transaction = CloudPaymentsTransaction.objects.get(
#                 id=transaction_id,
#                 user=request.user
#         )
#             serializer = CloudPaymentsTransactionSerializer(transaction)
#             return Response(serializer.data)
#         except CloudPaymentsTransaction.DoesNotExist:
#             return Response(
#                 {'error': 'Транзакция не найдена'}, 
#                 status=status.HTTP_404_NOT_FOUND
#             )
#     
#     @action(detail=False, methods=['get'])
#     def transactions(self, request):
#         """Получить историю транзакций пользователя"""
#         transactions = CloudPaymentsTransaction.objects.filter(
#             user=request.user
#         ).order_by('-created_at')
#         
#         serializer = CloudPaymentsTransactionSerializer(transactions, many=True)
#         return Response(serializer.data)


class BillingSettingsViewSet(viewsets.ReadOnlyModelViewSet):
    """API для настроек биллинга"""
    queryset = BillingSettings.objects.all()
    serializer_class = BillingSettingsSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_object(self):
        return BillingSettings.get_settings()


class UserPlanInfoViewSet(viewsets.ViewSet):
    """API для информации о плане пользователя"""
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        """Получить информацию о текущем плане пользователя"""
        user = request.user
        
        # Используем новую утилиту для получения информации о тарифе
        from .utils import get_user_plan_info, update_plan_emails_sent
        
        # Обновляем счётчик отправленных писем на основе фактических отправок
        update_plan_emails_sent(user)
        
        # Получаем информацию о тарифе
        plan_info = get_user_plan_info(user)
        
        # Добавляем дополнительную информацию
        plan_info.update({
            'has_exceeded_daily_limit': user.has_exceeded_daily_limit(),
        })
        
        return Response(plan_info)


# Webhook для CloudPayments
@csrf_exempt
@require_http_methods(["POST"])
def cloudpayments_webhook(request):
    """Webhook для обработки уведомлений от CloudPayments"""
    try:
        # Получаем данные
        data = request.POST.dict()
        signature = request.headers.get('X-Signature', '')
        
        print(f"DEBUG: CloudPayments webhook received")
        print(f"DEBUG: Data: {data}")
        print(f"DEBUG: Signature: {signature}")
        
        # Обрабатываем webhook
        result = cloudpayments_service.process_webhook(data, signature)
        
        if result.get('success'):
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse(
                {'status': 'error', 'message': result.get('error')}, 
                status=400
            )
            
    except Exception as e:
        print(f"DEBUG: Webhook error: {e}")
        return JsonResponse(
            {'status': 'error', 'message': str(e)}, 
            status=500
        )


# Views для покупки тарифов
@login_required
def confirm_plan(request):
    """Страница подтверждения покупки тарифа"""
    plan_id = request.GET.get('plan_id')
    plan_type = request.GET.get('plan_type')
    
    # Проверяем, переданы ли параметры fallback плана
    if plan_type and not plan_id:
        # Обрабатываем fallback план
        subscribers = request.GET.get('subscribers')
        emails_per_month = request.GET.get('emails_per_month')
        price = request.GET.get('price')
        name = request.GET.get('name')
        
        if not all([plan_type, price, name]):
            messages.error(request, 'Неполные данные тарифа')
            return redirect('pricing')
        
        # Создаем временный объект плана для fallback
        class FallbackPlan:
            def __init__(self, plan_type, subscribers, emails_per_month, price, name):
                self.id = f"fallback_{plan_type}_{price}"
                self.plan_type = plan_type
                self.subscribers = int(subscribers) if subscribers else None
                self.emails_per_month = int(emails_per_month) if emails_per_month else None
                self.price = int(price)
                self.name = name
                self.title = name
                self.is_fallback = True
            
            def get_final_price(self):
                return self.price
        
        plan = FallbackPlan(plan_type, subscribers, emails_per_month, price, name)
        
    elif plan_id:
        # Обрабатываем обычный план из базы данных
        plan = get_object_or_404(Plan, id=plan_id, is_active=True)
    else:
        messages.error(request, 'Тариф не выбран')
        return redirect('pricing')
    
    # Если тариф бесплатный - активируем сразу
    if plan.price == 0:
        return activate_free_plan(request, plan)
    
    # Получаем настройки CloudPayments
    billing_settings = BillingSettings.get_settings()
    
    # Для платных тарифов показываем страницу подтверждения
    context = {
        'plan': plan,
        'final_price': plan.get_final_price(),
        'duration_days': 30,  # Можно сделать настраиваемым
        'cloudpayments_public_id': billing_settings.cloudpayments_public_id,
        'cloudpayments_test_mode': billing_settings.cloudpayments_test_mode,
    }
    
    if request.method == 'POST':
        return process_plan_purchase(request, plan)
    
    return render(request, 'purchase_confirmation.html', context)


@login_required
def activate_free_plan(request, plan=None):
    """Активация бесплатного тарифа"""
    if not plan:
        plan = Plan.objects.filter(price=0, is_active=True).first()
    
    if not plan:
        messages.error(request, 'Бесплатный тариф недоступен')
        return redirect('pricing')
    
    user = request.user
    
    # Создаем запись о покупке бесплатного тарифа
    PurchasedPlan.objects.create(
        user=user,
        plan=plan,
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=365),  # Год бесплатно
        is_active=True,
        amount_paid=0,
        payment_method='free'
    )
    
    # Обновляем текущий план пользователя
    user.current_plan = plan
    user.plan_expiry = timezone.now() + timedelta(days=365)
    user.save()
    
    messages.success(request, f'Тариф "{plan.title}" успешно активирован!')
    return redirect('dashboard')


@login_required
def process_plan_purchase(request, plan):
    """Обработка покупки платного тарифа"""
    user = request.user
    
    # Временно отключено до настройки CloudPayments
    # payment_data = cloudpayments_service.create_payment(
    #     user=user,
    #     plan=plan
    # )
    # return redirect('billing:payment', transaction_id=payment_data['transaction_id'])
    
    # Временное решение - создаем тестовую покупку
    from django.utils import timezone
    from datetime import timedelta
    
    # Проверяем, является ли это fallback планом
    if hasattr(plan, 'is_fallback') and plan.is_fallback:
        # Для fallback планов создаем временный план в базе данных
        from apps.billing.models import PlanType
        
        # Создаем тип плана если его нет
        plan_type, created = PlanType.objects.get_or_create(
            name=plan.plan_type,
            defaults={'description': f'Тип плана {plan.plan_type}'}
        )
        
        # Создаем временный план в базе данных
        temp_plan = Plan.objects.create(
            title=plan.title,
            plan_type=plan_type,
            subscribers=plan.subscribers or 0,
            emails_per_month=plan.emails_per_month or 0,
            price=plan.price,
            is_active=True
        )
        
        # Используем временный план для создания PurchasedPlan
        actual_plan = temp_plan
    else:
        # Для обычных планов используем существующий план
        actual_plan = plan
    
    purchased_plan = PurchasedPlan.objects.create(
        user=user,
        plan=actual_plan,
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=30),
        is_active=True,
        amount_paid=plan.get_final_price(),
        payment_method='test',
        transaction_id=f'test_{timezone.now().strftime("%Y%m%d_%H%M%S")}'
    )
    
    # Обновляем текущий план пользователя
    user.current_plan = actual_plan
    user.plan_expiry = purchased_plan.end_date
    user.save()
    
    messages.success(request, f'Тариф "{plan.title}" успешно приобретен!')
    return redirect('dashboard')


# @login_required
# def payment_page(request, transaction_id):
#     """Страница оплаты"""
#     try:
#         transaction = CloudPaymentsTransaction.objects.get(
#             id=transaction_id,
#             user=request.user
#         )
#     except CloudPaymentsTransaction.DoesNotExist:
#         messages.error(request, 'Транзакция не найдена')
#         return redirect('dashboard')
#     
#     # Получаем настройки CloudPayments
#     settings = BillingSettings.get_settings()
#     
#     context = {
#         'transaction': transaction,
#         'cloudpayments_public_id': settings.cloudpayments_public_id,
#     }
#     
#     return render(request, 'billing/payment.html', context)


@login_required
def plan_history(request):
    """История тарифов пользователя"""
    purchased_plans = PurchasedPlan.objects.filter(
        user=request.user
    ).order_by('-start_date')
    
    return render(request, 'billing/plan_history.html', {
        'purchased_plans': purchased_plans
    })


@login_required
def billing_page(request):
    """Страница управления тарифами"""
    return render(request, 'billing/billing.html')


@csrf_exempt
def check_auth_status(request):
    """Проверка статуса авторизации для AJAX запросов"""
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'user': {
                'email': request.user.email,
                'full_name': request.user.full_name
            }
        })
    else:
        return JsonResponse({'authenticated': False})


@login_required
@require_http_methods(["POST"])
def activate_payment(request):
    """Активация тарифа после успешной оплаты через CloudPayments"""
    try:
        print(f"DEBUG: activate_payment called with user {request.user.email}")
        data = json.loads(request.body)
        print(f"DEBUG: Received data: {data}")
        plan_id = data.get('plan_id')
        payment_data = data.get('payment_data', {})
        print(f"DEBUG: Plan ID: {plan_id}, Payment data: {payment_data}")
        
        if not plan_id:
            return JsonResponse({
                'success': False,
                'error': 'Plan ID is required'
            }, status=400)
        
        # Получаем план
        plan = get_object_or_404(Plan, id=plan_id, is_active=True)
        user = request.user
        print(f"DEBUG: Found plan: {plan.title}, User: {user.email}")
        
        # Обрабатываем payment_data - может быть строкой или объектом
        if isinstance(payment_data, str):
            try:
                # Пытаемся распарсить как JSON
                payment_data = json.loads(payment_data)
            except json.JSONDecodeError:
                # Если не JSON, создаем простой объект
                payment_data = {'message': payment_data}
        
        # Получаем transaction_id безопасно
        transaction_id = None
        if isinstance(payment_data, dict):
            transaction_id = (payment_data.get('transactionId') or 
                            payment_data.get('invoiceId') or 
                            payment_data.get('TransactionId') or 
                            payment_data.get('transaction_id') or
                            payment_data.get('id'))
        
        print(f"DEBUG: Extracted transaction_id: {transaction_id}")
        print(f"DEBUG: Payment data: {payment_data}")
        
        if not transaction_id or transaction_id == 'undefined':
            # Если transaction_id нет, создаем временный
            transaction_id = f'cp_{timezone.now().strftime("%Y%m%d_%H%M%S")}'
            print(f"DEBUG: Created temporary transaction_id: {transaction_id}")
        
        # Проверяем, не была ли уже активирована эта транзакция
        existing_purchase = PurchasedPlan.objects.filter(
            transaction_id=transaction_id,
            user=user
        ).first()
        
        if existing_purchase:
            return JsonResponse({
                'success': True,
                'message': f'Тариф "{plan.title}" уже был активирован ранее!',
                'purchased_plan_id': existing_purchase.id
            })
        
        # Создаем запись о купленном тарифе
        print(f"DEBUG: Creating PurchasedPlan...")
        try:
            with transaction.atomic():
                print(f"DEBUG: About to create PurchasedPlan with data:")
                print(f"  - user: {user.id}")
                print(f"  - plan: {plan.id}")
                print(f"  - amount_paid: {plan.get_final_price()}")
                print(f"  - transaction_id: {transaction_id}")
                print(f"  - payment_data: {payment_data}")
                
                purchased_plan = PurchasedPlan.objects.create(
                    user=user,
                    plan=plan,
                    start_date=timezone.now(),
                    end_date=timezone.now() + timedelta(days=30),
                    is_active=True,
                    amount_paid=plan.get_final_price(),
                    payment_method='cloudpayments',
                    transaction_id=transaction_id,
                    cloudpayments_data=payment_data  # Сохраняем данные от CloudPayments
                )
                print(f"DEBUG: PurchasedPlan created successfully!")
                
                # Обновляем текущий план пользователя
                user.current_plan = plan
                user.plan_expiry = purchased_plan.end_date
                user.save()
                
                print(f"DEBUG: PurchasedPlan created with ID: {purchased_plan.id}")
                print(f"DEBUG: User plan updated: {user.current_plan.title}")
                
        except Exception as e:
            print(f"DEBUG: Error creating PurchasedPlan: {e}")
            print(f"DEBUG: Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            raise
        
        return JsonResponse({
            'success': True,
            'message': f'Тариф "{plan.title}" успешно активирован!',
            'purchased_plan_id': purchased_plan.id
        })
        
    except json.JSONDecodeError as e:
        print(f"DEBUG: JSON decode error: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        print(f"DEBUG: Unexpected error in activate_payment: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Не удалось проверить статус транзакции. Пожалуйста, обратитесь в поддержку. Ошибка: {str(e)}'
        }, status=500)
