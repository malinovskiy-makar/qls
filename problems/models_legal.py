# -*- coding: utf-8 -*-
"""Запись согласия (живёт в `problems`, как все модели проекта; логика — приложение `legal`): кто, на что, какую редакцию документов принял и когда.

Это доказательство, а не настройка: по ней можно показать, что КОНКРЕТНЫЙ
человек принял КОНКРЕТНУЮ редакцию. Поэтому строки только добавляются и
закрываются (отзыв, замена более новой редакцией), но не стираются и не
переписываются.

⚠️ IP-адрес и User-Agent НЕ хранятся (решение владельца 08.10.2026): они сами
были бы персональными данными, а для доказательства хватает пользователя,
вида, редакции и времени.

⚠️ ОДНА ДЕЙСТВУЮЩАЯ ЗАПИСЬ НА ПАРУ «ПОЛЬЗОВАТЕЛЬ — ВИД» держится ограничением
базы, а не только кодом: две одновременные кнопки «Принимаю» не создадут двух
строк (вторая упрётся в ограничение, `consent.grant` это переживает).
Действующая = не отозвана и не заменена более новой редакцией.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ConsentRecord(models.Model):
    class Kind(models.TextChoices):
        PD = 'pd', 'Обработка данных и пользовательское соглашение'
        AI = 'ai', 'Помощник на основе ИИ и передача данных в Сингапур'

    class Source(models.TextChoices):
        REGISTER = 'register', 'Регистрация'
        GATE = 'gate', 'Экран согласия при входе'
        CHAT = 'chat', 'Панель помощника'
        PROFILE = 'profile', 'Профиль'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='consents', verbose_name='Пользователь')
    kind = models.CharField('Вид', max_length=8, choices=Kind.choices)
    version = models.CharField('Редакция документов', max_length=16)
    given_at = models.DateTimeField('Принято', default=timezone.now)
    source = models.CharField('Откуда', max_length=16, choices=Source.choices)
    revoked_at = models.DateTimeField('Отозвано', null=True, blank=True)
    # Заменена записью более новой редакции. Отдельное поле, а не отзыв: человек
    # ничего не отзывал, он принял новую редакцию поверх прежней.
    superseded_at = models.DateTimeField('Заменено новой редакцией', null=True, blank=True)

    class Meta:
        verbose_name = 'Согласие'
        verbose_name_plural = 'Согласия'
        ordering = ['-given_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'kind'],
                condition=Q(revoked_at__isnull=True, superseded_at__isnull=True),
                name='legal_one_active_consent_per_kind'),
        ]
        indexes = [models.Index(fields=['user', 'kind'], name='legal_consent_user_kind')]

    def __str__(self):
        if self.revoked_at:
            state = 'отозвано'
        elif self.superseded_at:
            state = 'заменено'
        else:
            state = 'действует'
        return '%s · %s · ред. %s · %s' % (self.user_id, self.kind, self.version, state)

    @property
    def is_active(self):
        return self.revoked_at is None and self.superseded_at is None
