# -*- coding: utf-8 -*-
"""Коды подтверждения почты: выдать, проверить, погасить (docs/MAIL.md).

Регистрация, сброс пароля, страница «Почта» и стена тренажёра ВП пользуются
ТОЛЬКО этим модулем: второе место, где решают «подтверждена ли почта» или
«верен ли код», разошлось бы с первым.

Правила (таблица лимитов — в docs/MAIL.md):

* код — 6 цифр, живёт 10 минут, на него 5 неверных вводов, затем он мёртв;
* новый код на тот же адрес и цель — не раньше чем через 60 с и не больше
  5 писем в час; с одного адреса в сети — лестница `problems/ratelimit.py`
  (scope `email_code:ip`, за одним адресом бывает целый класс);
* в базе только отпечаток HMAC-SHA256 на `SECRET_KEY` от «цель:почта:код»;
* новый код гасит прежние непогашенные коды того же адреса и цели.

⚠️ НЕОТПРАВЛЕННЫЙ КОД НЕ СЧИТАЕТСЯ. Письмо не ушло — только что созданная
строка удаляется: иначе отказ почтового сервера съел бы минуту ожидания и
одно из пяти писем часа, а человек не получил бы ничего.
"""
import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from . import mail, ratelimit
from .models_mail import EmailCode

Purpose = EmailCode.Purpose

CODE_TTL = timedelta(minutes=10)
RESEND_AFTER = 60               # секунд между письмами на один адрес и цель
HOURLY_LIMIT = 5                # писем в час на один адрес и цель
MAX_ATTEMPTS = 5                # неверных вводов на один код
IP_SCOPE = 'email_code:ip'

_SUBJECTS = {
    Purpose.REGISTER: 'Код подтверждения Weconomics: %s',
    Purpose.CONFIRM: 'Код подтверждения Weconomics: %s',
    Purpose.RESET: 'Код для смены пароля Weconomics: %s',
}
_INTROS = {
    Purpose.REGISTER: 'Код для регистрации на Weconomics:',
    Purpose.CONFIRM: 'Код для подтверждения почты на Weconomics:',
    Purpose.RESET: 'Код для смены пароля на Weconomics:',
}


@dataclass(frozen=True)
class SendResult:
    ok: bool
    reason: str = ''        # '' | 'disabled' | 'wait' | 'limit' | 'ip_locked' | 'send_failed'
    wait_seconds: int = 0


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    reason: str = ''        # '' | 'missing' | 'expired' | 'locked' | 'wrong'
    attempts_left: int = 0


def mail_enabled():
    return bool(getattr(settings, 'MAIL_ENABLED', False))


def normalize_email(value):
    """Пробелы по краям и нижний регистр — больше ничего.

    Точки и «+метки» Gmail не трогаем: для других ящиков это разные адреса.
    """
    return (value or '').strip().lower()


def _digest(email, purpose, code):
    message = '%s:%s:%s' % (purpose, email, code)
    return hmac.new(settings.SECRET_KEY.encode('utf-8'), message.encode('utf-8'),
                    hashlib.sha256).hexdigest()


def _only_digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _new_code():
    return '%06d' % secrets.randbelow(10 ** 6)


def send_code(email, purpose, *, user=None, request=None):
    """Выдать новый код и отправить его письмом."""
    if not mail_enabled():
        return SendResult(False, 'disabled')
    email = normalize_email(email)
    now = timezone.now()

    ip = ratelimit.client_ip(request) if request is not None else ''
    if ip:
        locked = ratelimit.seconds_locked(IP_SCOPE, ip)
        if locked:
            return SendResult(False, 'ip_locked', locked)

    recent = EmailCode.objects.filter(email=email, purpose=purpose,
                                      created_at__gt=now - timedelta(hours=1))
    last = recent.order_by('-created_at').first()
    if last is not None:
        elapsed = (now - last.created_at).total_seconds()
        if elapsed < RESEND_AFTER:
            return SendResult(False, 'wait', max(1, math.ceil(RESEND_AFTER - elapsed)))
    if recent.count() >= HOURLY_LIMIT:
        oldest = recent.order_by('created_at').first()
        left = (oldest.created_at + timedelta(hours=1) - now).total_seconds()
        return SendResult(False, 'limit', max(1, math.ceil(left)))

    code = _new_code()
    row = EmailCode.objects.create(
        email=email, purpose=purpose, code_hash=_digest(email, purpose, code),
        user=user, created_at=now, expires_at=now + CODE_TTL)
    sent = mail.send_templated(
        to=email, subject=_SUBJECTS[purpose] % code, template='code',
        context={'intro': _INTROS[purpose], 'code': code})
    if not sent:
        row.delete()
        return SendResult(False, 'send_failed')

    # Прежние коды больше не годятся: в ящике должен работать только последний.
    (EmailCode.objects.filter(email=email, purpose=purpose, used_at__isnull=True)
     .exclude(pk=row.pk).update(used_at=now))
    if ip:
        ratelimit.note_failure(IP_SCOPE, ip, multiplier=ratelimit.IP_MULTIPLIER)
    return SendResult(True)


