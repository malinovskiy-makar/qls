# -*- coding: utf-8 -*-
"""Адреса для осмотра страниц ошибок. Только вместе с settings_errorcheck.

Обычные адреса проекта на месте; добавлены три, которых в бою нет и быть
не должно, — они нужны, чтобы человек мог ПОСМОТРЕТЬ на страницу 500, 403
и 400, а не поверить на слово, что она красивая.
"""
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.urls import path

from config.urls import urlpatterns as _base


def _boom(request):
    raise RuntimeError('нарочно сломано, чтобы посмотреть страницу 500')


def _forbidden(request):
    raise PermissionDenied('нарочно закрыто, чтобы посмотреть страницу 403')


def _bad(request):
    raise SuspiciousOperation('нарочно неверно, чтобы посмотреть страницу 400')


urlpatterns = list(_base) + [
    path('oshibka-500/', _boom),
    path('oshibka-403/', _forbidden),
    path('oshibka-400/', _bad),
]
