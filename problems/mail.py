# -*- coding: utf-8 -*-
"""Единственное место, откуда сайт отправляет письма (docs/MAIL.md).

Письмо собирается из пары шаблонов `templates/email/<имя>.txt` и `.html`,
уходит от `DEFAULT_FROM_EMAIL`, «Ответить» ведёт на `MAIL_REPLY_TO`.

⚠️ ОТКАЗ ПОЧТЫ НЕ РОНЯЕТ СТРАНИЦУ. Сервер отправки недоступен, отказал,
оборвал связь — `send_templated` возвращает `False`, а страница говорит
человеку «не получилось, попробуйте через минуту». Временный отказ (ответ
4xx, например лимит Postbox «1 письмо в секунду») повторяется ОДИН раз через
1,2 с; дольше держать запрос человека нельзя.

⚠️ В ЖУРНАЛ НЕ ПОПАДАЮТ НИ ТЕМА, НИ ТЕКСТ ПИСЬМА: в теме стоит код
подтверждения, а журнал читают люди и он лежит дольше кода. Адрес — только
замаскированный (`m***@gmail.com`), из ошибки — только её класс и числовой код.
"""
import logging
import smtplib
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger('problems.mail')

#: Пауза перед повтором при временном отказе. Postbox по умолчанию
#: пропускает одно письмо в секунду — ждём чуть дольше секунды.
RETRY_DELAY = 1.2


def mask_email(address):
    """`masha@gmail.com` → `m***@gmail.com`: для журнала, не для людей."""
    local, _, domain = (address or '').partition('@')
    if not domain:
        return '***'
    return '%s***@%s' % (local[:1], domain)


def _smtp_code(exc):
    """Числовой код ответа сервера из исключения smtplib или None."""
    code = getattr(exc, 'smtp_code', None)
    if code is None and isinstance(exc, smtplib.SMTPRecipientsRefused):
        # Отказ по адресатам: код лежит в словаре «адрес → (код, текст)».
        for value in exc.recipients.values():
            code = value[0]
            break
    return code if isinstance(code, int) else None


def send_templated(*, to, subject, template, context):
    """Отправить письмо одному адресату. `True` — сервер принял письмо."""
    text = render_to_string('email/%s.txt' % template, context)
    try:
        html = render_to_string('email/%s.html' % template, context)
    except TemplateDoesNotExist:
        html = None
    reply_to = getattr(settings, 'MAIL_REPLY_TO', '')
    message = EmailMultiAlternatives(
        subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to], reply_to=[reply_to] if reply_to else None,
        # Автоответчики получателя не должны отвечать на код.
        headers={'Auto-Submitted': 'auto-generated'})
    if html:
        message.attach_alternative(html, 'text/html')

    for attempt in (1, 2):
        try:
            message.send(fail_silently=False)
            return True
        except smtplib.SMTPException as exc:
            code = _smtp_code(exc)
            if attempt == 1 and code is not None and 400 <= code < 500:
                time.sleep(RETRY_DELAY)
                continue
            _log_failure(to, exc, code)
            return False
        except OSError as exc:
            # Нет связи с сервером, тайм-аут, отказ в соединении.
            _log_failure(to, exc, None)
            return False
    return False


def _log_failure(to, exc, code):
    logger.warning('Письмо не отправлено: адрес %s, ошибка %s, код %s',
                   mask_email(to), type(exc).__name__,
                   code if code is not None else '-')
