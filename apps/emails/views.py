# core/apps/emails/views.py

from django.conf import settings
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from rest_framework import viewsets, status
from rest_framework.decorators import action
from django.db import IntegrityError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

import uuid
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import SenderEmail, Domain
from .serializers import SenderEmailSerializer

import uuid
import dns.resolver

from .models import Domain, SenderEmail
from .serializers import DomainSerializer, SenderEmailSerializer
from .utils import has_spf, has_dkim, has_dmarc, validate_spf_record

class DomainViewSet(viewsets.ModelViewSet):
    serializer_class   = DomainSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Domain.objects.filter(owner=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                self.perform_create(serializer)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        try:
            token = uuid.uuid4().hex
            domain = serializer.save(owner=self.request.user, verification_token=token)
            
            # Пытаемся сгенерировать DKIM ключи асинхронно
            try:
                print(f"Attempting to generate DKIM keys for domain: {domain.domain_name}")
                domain.generate_dkim_keys()
                # Обновляем объект из базы данных
                domain.refresh_from_db()
                print(f"Domain {domain.domain_name} after DKIM generation - public_key: {bool(domain.public_key)}")
            except Exception as e:
                print(f"DKIM generation failed for {domain.domain_name}: {e}")
                # Не прерываем создание домена из-за ошибки DKIM
                
        except IntegrityError:
            domain_name = serializer.validated_data.get('domain_name', '')
            raise ValidationError({
                'domain_name': f'Домен {domain_name} уже добавлен в ваш аккаунт.'
            })
        except Exception as e:
            print(f"Unexpected error creating domain: {e}")
            raise ValidationError({
                'non_field_errors': 'Произошла ошибка при создании домена. Попробуйте еще раз.'
            })

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        domain = self.get_object()
        
        # SPF проверка с использованием утилиты
        spf_ok = has_spf(domain.domain_name)
        
        # DKIM проверка с использованием утилиты
        from django.conf import settings as dj_settings
        dkim_ok = has_dkim(domain.domain_name, selector=getattr(dj_settings, 'DKIM_SELECTOR', 'vashsender'))
        
        # DMARC проверка с использованием утилиты
        dmarc_ok = has_dmarc(domain.domain_name)
        
        print(f"Domain {domain.domain_name}: SPF={spf_ok}, DKIM={dkim_ok}, DMARC={dmarc_ok}")  # Отладка
        
        domain.spf_verified = spf_ok
        domain.dkim_verified = dkim_ok
        domain.is_verified = spf_ok and dkim_ok and dmarc_ok
        domain.save(update_fields=['spf_verified', 'dkim_verified', 'is_verified'])
        
        return Response(DomainSerializer(domain).data)

    @action(detail=True, methods=['post'], url_path='verify-manual')
    def verify_manual(self, request, pk=None):
        """Ручная верификация домена (для тестирования)"""
        domain = self.get_object()
        
        # Для тестирования помечаем домен как верифицированный
        domain.spf_verified = True
        domain.dkim_verified = True
        domain.is_verified = True
        domain.save(update_fields=['spf_verified', 'dkim_verified', 'is_verified'])
        
        return Response({
            'message': f'Домен {domain.domain_name} помечен как верифицированный',
            'domain': DomainSerializer(domain).data
        })

    @action(detail=True, methods=['post'], url_path='generate-dkim')
    def generate_dkim(self, request, pk=None):
        """Генерирует DKIM ключи для домена"""
        domain = self.get_object()
        
        if domain.generate_dkim_keys():
            return Response({
                'message': 'DKIM ключи успешно сгенерированы',
                'dns_record': domain.dkim_dns_record
            })
        else:
            return Response({
                'error': 'Не удалось сгенерировать DKIM ключи'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='regenerate-dkim')
    def regenerate_dkim(self, request, pk=None):
        """Перегенерирует DKIM ключи для домена"""
        domain = self.get_object()
        
        # Очищаем старые ключи
        domain.public_key = ""
        domain.private_key_path = ""
        domain.save(update_fields=['public_key', 'private_key_path'])
        
        # Генерируем новые
        if domain.generate_dkim_keys():
            return Response({
                'message': 'DKIM ключи успешно перегенерированы',
                'dns_record': domain.dkim_dns_record
            })
        else:
            return Response({
                'error': 'Не удалось перегенерировать DKIM ключи'
            }, status=status.HTTP_400_BAD_REQUEST)


class SenderEmailViewSet(viewsets.ModelViewSet):
    """
    Создаём отправителя (sender email) со следующей логикой:
     - из email вытягиваем домен
     - проверяем, что Domain с таким name есть у пользователя
     - если нет — 400 с подсказкой добавить домен
     - если есть, но не подтверждён — 400 с подсказкой подтвердить домен
     - иначе создаём запись SenderEmail, генерируем токен и шлём письмо-подтверждение
    """
    serializer_class = SenderEmailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Возвращаем все email'ы пользователя
        return SenderEmail.objects.filter(
            owner=self.request.user
        ).select_related('domain')

    @action(detail=False, methods=['get'], url_path='verified')
    def verified(self, request):
        """
        GET /emails/api/emails/verified/
        Возвращает только подтвержденные email'ы для использования в кампаниях
        """
        # Получаем только подтвержденные
        verified_emails = SenderEmail.objects.filter(
            owner=request.user,
            is_verified=True
        ).select_related('domain')
        
        # Сериализуем и возвращаем результат
        serializer = self.get_serializer(verified_emails, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        print(f"Creating email with data: {request.data}")
        email_addr = request.data.get('email', '').strip().lower()
        if '@' not in email_addr:
            print(f"Invalid email format: {email_addr}")
            return Response({'email': 'Неверный формат email.'},
                            status=status.HTTP_400_BAD_REQUEST)

        domain_part = email_addr.split('@', 1)[1]
        print(f"Domain part: {domain_part}")
        
        # 1) Домен должен существовать и принадлежать текущему пользователю
        try:
            domain_obj = Domain.objects.get(owner=request.user,
                                            domain_name=domain_part)
            print(f"Domain found: {domain_obj.domain_name}, verified: {domain_obj.is_verified}")
        except Domain.DoesNotExist:
            print(f"Domain not found: {domain_part}")
            return Response(
                {'detail': f'Домен {domain_part} не найден. Сначала добавьте и подтвердите домен.'},
                status=status.HTTP_400_BAD_REQUEST)

        # 2) Домен должен быть верифицирован
        if not domain_obj.is_verified:
            print(f"Domain not verified: {domain_obj.domain_name}")
            return Response(
                {'detail': f'Домен {domain_part} ещё не подтверждён. Перейдите в раздел «Домены» и завершите верификацию.'},
                status=status.HTTP_400_BAD_REQUEST)

        # 3) Всё ок — создаём отправителя и шлём письмо
        try:
            token = uuid.uuid4().hex
            sender = SenderEmail.objects.create(
                owner=request.user,
                email=email_addr,
                domain=domain_obj,
                verification_token=token
            )
            print(f"Email created successfully: {sender.email}")

            # Отправляем письмо-подтверждение
            confirm_url = request.build_absolute_uri(
                f"/emails/confirm-sender/?token={token}"
            )
            # Use shared SMTP pool to match campaigns delivery behavior
            try:
                from apps.emails.tasks import send_plain_notification_sync, send_plain_notification
                sent_ok = False
                try:
                    send_plain_notification_sync(
                        to_email=email_addr,
                        subject="Подтверждение отправителя",
                        plain_text=f"Пожалуйста, подтвердите ваш адрес: {confirm_url}"
                    )
                    sent_ok = True
                except Exception:
                    from django.core.mail import EmailMultiAlternatives
                    msg = EmailMultiAlternatives(
                        subject="Подтверждение отправителя",
                        body=f"Пожалуйста, подтвердите ваш адрес: {confirm_url}",
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@vashsender.ru'),
                        to=[email_addr]
                    )
                    try:
                        msg.send(fail_silently=False)
                        sent_ok = True
                    except Exception:
                        pass
                if not sent_ok:
                    try:
                        send_plain_notification.apply_async(args=[email_addr, "Подтверждение отправителя", f"Пожалуйста, подтвердите ваш адрес: {confirm_url}"], queue='email')
                    except Exception:
                        pass
            except Exception:
                pass

            return Response(
                SenderEmailSerializer(sender).data,
                status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            print(f"Email already exists: {email_addr}")
            return Response(
                {"detail": "Этот email уже добавлен."},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def resend(self, request, pk=None):
        """
        POST /emails/api/emails/{pk}/resend/
        Повторно шлёт письмо-подтверждение, если ещё не верифицировано.
        """
        sender = self.get_object()

        if sender.is_verified:
            return Response(
                {"detail": "Этот email уже подтверждён."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Собираем ссылку подтверждения
        confirm_url = request.build_absolute_uri(
            f"/emails/confirm-sender/?token={sender.verification_token}"
        )

        # Единый путь отправки: синхронно → фолбэк → Celery if needed
        try:
            from apps.emails.tasks import send_plain_notification_sync, send_plain_notification
            sent_ok = False
            try:
                send_plain_notification_sync(
                    to_email=sender.email,
                    subject="Подтверждение отправителя (повторное)",
                    plain_text=f"Пожалуйста, подтвердите ваш адрес по ссылке:\n\n{confirm_url}",
                )
                sent_ok = True
            except Exception:
                from django.core.mail import EmailMultiAlternatives
                msg = EmailMultiAlternatives(
                    subject="Подтверждение отправителя (повторное)",
                    body=f"Пожалуйста, подтвердите ваш адрес по ссылке:\n\n{confirm_url}",
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@vashsender.ru'),
                    to=[sender.email]
                )
                try:
                    msg.send(fail_silently=False)
                    sent_ok = True
                except Exception:
                    pass
            if not sent_ok:
                try:
                    send_plain_notification.apply_async(args=[sender.email, "Подтверждение отправителя (повторное)", f"Пожалуйста, подтвердите ваш адрес по ссылке:\n\n{confirm_url}"], queue='email')
                except Exception:
                    pass
        except Exception:
            pass

        return Response({"detail": "Письмо с подтверждением отправлено повторно."})

from django.shortcuts import redirect, get_object_or_404
from django.views import View

class SenderConfirmView(View):
    def get(self, request):
        token = request.GET.get('token')
        sender = get_object_or_404(SenderEmail, verification_token=token)
        sender.is_verified = True
        sender.verified_at = timezone.now()
        sender.save(update_fields=['is_verified','verified_at'])
        # после подтверждения можно редиректить на SPA с параметром ?confirmed=yes
        return redirect(f"/emails/?confirmed=1")

class EmailPlatformSpaView(LoginRequiredMixin, TemplateView):
    """
    Единая SPA-страница, где через Alpine.js переключаются 
    табы Emails ↔ Domains
    """
    template_name = 'domains.html'
