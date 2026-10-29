"""Адреса онбординга `/welcome/` (problems/views_onboarding.py)."""
from django.urls import path

from . import views_onboarding

urlpatterns = [
    path('', views_onboarding.entry, name='onboarding'),
    path('plan/', views_onboarding.plan, name='onboarding_plan'),
    path('build/', views_onboarding.build, name='onboarding_build'),
    path('api/cities/', views_onboarding.cities_api, name='onboarding_cities'),
    path('api/schools/', views_onboarding.schools_api, name='onboarding_schools'),
    path('<str:step>/', views_onboarding.step, name='onboarding_step'),
]
