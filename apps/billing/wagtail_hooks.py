from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet

from .models import PromoCode


class PromoCodeViewSet(ModelViewSet):
    """
    Wagtail CRUD-интерфейс для промокодов.

    Использует стандартный генератор форм Wagtail, поэтому
    отдельные формы/фильтры можно будет донастроить позже.
    """

    model = PromoCode
    icon = "tag"
    menu_label = "Промокоды"
    menu_order = 601  # рядом с разделом настроек/биллинга
    add_to_admin_menu = True

    # Конфигурация списка
    list_display = ["code", "plan", "max_activations", "used_activations", "expires_at", "is_active"]
    search_fields = ["code", "description", "plan__title"]

    # Говорим Wagtail, какие поля выводить в форме (требуется для ModelViewSet)
    form_fields = "__all__"


@hooks.register("register_admin_viewset")
def register_promo_code_viewset():
    """
    Регистрирует раздел «Промокоды» в левом меню Wagtail-админки.
    """

    return PromoCodeViewSet("promo-codes", url_prefix="promo-codes")


