"""Страховка от возврата публично известных дев-паролей.

Пароли из seed-команд лежат в открытом коде и в документации проекта.
Пока такой пользователь активен, вход в систему открыт любому, кто читал
репозиторий. Тест краснеет, если активный аккаунт с таким паролем появится
снова — например, если кто-то прогонит `seed_demo` на боевой базе.

Тест проверяет ТУ базу, против которой запущен (в CI это чистая тестовая
база). На проде тем же инвариантом занимается команда `lockdown_dev_accounts`.
"""

from django.test import TestCase

from problems.management.commands.lockdown_dev_accounts import (
    KNOWN_DEV_PASSWORDS,
    find_dev_accounts,
)
from problems.models import User


class NoDefaultPasswordsTests(TestCase):
    def test_no_active_user_has_known_dev_password(self):
        offenders = []
        for user in User.objects.filter(is_active=True):
            for password in KNOWN_DEV_PASSWORDS:
                if user.check_password(password):
                    offenders.append((user.username, password))
                    break

        self.assertEqual(
            offenders, [],
            'Активные учётные записи с публично известным дев-паролем: '
            f'{offenders}. Погасите их: manage.py lockdown_dev_accounts --apply',
        )

    def test_detector_finds_a_planted_account(self):
        """Сам детектор рабочий: подсаженный аккаунт обязан находиться.

        Без этой проверки первый тест был бы зелёным и на сломанном
        детекторе — то есть не проверял бы ничего.
        """
        User.objects.create_user(
            username='seeded_teacher', password='teacher12345')

        found = find_dev_accounts()
        names = {user.username for user, _ in found}
        self.assertIn('seeded_teacher', names)

        matched = {user.username: password for user, password in found}
        self.assertEqual(matched['seeded_teacher'], 'teacher12345')

    def test_random_password_is_not_flagged(self):
        """Обычный аккаунт со случайным паролем детектор не трогает."""
        User.objects.create_user(
            username='normal_user', password='Kr7#vQz2!mLp9xTw')

        names = {user.username for user, _ in find_dev_accounts()}
        self.assertNotIn('normal_user', names)
