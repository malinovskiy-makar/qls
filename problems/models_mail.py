# -*- coding: utf-8 -*-
"""Код подтверждения почты (живёт в `problems`, как все модели проекта;
логика — `problems/email_codes.py`, docs/MAIL.md).

⚠️ САМ КОД НЕ ХРАНИТСЯ. В базе только отпечаток HMAC-SHA256 на `SECRET_KEY`
от строки «цель:почта:код»: копия базы или выгрузка таблицы не даёт ввести
чужой код, а отпечаток одного кода не подходит ни к другой цели, ни к другому
адресу.

Строки живут сутки: старше их удаляет `purge_expired` (`problems/retention.py`).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class EmailCode(models.Model):
    class Purpose(models.TextChoices):
        REGISTER = 'register', 'Регистрация'
        RESET = 'reset', 'Смена пароля'
        CONFIRM = 'confirm', 'Подтверждение почты в профиле'

    email = models.EmailField('Почта', max_length=254)            # всегда нижний регистр
    purpose = models.CharField('Цель', max_length=16, choices=Purpose.choices)
    code_hash = models.CharField('Отпечаток кода', max_length=64)  # сам код не хранится
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.CASCADE, related_name='email_codes')
    created_at = models.DateTimeField('Создан', default=timezone.now)
    expires_at = models.DateTimeField('Действует до')
    attempts = models.PositiveSmallIntegerField('Неверных вводов', default=0)
    used_at = models.DateTimeField('Погашен', null=True, blank=True)

    class Meta:
        verbose_name = 'Код подтверждения'
        verbose_name_plural = 'Коды подтверждения'
        indexes = [models.Index(fields=['email', 'purpose', 'created_at'],
                                name='mail_code_email_purpose_ts')]

    def __str__(self):
        return '%s · %s · %s' % (self.email, self.purpose,
                                 self.created_at.strftime('%d.%m %H:%M'))
