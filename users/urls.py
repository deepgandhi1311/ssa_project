from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
from .views import SecureTwoFactorLoginView

urlpatterns = [
    path("login", SecureTwoFactorLoginView.as_view(), name="login"),
    path('logout/', LogoutView.as_view(next_page='two_factor:login'), name='logout'),
    path('register/', views.register, name='register'),
]