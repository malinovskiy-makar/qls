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


def version_for(kind):
    """Номер редакции, на которой сверяется и пишется согласие этого вида.

    Согласие на помощника живёт своей редакцией (`ai_version`, документ
    `consent_ai.md`): правка Политики не должна спрашивать его заново.
    Остальные виды идут за `docs_version`.
    """
    if kind == ConsentRecord.Kind.AI:
        return settings.LEGAL['ai_version']
    return current_version()


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
    """Есть действующая запись ТЕКУЩЕЙ редакции документа этого вида (`version_for`)."""
    record = active_record(user, kind)
    return bool(record and record.version == version_for(kind))


def wants_mail(user):
    """Человек согласился на рассылку: есть действующая запись `mail` ЛЮБОЙ редакции.

    ⚠️ НЕ `has_current`. Номер редакции поднимают при правке Политики или
    Согласия на обработку данных; если бы рассылка требовала текущую редакцию,
    каждое такое поднятие молча отписывало бы всех. Согласие на рассылку —
    отдельный документ, и оно действует, пока человек его не отозвал.
    """
    return active_record(user, ConsentRecord.Kind.MAIL) is not None


def grant(user, kind, source):
    """Принять документы текущей редакции. Идемпотентно.

    Действующая запись этой же редакции возвращается как есть. Действующая
    запись СТАРОЙ редакции закрывается (`superseded_at`) и заменяется новой,
    в одной транзакции, чтобы пара не осталась без действующей записи.
    """
    version = version_for(kind)
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
