from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ContactListViewSet, ListSpaView, ImportTasksView, DomainProxyViewSet

router = DefaultRouter()
router.register(r'contactlists', ContactListViewSet, basename='contactlists')
router.register(r'domains', DomainProxyViewSet, basename='mailer-domains')

urlpatterns = [
    path('api/', include(router.urls)),
    path('', ListSpaView.as_view(), name='lists_spa'),
    path('import-tasks/', ImportTasksView.as_view(), name='import_tasks'),
]
