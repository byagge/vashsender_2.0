from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SupportTicketViewSet, SupportMessageViewSet, SupportTicketListView, 
    SupportAdminPanelView, SupportChatViewSet, SupportChatMessageViewSet, SupportChatView
)

router = DefaultRouter()
router.register(r'tickets', SupportTicketViewSet, basename='support-ticket')
router.register(r'chats', SupportChatViewSet, basename='support-chat')
router.register(r'chat-messages', SupportChatMessageViewSet, basename='support-chat-message')

urlpatterns = [
    path('', SupportTicketListView.as_view(), name='ticket-list'),
    path('chat/', SupportChatView.as_view(), name='support-chat'),
    path('admin/', SupportAdminPanelView.as_view(), name='support-admin-panel'),
    path('api/', include(router.urls)),
] 