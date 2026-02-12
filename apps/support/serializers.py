from rest_framework import serializers
from .models import SupportTicket, SupportMessage, SupportAttachment, SupportChat, SupportChatMessage
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

class SupportTicketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            'ticket_id', 'ticket_subject', 'ticket_description', 'ticket_status', 'ticket_priority',
            'ticket_category', 'ticket_user', 'ticket_assigned_to',
            'ticket_created_at', 'ticket_updated_at', 'ticket_resolved_at', 'ticket_closed_at'
        ]

class SupportTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['ticket_subject', 'ticket_description', 'ticket_category', 'ticket_priority']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['ticket_user'] = request.user
        ticket = super().create(validated_data)
        # Создаём первое сообщение с текстом описания тикета
        SupportMessage.objects.create(
            message_ticket=ticket,
            message_author=request.user,
            message_text=ticket.ticket_description
        )
        try:
            # Уведомление в поддержку о новом тикете
            support_email = getattr(settings, 'SUPPORT_NOTIFICATIONS_EMAIL', 'support@vashsender.ru')
            subject = f"[Support] Новый тикет от {request.user.email}: {ticket.ticket_subject}"
            text_body = (
                f"Пользователь: {request.user.email}\n"
                f"Тема: {ticket.ticket_subject}\n\n"
                f"Описание:\n{ticket.ticket_description}\n\n"
                f"ID тикета: {ticket.ticket_id}\n"
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
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@regvshsndr.ru'),
                    to=[support_email]
                )
                msg.send(fail_silently=not getattr(settings, 'EMAIL_DEBUG', False))
        except Exception:
            # Безопасно игнорируем сбои уведомлений, чтобы не мешать созданию тикета
            pass
        return ticket

class SupportTicketDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            'ticket_id', 'ticket_subject', 'ticket_description', 'ticket_status', 'ticket_priority',
            'ticket_category', 'ticket_user', 'ticket_assigned_to',
            'ticket_created_at', 'ticket_updated_at', 'ticket_resolved_at', 'ticket_closed_at'
        ]

class SupportMessageSerializer(serializers.ModelSerializer):
    attachment_url = serializers.SerializerMethodField()
    class Meta:
        model = SupportMessage
        fields = [
            'message_id', 'message_text', 'message_author', 'message_internal', 'message_staff_reply',
            'message_created_at', 'message_updated_at', 'attachment_url'
        ]
    def get_attachment_url(self, obj):
        attachment = obj.message_attachments.first()
        if attachment and attachment.attachment_file:
            return attachment.attachment_file.url
        return None

class SupportMessageCreateSerializer(serializers.ModelSerializer):
    attachment = serializers.FileField(required=False, write_only=True)
    class Meta:
        model = SupportMessage
        fields = ['message_text', 'message_internal', 'attachment']

    def create(self, validated_data):
        request = self.context.get('request')
        attachment_file = validated_data.pop('attachment', None)
        if request and hasattr(request, 'user'):
            validated_data['message_author'] = request.user
        message = super().create(validated_data)
        if attachment_file:
            SupportAttachment = self.Meta.model._meta.apps.get_model('support', 'SupportAttachment')
            SupportAttachment.objects.create(
                attachment_message=message,
                attachment_ticket=message.message_ticket,
                attachment_file=attachment_file,
                attachment_filename=attachment_file.name,
                attachment_file_size=attachment_file.size,
                attachment_mime_type=attachment_file.content_type
            )
        try:
            # Уведомление в поддержку о новом сообщении в тикете
            support_email = getattr(settings, 'SUPPORT_NOTIFICATIONS_EMAIL', 'support@vashsender.ru')
            subject = f"[Support] Новое сообщение в тикете {message.message_ticket.ticket_id.hex[:8]} от {message.message_author.email}"
            text_body = (
                f"Тикет: {message.message_ticket.ticket_subject}\n"
                f"Автор: {message.message_author.email}\n\n"
                f"Сообщение:\n{message.message_text}\n\n"
                f"ID тикета: {message.message_ticket.ticket_id}\n"
                f"ID сообщения: {message.message_id}\n"
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
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@regvshsndr.ru'),
                    to=[support_email]
                )
                msg.send(fail_silently=not getattr(settings, 'EMAIL_DEBUG', False))
        except Exception:
            pass
        return message 

class SupportChatSerializer(serializers.ModelSerializer):
    chat_user = serializers.ReadOnlyField(source='chat_user.email')
    chat_assigned_to = serializers.ReadOnlyField(source='chat_assigned_to.email')
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SupportChat
        fields = [
            'chat_id', 'chat_user', 'chat_status', 'chat_created_at', 
            'chat_updated_at', 'chat_assigned_to', 'last_message', 'unread_count'
        ]
    
    def get_last_message(self, obj):
        last_msg = obj.chat_messages.last()
        if last_msg:
            text = last_msg.message_text[:100]
            if len(last_msg.message_text) > 100:
                text += '...'
            return text
        return None
    
    def get_unread_count(self, obj):
        try:
            user = self.context['request'].user
            if user.is_staff:
                # Для сотрудников считаем сообщения от пользователей
                return obj.chat_messages.filter(message_staff_reply=False).count()
            else:
                # Для пользователей считаем сообщения от сотрудников
                return obj.chat_messages.filter(message_staff_reply=True).count()
        except:
            return 0


class SupportChatMessageSerializer(serializers.ModelSerializer):
    message_author = serializers.ReadOnlyField(source='message_author.email')
    message_author_name = serializers.SerializerMethodField()
    
    class Meta:
        model = SupportChatMessage
        fields = [
            'message_id', 'message_author', 'message_author_name',
            'message_text', 'message_staff_reply', 'message_created_at'
        ]
    
    def get_message_author_name(self, obj):
        if obj.message_author.is_staff:
            return "Поддержка"
        return obj.message_author.email


class SupportChatMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportChatMessage
        fields = ['message_text'] 