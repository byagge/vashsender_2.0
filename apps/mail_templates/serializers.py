# core/apps/mail_templates/serializers.py

from rest_framework import serializers
from .models import EmailTemplate, TemplateImage


class EmailTemplateListSerializer(serializers.ModelSerializer):
    """Облегченный сериализатор для списка шаблонов (без полного контента)"""
    content_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailTemplate
        fields = [
            'id', 'title', 'content_preview', 'is_draft', 
            'send_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'send_count', 'created_at', 'updated_at']
    
    def get_content_preview(self, obj):
        """Возвращает первые 150 символов контента для превью"""
        if obj.html_content:
            # Удаляем HTML-теги и берем первые 150 символов
            import re
            text = re.sub(r'<[^>]+>', '', obj.html_content)
            return text[:150] + '...' if len(text) > 150 else text
        return ''


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            'id', 'title', 'html_content', 'ck_content', 
            'plain_text_content', 'is_draft', 'send_count', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'send_count', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().update(instance, validated_data)


class TemplateImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    dimensions = serializers.SerializerMethodField()
    
    class Meta:
        model = TemplateImage
        fields = [
            'id', 'image', 'filename', 'file_size', 'file_size_mb',
            'width', 'height', 'dimensions', 'alt_text', 'url', 'created_at'
        ]
        read_only_fields = ['id', 'filename', 'file_size', 'width', 'height', 'created_at']

    def get_url(self, obj):
        """Возвращает полный URL изображения"""
        request = self.context.get('request')
        if request and obj.image:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url if obj.image else None

    def get_file_size_mb(self, obj):
        """Возвращает размер файла в МБ"""
        return obj.get_file_size_mb()

    def get_dimensions(self, obj):
        """Возвращает размеры изображения"""
        return obj.get_dimensions()

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)
