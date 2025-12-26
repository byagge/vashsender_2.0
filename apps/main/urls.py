from django.urls import path
from . import views

app_name = 'main'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('consultation/', views.consultation_page, name='consultation'),
    path('pricing/', views.pricing_page, name='pricing'),
    path('api/plans/', views.get_plans_api, name='get_plans_api'),
    path('purchase/confirm/', views.purchase_confirmation_page, name='purchase_confirmation'),
    path('purchase/success/', views.purchase_success, name='purchase_success'),
    path('how-to-create-a-campaign/', views.campaigns_page, name='campaigns'),
    path('legal/license/', views.license_page, name='license'),
    path('legal/privacy/', views.privacy_page, name='privacy'),
    path('legal/antispam/', views.antispam_page, name='antispam'),
    path('consultation-request/', views.consultation_request, name='consultation_request'),
    path('legal/download-instruction/', views.download_instruction_file, name='download_instruction'),
] 
