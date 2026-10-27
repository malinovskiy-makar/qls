# -*- coding: utf-8 -*-
"""Безопасный адрес возврата `next` — одна проверка на регистрацию, её
подтверждение, сброс пароля и страницу «Почта».

⚠️ `next` СЛУШАЕТСЯ, НО ТОЛЬКО СВОЙ. Тренажёр ВП уводит гостя на регистрацию
со своего варианта и ждёт его обратно (решение владельца 22.09.2026). Чужой
адрес в `next` — открытый перенаправитель, поэтому он проверяется
`url_has_allowed_host_and_scheme` и при непригодности молча отбрасывается.
"""
from django.utils.http import url_has_allowed_host_and_scheme


def is_safe(request, target):
    return bool(target) and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()},
        require_https=request.is_secure())


def safe_next(request):
    """Безопасный `next` из POST или GET; пусто, если его нет или он чужой."""
    target = request.POST.get('next') or request.GET.get('next') or ''
    return target if is_safe(request, target) else ''
