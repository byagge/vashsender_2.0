from wagtail.admin.viewsets.model import ModelViewSet
from .models import SendingSettings


class SendingSettingsViewSet(ModelViewSet):
    model = SendingSettings
    icon = "cog"
    add_to_admin_menu = True
    menu_label = "Скорость отправки"
    menu_order = 900
    list_display = ("emails_per_minute", "updated_at")
    ordering = ("-updated_at",)
    form_fields = ["emails_per_minute"]


