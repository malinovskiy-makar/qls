"""Адреса онбординга `/welcome/` (problems/views_onboarding.py)."""
from django.urls import path

from . import views_onboarding

urlpatterns = [
    path('', views_onboarding.entry, name='onboarding'),
    path('plan/', views_onboarding.plan, name='onboarding_plan'),
    path('<str:step>/', views_onboarding.step, name='onboarding_step'),
]
