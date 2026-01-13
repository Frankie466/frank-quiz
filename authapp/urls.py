# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('activate-premium/', views.activate_premium_view, name='activate_premium'),
    path('debug-users/', views.debug_users, name='debug_users'),
    path('test-pin/', views.test_pin_verification, name='test_pin'),  # Add this
    
    # Premium activation URLs
   
    path('initiate-premium-payment/', views.initiate_premium_payment, name='initiate_premium_payment'),
    path('mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
    path('check-payment-status/', views.check_payment_status, name='check_payment_status'),
    
    # Debug URLs (remove in production)
    path('debug-users/', views.debug_users, name='debug_users'),
    path('test-pin/', views.test_pin_verification, name='test_pin_verification'),
]
