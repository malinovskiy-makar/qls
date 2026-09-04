# -*- coding: utf-8 -*-
"""Код приглашения у занятия — в ТРИ ШАГА в одном файле.

⚠️ ОДНИМ ШАГОМ НЕЛЬЗЯ. Поле уникальное и обязательное; добавить его сразу
таким на таблицу, где строки уже есть, — значит попросить базу вписать во
все существующие занятия ОДНО И ТО ЖЕ значение по умолчанию и тут же
нарушить уникальность. Поэтому:

  1. добавляем поле, разрешая пустоту;
  2. `RunPython` раздаёт каждому занятию свой код;
  3. `AlterField` закрывает поле: `unique=True, null=False`.

Обратная операция у шага 2 — `noop`, и это осознанно: при откате шаг 3
превращает поле обратно в необязательное, а шаг 1 удаляет его целиком
вместе со значениями. Отдельно «расчищать» коды не нужно и негде.

Время выкатки: занятий в базе десятки, не тысячи — шаг 2 идёт мгновенно.
"""
from django.db import migrations, models


def fill_codes(apps, schema_editor):
    """Раздать каждому занятию свой код.

    ⚠️ Генератор берётся из `problems.models`, а НЕ переписывается здесь:
    две реализации одного алфавита разошлись бы при первой же правке, и
    разошлись бы молча. Модель через `apps.get_model` — историческая, но
    функция-генератор к состоянию схемы отношения не имеет.
    """
    from problems.models import make_invite_code

    StudentGroup = apps.get_model('problems', 'StudentGroup')
    used = set()
    for group in StudentGroup.objects.filter(invite_code__isnull=True):
        code = make_invite_code()
        while code in used:
            code = make_invite_code()
        used.add(code)
        group.invite_code = code
        group.save(update_fields=['invite_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('problems', '0050_userprofile_avatar_userprofile_level'),
    ]

    operations = [
        # Шаг 1: поле есть, пустота разрешена.
        #
        # ⚠️ БЕЗ `db_index` — И ЭТО НЕ МЕЛОЧЬ, А ОШИБКА, ПОЙМАННАЯ НА
        # POSTGRESQL. Для текстовой колонки с индексом PostgreSQL заводит
        # ВТОРОЙ, вспомогательный индекс `..._like` (varchar_pattern_ops).
        # Шаг 3 создаёт уникальный индекс и вместе с ним снова пытается
        # завести `..._like` — и падает с «relation … already exists».
        # На SQLite этого не видно вовсе: там нет ни таких индексов, ни
        # такой ошибки, и развёртывание с нуля проходило зелёным.
        # Индекс здесь и не нужен: между шагом 1 и шагом 3 по коду никто не
        # ищет, а шаг 3 всё равно строит уникальный индекс.
        migrations.AddField(
            model_name='studentgroup',
            name='invite_code',
            field=models.CharField(
                'Код приглашения', max_length=9, null=True, blank=True),
        ),
        # Шаг 2: у каждого занятия свой код.
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
        # Шаг 3: поле закрыто — уникальное и обязательное.
        migrations.AlterField(
            model_name='studentgroup',
            name='invite_code',
            field=models.CharField(
                'Код приглашения', max_length=9, unique=True, db_index=True,
                help_text='Формат XXXX-XXXX. Ученик вводит его на экране '
                          '«Занятия».'),
        ),
    ]
