# -*- coding: utf-8 -*-
"""Логин, который сайт придумывает сам: `econ_` + 6 знаков `[a-z0-9]`.

Нужен двум местам: регистрации почтой (раунд 2, решение 29.10.2026 «почта +
пароль, логин создаём сами») и входу через VK ID / Яндекс ID. Логин виден в
таблицах результатов, поэтому он НЕ из имени и не из почты: имя ребёнка там
светиться не должно. Сменить его можно в профиле.
"""
import secrets
import string

USERNAME_PREFIX = 'econ_'
USERNAME_ALPHABET = string.ascii_lowercase + string.digits


def free_username():
    """Свободный логин. Занятость сверяется без учёта регистра, как у формы."""
    from problems.models import User

    for _attempt in range(50):
        name = USERNAME_PREFIX + ''.join(secrets.choice(USERNAME_ALPHABET) for _ in range(6))
        if not User.objects.filter(username__iexact=name).exists():
            return name
    raise RuntimeError('не удалось подобрать свободный логин')
