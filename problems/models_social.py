"""Вход через VK ID и Яндекс ID (решения владельца 29.10.2026).

Отдельный файл по той же причине, что `models_platform.py`: модуль лежит
внутри приложения `problems`, app_label у него `problems`, а с `models.py`
его связывает одна строка импорта в конце.

⚠️ ТОКЕНОВ ЗДЕСЬ НЕТ И БЫТЬ НЕ ДОЛЖНО. После входа токен сервиса не нужен
ни для чего: данные человека мы забираем один раз, в момент возврата с
сервиса. Хранить его — значит хранить ключ от чужого аккаунта VK или Яндекса.
Сторож — `problems/tests/test_social_login.py` (имена полей без «token» и
«secret»).
"""
from django.conf import settings
from django.db import models


class SocialAccount(models.Model):
    """Привязка аккаунта к VK ID / Яндекс ID. Токены НЕ храним: они не нужны после входа."""

    PROVIDERS = (('vk', 'VK ID'), ('yandex', 'Яндекс ID'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='social_accounts', verbose_name='Пользователь')
    provider = models.CharField('Сервис', max_length=16, choices=PROVIDERS)
    uid = models.CharField('ID у сервиса', max_length=64)
    created_user = models.BooleanField('Аккаунт создан через сервис', default=False)
    created_at = models.DateTimeField('Привязан', auto_now_add=True)
    last_login_at = models.DateTimeField('Последний вход', null=True, blank=True)

    class Meta:
        verbose_name = 'Вход через сервис'
        verbose_name_plural = 'Входы через сервисы'
        constraints = [models.UniqueConstraint(fields=['provider', 'uid'],
                                               name='social_provider_uid_unique')]

    def __str__(self):
        return f'{self.user_id}: {self.get_provider_display()}'
