from wagtail import hooks
from wagtail.admin.menu import MenuItem
from django.urls import reverse


@hooks.register('register_admin_menu_item')
def register_link_to_django_admin():
    # Добавляем ссылку на стандартную Django админку в меню Wagtail
    return MenuItem('Django Admin', '/django-admin/', icon_name='site', order=1000)


