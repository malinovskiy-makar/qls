# -*- coding: utf-8 -*-
"""ROOT_URLCONF проверки отображения: весь сайт + служебный просмотр задачи.

Подключается только в локальных `config/settings_quality_ro.py`; просмотр сам
проверяет `QUALITY_CONTOUR_PREVIEW` (иначе 404).
"""
from django.urls import path

from config.urls import urlpatterns as site_urlpatterns
from problems.olympiad_contour import views

urlpatterns = [
    path('_quality/problem/<int:pk>/', views.preview, name='quality_contour_preview'),
] + list(site_urlpatterns)
