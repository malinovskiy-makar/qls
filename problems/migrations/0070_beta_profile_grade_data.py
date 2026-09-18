# Часть 2 из 3 (18.09.2026): перевод значений `grade` число → код.
"""Только данные — своей транзакцией, отдельно от структурных изменений.

Контекст и причина разбивки — в docstring `0069_beta_profile_fields.py`.

Вперёд: 5, 6, 7 → `le7`; 8…11 → та же строка; NULL → ''.
Назад: `le7` → 7 (⚠️ различие 5/6/7 теряется безвозвратно — после перехода
его нет в данных); `none` и '' → NULL; 8…11 → число.
"""
from django.db import migrations

YOUNG = ('5', '6', '7')


def grade_to_codes(apps, schema_editor):
    UserProfile = apps.get_model('problems', 'UserProfile')
    UserProfile.objects.filter(grade__in=YOUNG).update(grade='le7')
    UserProfile.objects.filter(grade__isnull=True).update(grade='')


def grade_to_numbers(apps, schema_editor):
    UserProfile = apps.get_model('problems', 'UserProfile')
    UserProfile.objects.filter(grade='le7').update(grade='7')
    UserProfile.objects.filter(grade__in=('none', '')).update(grade=None)


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0069_beta_profile_fields'),
    ]

    operations = [
        migrations.RunPython(grade_to_codes, grade_to_numbers),
    ]
