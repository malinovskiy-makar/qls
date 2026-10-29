"""Адреса входа через VK ID / Яндекс ID. Подключаются в config/urls.py под `auth/`."""
from django.urls import path

from . import views

urlpatterns = [
    path('finish/', views.finish, name='social_finish'),
    path('<str:provider>/start/', views.start, name='social_start'),
    path('<str:provider>/callback/', views.callback, name='social_callback'),
]
