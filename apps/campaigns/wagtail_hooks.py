from wagtail import hooks
from .utils import SendingSettingsViewSet


@hooks.register("register_admin_viewset")
def register_sending_settings_viewset():
    return SendingSettingsViewSet("sending-settings", url_prefix="sending-settings")


