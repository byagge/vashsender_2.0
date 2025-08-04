from django.db import models
from django.utils import timezone
from apps.campaigns.models import Campaign
from apps.accounts.models import User

class CampaignModeration(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Ожидает проверки'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
    )

    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name='moderation')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_campaigns')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    auto_send_at = models.DateTimeField(null=True, blank=True)  # Время автоматической отправки, если не одобрено

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Модерация кампании'
        verbose_name_plural = 'Модерация кампаний'

    def __str__(self):
        return f"Модерация кампании {self.campaign.name} - {self.get_status_display()}"

    def approve(self, moderator):
        """Одобрить кампанию и начать отправку"""
        print(f"Одобряем кампанию {self.campaign.name} модератором {moderator.email}")
        
        self.status = 'approved'
        self.moderator = moderator
        self.save()
        
        # Запускаем фактическую отправку писем
        try:
            from apps.campaigns.tasks import send_campaign
            print(f"Запускаем отправку кампании {self.campaign.id} с skip_moderation=True")
            result = send_campaign.apply(args=[str(self.campaign.id), True])  # skip_moderation=True
            print(f"Результат отправки: {result}")
            print(f"Кампания {self.campaign.name} успешно отправлена после одобрения модератором")
        except Exception as e:
            print(f"Ошибка при отправке кампании {self.campaign.name} после одобрения: {e}")
            # Если отправка не удалась, меняем статус на failed
            self.campaign.status = 'failed'
            self.campaign.save()

    def reject(self, moderator, reason):
        """Отклонить кампанию с указанием причины"""
        self.status = 'rejected'
        self.moderator = moderator
        self.rejection_reason = reason
        self.save()
        
        # Обновляем статус кампании
        self.campaign.status = 'rejected'
        self.campaign.save()
        
        # Здесь можно добавить логику уведомления пользователя об отклонении

    def set_auto_send(self, hours=2):
        """Установить время автоматической отправки"""
        self.auto_send_at = timezone.now() + timezone.timedelta(hours=hours)
        self.save()

    def cancel_auto_send(self):
        """Отменить автоматическую отправку"""
        self.auto_send_at = None
        self.save()

    @property
    def time_until_auto_send(self):
        """Время до автоматической отправки в секундах"""
        if self.auto_send_at and self.status == 'pending':
            return int((self.auto_send_at - timezone.now()).total_seconds())
        return None 