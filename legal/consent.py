# -*- coding: utf-8 -*-
"""Единственная точка чтения и записи согласий.

Экран, регистрация, защита помощника и профиль ходят сюда и больше никуда:
второе место, где решают «есть ли согласие», разошлось бы с первым.
"""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models_legal import ConsentRecord

#: Ключ сессии: «этот человек уже принял текущую редакцию». Без него экран
#: согласия спрашивал бы базу на КАЖДОМ запросе. Значение — номер редакции,
#: поэтому смена редакции сбрасывает признак сама, без чистки сессий.
SESSION_KEY = 'legal_pd_version'


def current_version():
    return settings.LEGAL['docs_version']


def enforcement_enabled():
    return bool(getattr(settings, 'LEGAL_ENFORCEMENT_ENABLED', True))


def active_record(user, kind):
    """Действующая запись этого вида или None (любой редакции)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    return (ConsentRecord.objects
            .filter(user=user, kind=kind, revoked_at__isnull=True, superseded_at__isnull=True)
            .first())


def has_current(user, kind):
    """Есть действующая запись ТЕКУЩЕЙ редакции документов."""
    record = active_record(user, kind)
    return bool(record and record.version == current_version())


def grant(user, kind, source):
    """Принять документы текущей редакции. Идемпотентно.

    Действующая запись этой же редакции возвращается как есть. Действующая
    запись СТАРОЙ редакции закрывается (`superseded_at`) и заменяется новой,
    в одной транзакции, чтобы пара не осталась без действующей записи.
    """
    version = current_version()
    for _attempt in range(2):
        try:
            with transaction.atomic():
                record = (ConsentRecord.objects.select_for_update()
                          .filter(user=user, kind=kind,
                                  revoked_at__isnull=True, superseded_at__isnull=True)
                          .first())
                if record is not None and record.version == version:
                    return record
                if record is not None:
                    record.superseded_at = timezone.now()
                    record.save(update_fields=['superseded_at'])
                return ConsentRecord.objects.create(
                    user=user, kind=kind, version=version, source=source)
        except IntegrityError:
            # Параллельный запрос успел создать действующую запись раньше;
            # второй проход её найдёт и вернёт.
            continue
    return active_record(user, kind)


def revoke(user, kind):
    """Отозвать действующее согласие. Строка остаётся. Возвращает число отозванных."""
    return (ConsentRecord.objects
            .filter(user=user, kind=kind, revoked_at__isnull=True, superseded_at__isnull=True)
            .update(revoked_at=timezone.now()))


def remember_in_session(request):
    """Запомнить в сессии, что документы текущей редакции приняты."""
    request.session[SESSION_KEY] = current_version()


def forget_in_session(request):
    request.session.pop(SESSION_KEY, None)
