"""
URL configuration for library_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from library.views import register, verify_registration
from django.contrib.auth.views import LoginView, LogoutView

from library.views import RegisterView
from library.auth_views import StudentLoginView, AdminLoginView, verify_otp
from library.librarian_views import (
    librarian_dashboard,
    approve_borrow_request,
    reject_borrow_request,
    approve_return_request,
    reject_return_request,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # These three must come before the django.contrib.auth.urls include below
    # so they win the 'login' name and take over that URL/behavior.
    path('accounts/login/', StudentLoginView.as_view(), name='login'),
    path('admin-login/', AdminLoginView.as_view(), name='admin_login'),
    path('verify-otp/', verify_otp, name='verify_otp'),
    path('accounts/register/verify/', verify_registration, name='verify_registration'),
    path('librarian/', librarian_dashboard, name='librarian_dashboard'),
    path('librarian/borrow/<int:pk>/approve/', approve_borrow_request, name='approve_borrow_request'),
    path('librarian/borrow/<int:pk>/reject/', reject_borrow_request, name='reject_borrow_request'),
    path('librarian/return/<int:pk>/approve/', approve_return_request, name='approve_return_request'),
    path('librarian/return/<int:pk>/reject/', reject_return_request, name='reject_return_request'),
    path('', include('library.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/register/', register, name='register'),
]
