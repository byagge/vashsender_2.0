# mailer/serializers.py

from rest_framework import serializers
from .models import ContactList, Contact

# Проксирующий сериализатор для доменов из apps.emails
class MailerDomainSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    domain_name = serializers.CharField()
    is_verified = serializers.BooleanField(read_only=True)
    spf_verified = serializers.BooleanField(read_only=True)
    dkim_verified = serializers.BooleanField(read_only=True)
    dkim_dns_record = serializers.CharField(read_only=True)
    dmarc_dns_record = serializers.CharField(read_only=True)

    def create(self, validated_data):
        request = self.context.get('request')
        owner = getattr(request, 'user', None)
        from apps.emails.models import Domain
        domain = Domain.objects.create(owner=owner, domain_name=validated_data['domain_name'])
        # Генерируем DKIM ключи сразу при создании
        try:
            domain.generate_dkim_keys()
        except Exception:
            pass
        return domain

    def to_representation(self, instance):
        # instance — это apps.emails.models.Domain
        data = {
            'id': instance.id,
            'domain_name': instance.domain_name,
            'is_verified': instance.is_verified,
            'spf_verified': instance.spf_verified,
            'dkim_verified': instance.dkim_verified,
            'dkim_dns_record': getattr(instance, 'dkim_dns_record', ''),
            'dmarc_dns_record': getattr(instance, 'dmarc_dns_record', ''),
        }
        return data

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['id', 'email', 'status', 'added_date']
    
    def validate_email(self, value):
        """Валидация email адреса при ручном добавлении"""
        from .utils import is_syntax_valid, is_reserved_domain, is_disposable_domain
        
        # Приводим к нижнему регистру
        email = value.lower().strip()
        
        # Базовая проверка синтаксиса
        syntax_valid = is_syntax_valid(email)
        if not syntax_valid:
            raise serializers.ValidationError('Неверный синтаксис email адреса')
        
        try:
            domain = email.split('@', 1)[1].lower()
        except (ValueError, IndexError) as e:
            raise serializers.ValidationError('Не удалось извлечь домен')
        
        # Проверка зарезервированных доменов
        is_reserved = is_reserved_domain(domain)
        if is_reserved:
            raise serializers.ValidationError('Зарезервированный домен')
        
        # Проверка disposable доменов (предупреждение, но не ошибка)
        is_disposable = is_disposable_domain(domain)
        if is_disposable:
            # Добавляем предупреждение, но не блокируем
            pass
        
        # Возвращаем очищенный email
        return email
    
    def validate(self, data):
        """Дополнительная валидация при ручном добавлении"""
        from .utils import is_disposable_domain
        
        email = data.get('email', '')
        if email:
            try:
                domain = email.split('@', 1)[1].lower()
                
                # Устанавливаем статус на основе проверок
                if is_disposable_domain(domain):
                    data['status'] = Contact.BLACKLIST
                else:
                    data['status'] = Contact.VALID
                    
            except (ValueError, IndexError) as e:
                data['status'] = Contact.INVALID
        else:
            pass
        
        return data

class ContactListSerializer(serializers.ModelSerializer):
    # убираем source=… — DRF найдёт total_contacts, valid_count и т.д. по name
    total_contacts    = serializers.IntegerField(read_only=True)
    valid_count       = serializers.IntegerField(read_only=True)
    invalid_count     = serializers.IntegerField(read_only=True)
    blacklisted_count = serializers.IntegerField(read_only=True)
    contacts          = ContactSerializer(many=True, read_only=True)

    class Meta:
        model = ContactList
        fields = [
            'id', 'name', 'created_at', 'updated_at',
            'total_contacts', 'valid_count', 'invalid_count', 'blacklisted_count',
            'contacts',
        ]

class ContactListListSerializer(serializers.ModelSerializer):
    total_contacts    = serializers.IntegerField(read_only=True)
    valid_count       = serializers.IntegerField(read_only=True)
    invalid_count     = serializers.IntegerField(read_only=True)
    blacklisted_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContactList
        fields = [
            'id', 'name', 'created_at', 'updated_at',
            'total_contacts', 'valid_count', 'invalid_count', 'blacklisted_count',
        ]

class ContactListDetailSerializer(ContactListListSerializer):
    contacts = ContactSerializer(many=True, read_only=True)

    class Meta(ContactListListSerializer.Meta):
        fields = ContactListListSerializer.Meta.fields + ['contacts']
