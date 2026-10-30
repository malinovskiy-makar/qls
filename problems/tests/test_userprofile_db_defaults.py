# -*- coding: utf-8 -*-
"""Миграция `problems/0088`: `db_default` у четырёх полей анкеты, чтобы откат кода безопасен.

Старый код (до входа и онбординга) создаёт профиль сигналом и вставляет строку, не зная колонок
`goals`, `source_other`, `teach_grades`, `teach_places` (миграции 0084–0085). Колонка NOT NULL без
DEFAULT в базе роняла бы каждую новую регистрацию, а Django после `AddField` с обычным `default=`
снимает DEFAULT (`ALTER COLUMN … DROP DEFAULT`). С `db_default` в базе остаётся DEFAULT.
"""
from django.db import connection
from django.db.models.fields import NOT_PROVIDED
from django.test import TestCase
from django.utils import timezone

from problems.models_platform import UserProfile
from problems.tests.factories import make_user

NEW_COLUMNS = ('goals', 'source_other', 'teach_grades', 'teach_places')


class UserProfileDbDefaultTests(TestCase):
    def test_the_four_fields_carry_a_database_default(self):
        for name in NEW_COLUMNS:
            field = UserProfile._meta.get_field(name)
            self.assertIsNot(field.db_default, NOT_PROVIDED, name)

    def test_old_code_insert_without_the_four_columns_passes(self):
        """Вставка «как у старого кода»: все колонки, КРОМЕ четырёх новых, сырым SQL."""
        user = make_user('old_code_signup')
        UserProfile.objects.filter(user=user).delete()
        fields = [f for f in UserProfile._meta.concrete_fields
                  if not f.primary_key and f.name not in NEW_COLUMNS]
        columns = [f.column for f in fields]
        values = []
        for f in fields:
            if f.name == 'user':
                values.append(user.pk)
            elif getattr(f, 'auto_now', False) or getattr(f, 'auto_now_add', False):
                values.append(f.get_db_prep_save(timezone.now(), connection))   # Django ставит сам
            else:
                values.append(f.get_db_prep_save(f.get_default(), connection))
        quote = connection.ops.quote_name
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            quote(UserProfile._meta.db_table), ', '.join(quote(c) for c in columns),
            ', '.join(['%s'] * len(columns)))
        with connection.cursor() as cursor:
            cursor.execute(sql, values)
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.goals, [])
        self.assertEqual(profile.teach_grades, [])
        self.assertEqual(profile.teach_places, [])
        self.assertEqual(profile.source_other, '')