def check_code(email, purpose, code):
    """Проверить введённый код. При `ok` код погашен и второй раз не пройдёт.

    ⚠️ В ТРАНЗАКЦИИ С `select_for_update`: иначе пять параллельных запросов
    прочитали бы один и тот же счётчик неверных вводов и каждый получил бы
    свою «последнюю» попытку.
    """
    email = normalize_email(email)
    digest = _digest(email, purpose, _only_digits(code))
    now = timezone.now()
    with transaction.atomic():
        live = list(EmailCode.objects.select_for_update()
                    .filter(email=email, purpose=purpose, used_at__isnull=True)
                    .order_by('-created_at', '-pk'))
        if not live:
            return CheckResult(False, 'missing')
        current = live[0]
        if current.attempts >= MAX_ATTEMPTS:
            return CheckResult(False, 'locked')
        match = next((row for row in live
                      if hmac.compare_digest(row.code_hash, digest)), None)
        if match is not None:
            if match.expires_at <= now:
                return CheckResult(False, 'expired')
            match.used_at = now
            match.save(update_fields=['used_at'])
            return CheckResult(True)
        if current.expires_at <= now:
            return CheckResult(False, 'expired')
        current.attempts += 1
        current.save(update_fields=['attempts'])
        if current.attempts >= MAX_ATTEMPTS:
            return CheckResult(False, 'locked')
        return CheckResult(False, 'wrong', MAX_ATTEMPTS - current.attempts)


def resend_wait(email, purpose):
    """Сколько секунд до следующей отправки на этот адрес (0 — можно).

    Для кнопки «Отправить код ещё раз»: сервер говорит, сколько ждать, а
    скрипт страницы только отсчитывает.
    """
    last = (EmailCode.objects.filter(email=normalize_email(email), purpose=purpose)
            .order_by('-created_at').first())
    if last is None:
        return 0
    left = RESEND_AFTER - (timezone.now() - last.created_at).total_seconds()
    return max(0, math.ceil(left))


def has_verified_email(user):
    """У вошедшего человека есть подтверждённая почта."""
    return bool(user is not None and getattr(user, 'is_authenticated', False)
                and user.email and user.email_verified_at)


def verified_user_for(email):
    """Пользователь, который подтвердил эту почту, или None."""
    email = normalize_email(email)
    if not email:
        return None
    return (get_user_model().objects
            .filter(email__iexact=email, email_verified_at__isnull=False).first())


# ── Тексты для человека и привязка почты ────────────────────────────────
#
# Здесь, а не в представлении: ими пользуются и страница «Почта», и окно стены
# тренажёра ВП (`vp/views.py`). Две копии текстов разошлись бы при первой правке.

def minutes(seconds):
    return max(1, (seconds + 59) // 60)


def send_error(result):
    """Текст для человека по отказу `send_code`."""
    if result.reason == 'limit':
        return ('Слишком много писем на этот адрес. Попробуйте через %d мин.'
                % minutes(result.wait_seconds))
    if result.reason == 'wait':
        return ('Код на этот адрес уже отправлен. Новый можно запросить через %d с.'
                % result.wait_seconds)
    if result.reason == 'ip_locked':
        return ('Слишком много писем с вашего адреса в сети. Попробуйте через %d мин.'
                % minutes(result.wait_seconds))
    return 'Не получилось отправить письмо. Проверьте адрес или попробуйте через минуту.'


def check_error(check):
    """Текст для человека по отказу `check_code`."""
    if check.reason == 'wrong':
        return 'Неверный код. Осталось попыток: %d.' % check.attempts_left
    if check.reason == 'locked':
        return 'Слишком много неверных попыток. Отправьте новый код.'
    return 'Код устарел. Отправьте новый.'


#: Текст для человека, когда почту уже подтвердил другой аккаунт.
TAKEN_MESSAGE = 'Эта почта уже привязана к другому аккаунту.'


class EmailTaken(Exception):
    """Почта уже подтверждена другим аккаунтом."""


def attach_verified_email(user, email):
    """Привязывает к аккаунту почту, подтверждённую кодом. В транзакции заново проверяет,
    что почта не подтверждена другим аккаунтом (два человека могли ввести коды одновременно);
    IntegrityError от ограничения user_verified_email_ci_unique — тоже EmailTaken.
    Занята — EmailTaken, в базе ничего не меняется. Согласие на рассылку — НЕ здесь:
    у страницы «Почта» и у стены свои правила галочки."""
    from django.db import IntegrityError

    email = normalize_email(email)
    before = (user.email, user.email_verified_at)
    try:
        with transaction.atomic():
            other = verified_user_for(email)
            if other is not None and other.pk != user.pk:
                raise EmailTaken()
            user.email = email
            user.email_verified_at = timezone.now()
            user.save(update_fields=['email', 'email_verified_at'])
    except (EmailTaken, IntegrityError):
        # В базе откатилось само; объект в памяти возвращаем к прежнему.
        user.email, user.email_verified_at = before
        raise EmailTaken() from None
