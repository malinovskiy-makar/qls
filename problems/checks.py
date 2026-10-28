# -*- coding: utf-8 -*-
"""Проверки Django приложения `problems`.

`mail.E001`: сайт не выкатывается с включённой почтой, которая никуда не
отправляет (docs/MAIL.md). Без `EMAIL_HOST` Django молча печатал бы письма в
журнал контейнера: регистрация шла бы, а коды не доходили бы ни до кого.
"""
from django.conf import settings
from django.core.checks import Error, register

_REQUIRED = (
    ('EMAIL_HOST', 'адрес почтового сервера, например postbox.cloud.yandex.net'),
    ('EMAIL_HOST_USER', 'идентификатор ключа сервисного аккаунта Postbox'),
    ('EMAIL_HOST_PASSWORD', 'секрет ключа сервисного аккаунта Postbox'),
)


@register()
def mail_channel_configured(app_configs, **kwargs):
    """При MAIL_ENABLED и DEBUG=False канал отправки обязан быть задан."""
    if settings.DEBUG or not getattr(settings, 'MAIL_ENABLED', False):
        return []
    missing = [(name, what) for name, what in _REQUIRED
               if not (getattr(settings, name, '') or '').strip()]
    if not missing:
        return []
    return [Error(
        'Почта включена (MAIL_ENABLED=1), но канал отправки не задан: %s.'
        % ', '.join(name for name, _ in missing),
        hint='Задайте в .env: %s. Или выключите почту: MAIL_ENABLED=0. '
             'Порядок включения — docs/MAIL.md.'
             % '; '.join('%s — %s' % pair for pair in missing),
        id='mail.E001')]
