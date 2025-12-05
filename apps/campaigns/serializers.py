# apps/campaigns/serializers.py

from rest_framework import serializers
from apps.mailer.models import Contact, ContactList
from apps.emails.models import SenderEmail
from apps.mail_templates.models import EmailTemplate
from apps.campaigns.models import Campaign, CampaignStats, EmailTracking, CampaignRecipient
from apps.campaigns.models import Campaign as CampaignModel

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        # В модели Contact есть поля email, status, added_date и связь со списком
        fields = ['id', 'email', 'status', 'added_date', 'contact_list']
        read_only_fields = ['id', 'added_date', 'contact_list']

class ContactListSerializer(serializers.ModelSerializer):
    contacts_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ContactList
        fields = ['id', 'name', 'contacts_count', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_contacts_count(self, obj):
        return obj.contacts.count()

class SenderEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SenderEmail
        fields = ['id', 'email', 'sender_name', 'reply_to', 'is_verified', 'created_at']

class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ['id', 'title', 'html_content', 'plain_text_content']

class CampaignStatsSerializer(serializers.ModelSerializer):
    contact_list = ContactListSerializer(read_only=True)
    
    class Meta:
        model = CampaignStats
        fields = ['id', 'contact_list', 'emails_sent', 'opens_count', 'clicks_count', 'bounces_count', 'created_at', 'updated_at']

class CampaignRecipientSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(read_only=True)
    
    class Meta:
        model = CampaignRecipient
        fields = ['id', 'contact', 'is_sent', 'sent_at', 'created_at']

class CampaignSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.email')
    template = serializers.PrimaryKeyRelatedField(queryset=EmailTemplate.objects.all(), required=False, allow_null=True)
    sender_email = serializers.PrimaryKeyRelatedField(queryset=SenderEmail.objects.all(), required=False, allow_null=True)
    sender_email_detail = SenderEmailSerializer(source='sender_email', read_only=True)
    contact_lists = serializers.PrimaryKeyRelatedField(queryset=ContactList.objects.all(), many=True, required=False)
    contact_lists_detail = serializers.SerializerMethodField()
    template_detail = EmailTemplateSerializer(source='template', read_only=True)
    recipients = ContactSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    emails_sent = serializers.ReadOnlyField()
    delivered_emails = serializers.ReadOnlyField()
    open_rate = serializers.ReadOnlyField()
    click_rate = serializers.ReadOnlyField()
    bounce_rate = serializers.ReadOnlyField()
    opens_count = serializers.SerializerMethodField()
    clicks_count = serializers.SerializerMethodField()
    unsubscribed_count = serializers.SerializerMethodField()
    delivery_rate = serializers.ReadOnlyField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'user', 'name', 'subject', 'content', 'status', 'status_display',
            'created_at', 'updated_at', 'scheduled_at', 'sent_at',
            'template', 'template_detail', 'sender_email', 'sender_email_detail', 'contact_lists', 'contact_lists_detail', 'recipients',
            'emails_sent', 'delivered_emails', 'open_rate', 'click_rate', 'bounce_rate', 'delivery_rate', 'celery_task_id', 'sender_name', 'failure_reason',
            'opens_count', 'clicks_count', 'unsubscribed_count'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'sent_at']

    def get_contact_lists_detail(self, obj):
        obj.refresh_from_db()
        return [
            {
                'id': str(cl.id),
                'name': cl.name,
                'contacts_count': cl.contacts.count(),
                'valid_contacts_count': cl.contacts.filter(status=Contact.VALID).count()
            }
            for cl in obj.contact_lists.all()
        ]

    def get_emails_sent(self, obj):
        return EmailTracking.objects.filter(campaign=obj).count()

    def get_delivered_emails(self, obj):
        return EmailTracking.objects.filter(campaign=obj, delivered_at__isnull=False).count()

    def get_open_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        total_opens = EmailTracking.objects.filter(campaign=obj, opened_at__isnull=False).count()
        return (total_opens / total_sent * 100)

    def get_click_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        total_clicks = EmailTracking.objects.filter(campaign=obj, clicked_at__isnull=False).count()
        return (total_clicks / total_sent * 100)

    def get_bounce_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        total_bounces = EmailTracking.objects.filter(campaign=obj, bounced_at__isnull=False).count()
        return (total_bounces / total_sent * 100)

    def get_delivery_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        delivered = self.get_delivered_emails(obj)
        return (delivered / total_sent * 100)

    def get_opens_count(self, obj):
        return EmailTracking.objects.filter(campaign=obj, opened_at__isnull=False).count()

    def get_clicks_count(self, obj):
        return EmailTracking.objects.filter(campaign=obj, clicked_at__isnull=False).count()

    def get_unsubscribed_count(self, obj):
        # Количество контактов, ушедших в blacklist среди получивших эту кампанию
        from apps.mailer.models import Contact as MailerContact
        contact_ids = EmailTracking.objects.filter(campaign=obj).values_list('contact_id', flat=True)
        return MailerContact.objects.filter(id__in=contact_ids, status=getattr(MailerContact, 'UNSUBSCRIBED', getattr(MailerContact, 'BLACKLIST', 'blacklist'))).count()

class CampaignListSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.email')
    sender_email_detail = SenderEmailSerializer(source='sender_email', read_only=True)
    contact_lists_detail = serializers.SerializerMethodField()
    template_detail = EmailTemplateSerializer(source='template', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    opens_count = serializers.SerializerMethodField()
    clicks_count = serializers.SerializerMethodField()
    unsubscribed_count = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'user', 'name', 'subject', 'content', 'status', 'status_display',
            'created_at', 'sent_at', 'scheduled_at',
            'sender_email', 'sender_email_detail', 'contact_lists', 'contact_lists_detail',
            'template', 'template_detail', 'emails_sent', 'delivered_emails', 'open_rate', 'click_rate', 'bounce_rate', 'delivery_rate', 'sender_name', 'failure_reason',
            'opens_count', 'clicks_count', 'unsubscribed_count'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'sent_at']

    def get_contact_lists_detail(self, obj):
        obj.refresh_from_db()
        return [
            {
                'id': str(cl.id),
                'name': cl.name,
                'contacts_count': cl.contacts.count(),
                'valid_contacts_count': cl.contacts.filter(status=Contact.VALID).count()
            }
            for cl in obj.contact_lists.all()
        ]

    def get_emails_sent(self, obj):
        return EmailTracking.objects.filter(campaign=obj).count()

    def get_delivered_emails(self, obj):
        return EmailTracking.objects.filter(campaign=obj, delivered_at__isnull=False).count()

    def get_open_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        total_opens = EmailTracking.objects.filter(campaign=obj, opened_at__isnull=False).count()
        return (total_opens / total_sent * 100)

    def get_click_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        total_clicks = EmailTracking.objects.filter(campaign=obj, clicked_at__isnull=False).count()
        return (total_clicks / total_sent * 100)

    def get_bounce_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        total_bounces = EmailTracking.objects.filter(campaign=obj, bounced_at__isnull=False).count()
        return (total_bounces / total_sent * 100)

    def get_delivery_rate(self, obj):
        total_sent = self.get_emails_sent(obj)
        if total_sent == 0:
            return 0
        delivered = self.get_delivered_emails(obj)
        return (delivered / total_sent * 100)

    def get_opens_count(self, obj):
        return EmailTracking.objects.filter(campaign=obj, opened_at__isnull=False).count()

    def get_clicks_count(self, obj):
        return EmailTracking.objects.filter(campaign=obj, clicked_at__isnull=False).count()

    def get_unsubscribed_count(self, obj):
        from apps.mailer.models import Contact as MailerContact
        contact_ids = EmailTracking.objects.filter(campaign=obj).values_list('contact_id', flat=True)
        return MailerContact.objects.filter(id__in=contact_ids, status=getattr(MailerContact, 'UNSUBSCRIBED', getattr(MailerContact, 'BLACKLIST', 'blacklist'))).count()
