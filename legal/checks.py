# -*- coding: utf-8 -*-
"""Проверка Django: сайт не выкатывается с пустыми реквизитами документов."""
from django.conf import settings
from django.core.checks import Error, register

from . import documents


@register()
def legal_requisites_filled(app_configs, **kwargs):
    """При DEBUG=False почта и дата редакции обязаны быть заданы.

    Документы показывают заглушку «[не заполнено]», пока значения пусты;
    на боевом сайте это недопустимо. Значения берутся из окружения
    (`LEGAL_CONTACT_EMAIL`, `LEGAL_DOCS_DATE`).
    """
    if settings.DEBUG or not getattr(settings, 'LEGAL_ENFORCEMENT_ENABLED', True):
        return []
    legal = getattr(settings, 'LEGAL', {})
    missing = []
    if not (legal.get('contact_email') or '').strip():
        missing.append(('LEGAL_CONTACT_EMAIL', 'почта для обращений по данным'))
    if not (legal.get('docs_date') or '').strip():
        missing.append(('LEGAL_DOCS_DATE',
                        'дата редакции документов, например «15 октября 2026 г.»'))
    errors = [
        Error('Не заполнено: %s.' % what,
              hint='Задайте переменную окружения %s. Пока она пуста, на страницах '
                   'документов вместо значения стоит заглушка «[не заполнено]».' % env,
              id='legal.E001')
        for env, what in missing
    ]
    email = (legal.get('contact_email') or '').strip()
    if email and not documents.EMAIL_RE.match(email):
        # Страницы такую «почту» не покажут: вместо неё встанет та же заглушка.
        errors.append(Error(
            'LEGAL_CONTACT_EMAIL не похож на адрес почты.',
            hint='Нужен один адрес электронной почты без пробелов и скобок.',
            id='legal.E002'))
    return errors
