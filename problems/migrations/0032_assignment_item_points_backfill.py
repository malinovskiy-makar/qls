"""Явный максимальный балл у КАЖДОЙ позиции задания.

Поле `AssignmentItem.points` было и раньше, но у части позиций стояло пусто,
и тогда система молча считала такую задачу за ЕДИНИЦУ
(`assignment_rows.item_max_score`). Балл существовал, но его нельзя было
увидеть и нельзя было поправить.

Миграция проставляет пустым позициям РОВНО ТО ЧИСЛО, по которому они и так
считались, — единицу. Это перенос «как есть», а не переоценка: у уже
собранных заданий ни один максимум не меняется, сданные работы не съезжают.

Новые значения по умолчанию (10 задаче, 3 тесту) применяются только к
позициям, которые создадут ПОСЛЕ этой миграции — их проставляет
`AssignmentItem.save()`.
"""
from django.db import migrations


def fill_legacy_points(apps, schema_editor):
    AssignmentItem = apps.get_model('problems', 'AssignmentItem')
    AssignmentItem.objects.filter(points__isnull=True).update(points=1)


def unfill(apps, schema_editor):
    """Обратно ничего не чистим.

    Откат должен быть безопасным: мы не знаем, какие единицы стояли до
    миграции, а какие поставил репетитор руками уже после. Стирать чужой
    осознанный выбор ради симметрии нельзя.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0031_ai_usage_cache_tokens'),
    ]

    operations = [
        migrations.RunPython(fill_legacy_points, unfill),
    ]
