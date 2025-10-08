from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

from .models import SupportTicket, SupportMessage, SupportCategory, SupportChat, SupportChatMessage
from .serializers import (
    SupportTicketListSerializer, SupportTicketCreateSerializer, SupportTicketDetailSerializer,
    SupportMessageSerializer, SupportMessageCreateSerializer, SupportChatSerializer, SupportChatMessageSerializer,
    SupportChatMessageCreateSerializer
)


# Удалён класс SupportCategoryViewSet


class SupportTicketViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketListSerializer
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SupportTicket.objects.all()
        else:
            return SupportTicket.objects.filter(ticket_user=user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SupportTicketCreateSerializer
        elif self.action in ['retrieve']:
            return SupportTicketDetailSerializer
        return SupportTicketListSerializer
    
    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        ticket = self.get_object()
        if request.method == 'GET':
            messages = SupportMessage.objects.filter(message_ticket=ticket)
            serializer = SupportMessageSerializer(messages, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = SupportMessageCreateSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save(message_ticket=ticket, message_author=request.user)
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)
    
    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        ticket = self.get_object()
        
        if ticket.ticket_status == SupportTicket.STATUS_CLOSED:
            return Response(
                {'error': 'Тикет закрыт и не принимает ответы'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        if not user.is_staff and ticket.ticket_user != user:
            return Response(
                {'error': 'Нет прав для ответа на этот тикет'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SupportMessageCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(message_ticket=ticket)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        if not request.user.is_staff:
            return Response(
                {'error': 'Только сотрудники могут закрывать тикеты'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        ticket = self.get_object()
        ticket.ticket_status = SupportTicket.STATUS_CLOSED
        ticket.ticket_closed_at = timezone.now()
        ticket.save(update_fields=['ticket_status', 'ticket_closed_at'])
        
        return Response({'status': 'Тикет закрыт'})
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        if not request.user.is_staff:
            return Response(
                {'error': 'Только сотрудники могут решать тикеты'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        ticket = self.get_object()
        ticket.ticket_status = SupportTicket.STATUS_RESOLVED
        ticket.ticket_resolved_at = timezone.now()
        ticket.save(update_fields=['ticket_status', 'ticket_resolved_at'])
        
        return Response({'status': 'Тикет решён'})
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        if not request.user.is_staff:
            return Response(
                {'error': 'Только сотрудники могут назначать тикеты'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        ticket = self.get_object()
        assigned_to_id = request.data.get('assigned_to')
        
        if not assigned_to_id:
            return Response(
                {'error': 'Не указан сотрудник для назначения'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            assigned_user = User.objects.get(id=assigned_to_id, is_staff=True)
            ticket.ticket_assigned_to = assigned_user
            ticket.save(update_fields=['ticket_assigned_to'])
            return Response({'status': f'Тикет назначен {assigned_user.email}'})
        except User.DoesNotExist:
            return Response(
                {'error': 'Сотрудник не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def my_tickets(self, request):
        if request.user.is_staff:
            tickets = SupportTicket.objects.filter(ticket_assigned_to=request.user)
        else:
            tickets = SupportTicket.objects.filter(ticket_user=request.user)
        
        serializer = SupportTicketListSerializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        if not request.user.is_staff:
            return Response(
                {'error': 'Только сотрудники могут просматривать статистику'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        total_tickets = SupportTicket.objects.count()
        open_tickets = SupportTicket.objects.filter(ticket_status=SupportTicket.STATUS_OPEN).count()
        in_progress_tickets = SupportTicket.objects.filter(ticket_status=SupportTicket.STATUS_IN_PROGRESS).count()
        waiting_tickets = SupportTicket.objects.filter(ticket_status=SupportTicket.STATUS_WAITING).count()
        resolved_tickets = SupportTicket.objects.filter(ticket_status=SupportTicket.STATUS_RESOLVED).count()
        closed_tickets = SupportTicket.objects.filter(ticket_status=SupportTicket.STATUS_CLOSED).count()
        
        urgent_tickets = SupportTicket.objects.filter(ticket_priority=SupportTicket.PRIORITY_URGENT).count()
        high_tickets = SupportTicket.objects.filter(ticket_priority=SupportTicket.PRIORITY_HIGH).count()
        
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        new_tickets_30d = SupportTicket.objects.filter(ticket_created_at__gte=thirty_days_ago).count()
        resolved_tickets_30d = SupportTicket.objects.filter(ticket_resolved_at__gte=thirty_days_ago).count()
        
        return Response({
            'total': total_tickets,
            'open': open_tickets,
            'in_progress': in_progress_tickets,
            'waiting': waiting_tickets,
            'resolved': resolved_tickets,
            'closed': closed_tickets,
            'urgent': urgent_tickets,
            'high': high_tickets,
            'new_30d': new_tickets_30d,
            'resolved_30d': resolved_tickets_30d,
        })


class SupportMessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportMessageSerializer
    
    def get_queryset(self):
        ticket_id = self.kwargs.get('ticket_pk')
        ticket = get_object_or_404(SupportTicket, ticket_id=ticket_id)
        return SupportMessage.objects.filter(message_ticket=ticket)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SupportMessageCreateSerializer
        return SupportMessageSerializer

    def perform_create(self, serializer):
        ticket_id = self.kwargs.get('ticket_pk')
        ticket = get_object_or_404(SupportTicket, ticket_id=ticket_id)
        serializer.save(message_ticket=ticket, message_author=self.request.user)

    def create(self, request, *args, **kwargs):
        """
        Явная реализация create для поддержки POST /support/api/tickets/<ticket_id>/messages/
        """
        return super().create(request, *args, **kwargs)


class SupportTicketListView(LoginRequiredMixin, TemplateView):
    template_name = 'support/tickets.html' 


class SupportAdminPanelView(LoginRequiredMixin, TemplateView):
    template_name = 'support/admin_panel.html'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs) 


class SupportChatViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportChatSerializer
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SupportChat.objects.all().order_by('-chat_updated_at')
        else:
            return SupportChat.objects.filter(chat_user=user).order_by('-chat_updated_at')
    
    @action(detail=False, methods=['post'])
    def start_chat(self, request):
        """Создать новый чат"""
        user = request.user
        
        # Проверяем, есть ли уже активный чат у пользователя
        existing_chat = SupportChat.objects.filter(
            chat_user=user,
            chat_status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS, SupportTicket.STATUS_WAITING, SupportTicket.STATUS_RESOLVED]
        ).first()
        
        if existing_chat and existing_chat.chat_status != SupportTicket.STATUS_CLOSED:
            return Response({
                'chat_id': existing_chat.chat_id,
                'message': 'У вас уже есть активный чат'
            })
        
        # Создаем новый чат
        chat = SupportChat.objects.create(chat_user=user)
        
        # Если есть сообщение в запросе, создаем первое сообщение
        message_text = request.data.get('message', '')
        if message_text:
            SupportChatMessage.objects.create(
                chat_message=chat,
                message_author=user,
                message_text=message_text,
                message_staff_reply=user.is_staff
            )
            
            # Обновляем время последнего обновления чата
            chat.chat_updated_at = timezone.now()
            chat.save(update_fields=['chat_updated_at'])

            # Уведомление поддержки о новом чате/сообщении
            try:
                support_email = getattr(settings, 'SUPPORT_NOTIFICATIONS_EMAIL', 'support@vashsender.ru')
                subject = f"[Support Chat] Новое сообщение от {user.email}"
                text_body = (
                    f"Пользователь: {user.email}\n"
                    f"Чат: {chat.chat_id}\n\n"
                    f"Сообщение:\n{message_text}\n"
                )
                try:
                    from apps.emails.tasks import send_plain_notification_sync
                    send_plain_notification_sync(
                        to_email=support_email,
                        subject=subject,
                        plain_text=text_body,
                    )
                except Exception:
                    msg = EmailMultiAlternatives(
                        subject=subject,
                        body=text_body,
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@vashsender.ru'),
                        to=[support_email]
                    )
                    msg.send(fail_silently=not getattr(settings, 'EMAIL_DEBUG', False))
            except Exception:
                pass
        
        return Response({
            'chat_id': chat.chat_id,
            'message': 'Чат создан'
        }, status=201)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Получить сообщения чата"""
        chat = self.get_object()
        messages = SupportChatMessage.objects.filter(chat_message=chat).order_by('message_created_at')
        serializer = SupportChatMessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Отправить сообщение в чат"""
        chat = self.get_object()
        
        if chat.chat_status == SupportTicket.STATUS_CLOSED:
            return Response(
                {'error': 'Чат закрыт'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        message_text = request.data.get('message_text', '')
        if not message_text:
            return Response(
                {'error': 'Текст сообщения обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Определяем, является ли сообщение ответом сотрудника
        is_staff_reply = request.user.is_staff
        
        message = SupportChatMessage.objects.create(
            chat_message=chat,
            message_author=request.user,
            message_text=message_text,
            message_staff_reply=is_staff_reply
        )
        
        # Обновляем время последнего обновления чата
        chat.chat_updated_at = timezone.now()
        chat.save(update_fields=['chat_updated_at'])
        
        # Уведомление поддержки о новом сообщении в чате
        try:
                support_email = getattr(settings, 'SUPPORT_NOTIFICATIONS_EMAIL', 'support@vashsender.ru')
                subject = f"[Support Chat] Новое сообщение в чате {chat.chat_id.hex[:8]} от {request.user.email}"
                text_body = (
                    f"Пользователь: {request.user.email}\n"
                    f"Чат: {chat.chat_id}\n\n"
                    f"Сообщение:\n{message_text}\n"
                )
                try:
                    from apps.emails.tasks import send_plain_notification_sync
                    send_plain_notification_sync(
                        to_email=support_email,
                        subject=subject,
                        plain_text=text_body,
                    )
                except Exception:
                    msg = EmailMultiAlternatives(
                        subject=subject,
                        body=text_body,
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@vashsender.ru'),
                        to=[support_email]
                    )
                    msg.send(fail_silently=not getattr(settings, 'EMAIL_DEBUG', False))
        except Exception:
            pass

        serializer = SupportChatMessageSerializer(message)
        return Response(serializer.data, status=201)
    
    @action(detail=True, methods=['post'])
    def close_chat(self, request, pk=None):
        """Закрыть чат"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Только сотрудники могут закрывать чаты'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        chat = self.get_object()
        chat.chat_status = SupportTicket.STATUS_CLOSED
        chat.chat_updated_at = timezone.now()
        chat.save(update_fields=['chat_status', 'chat_updated_at'])
        return Response({'status': 'Чат закрыт'})
    
    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        """Изменить статус чата"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Только сотрудники могут изменять статус чатов'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        chat = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'error': 'Статус обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем, что статус валидный
        valid_statuses = [choice[0] for choice in SupportTicket.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Неверный статус. Допустимые значения: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        chat.chat_status = new_status
        chat.chat_updated_at = timezone.now()
        chat.save(update_fields=['chat_status', 'chat_updated_at'])
        
        return Response({
            'status': 'Статус изменён',
            'new_status': new_status,
            'chat_id': chat.chat_id
        })


class SupportChatMessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportChatMessageSerializer
    
    def get_queryset(self):
        chat_id = self.kwargs.get('chat_pk')
        chat = get_object_or_404(SupportChat, chat_id=chat_id)
        return SupportChatMessage.objects.filter(chat_message=chat).order_by('message_created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SupportChatMessageCreateSerializer
        return SupportChatMessageSerializer
    
    def perform_create(self, serializer):
        chat_id = self.kwargs.get('chat_pk')
        chat = get_object_or_404(SupportChat, chat_id=chat_id)
        
        # Определяем, является ли сообщение ответом сотрудника
        is_staff_reply = self.request.user.is_staff
        
        serializer.save(
            chat_message=chat, 
            message_author=self.request.user,
            message_staff_reply=is_staff_reply
        )
        
        # Обновляем время последнего обновления чата
        chat.chat_updated_at = timezone.now()
        chat.save(update_fields=['chat_updated_at'])


class SupportChatView(LoginRequiredMixin, TemplateView):
    template_name = 'support/chat.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Получаем активный чат пользователя
        user = self.request.user
        active_chat = SupportChat.objects.filter(
            chat_user=user,
            chat_status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS, SupportTicket.STATUS_WAITING, SupportTicket.STATUS_RESOLVED]
        ).first()
        context['active_chat'] = active_chat
        return context 