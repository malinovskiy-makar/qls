# -*- coding: utf-8 -*-
"""Боты для браузерных проб: ученик, преподаватель, родитель.

Зачем отдельные аккаунты. Демонстрационные учётки (`student1`, `teacher1`,
`admin`) в этой копии базы уже погашены командой `lockdown_dev_accounts`
— и правильно: их пароли публично известны. Пробам Playwright всё равно
нужен вход, поэтому заводится отдельная тройка ботов с паролем, который
осмысленно существует только в локальной копии базы.

⚠️ На боевом сервере запускать НЕЛЬЗЯ и незачем: пароль лежит в открытом
виде прямо здесь. Скрипт нужен разработчику на своей машине.

Запуск: venv313/Scripts/python.exe scripts/ensure_probe_users.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from problems.models import User  # noqa: E402

PASSWORD = 'probebot-local-2026'

BOTS = (
    ('shot_bot', 'student', 'Ученик', 'Пробный'),
    ('shot_bot_teacher', 'teacher', 'Преподаватель', 'Пробный'),
    ('shot_bot_parent', 'viewer', 'Родитель', 'Пробный'),
)


def main():
    for username, role, first, last in BOTS:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'first_name': first, 'last_name': last},
        )
        user.first_name = first
        user.last_name = last
        user.role = role
        user.is_active = True
        user.set_password(PASSWORD)
        user.save()
        print(f'{"создан" if created else "обновлён"}: {username} (role={role})')


if __name__ == '__main__':
    main()
