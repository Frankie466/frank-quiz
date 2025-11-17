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
]