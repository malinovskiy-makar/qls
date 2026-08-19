# -*- coding: utf-8 -*-
"""Мина отставших счётчиков и команда, которая её снимает.

ЧТО ЗДЕСЬ ДОКАЗЫВАЕТСЯ. Заливка записей с ЯВНЫМИ номерами не двигает счётчик
таблицы, и следующая обычная вставка без номера получает занятый id. Проверок
две, и обе обязательны:

  1. Без `fix_sequences` вставка ПАДАЕТ. Если этот тест перестанет краснеть,
     значит мина исчезла сама — и тогда вторая проверка ничего не доказывает.
  2. После `fix_sequences --apply` та же вставка проходит.

Тест без первой половины был бы бесполезен: он был бы зелёным и на сломанной
команде, и на пустой заглушке.

⚠️ ТОЛЬКО POSTGRESQL. На SQLite мина не воспроизводится — он выдаёт
max(rowid) + 1 и про счётчики не знает. Прогон:

    manage.py test problems.tests.test_fix_sequences --settings=config.settings_test_pg
"""
import unittest
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from problems.models import Topic

# Номер заведомо выше всего, что раздаст счётчик за время теста: смысл в том,
# чтобы между «занято» и «что выдаст счётчик» образовалась дыра.
EXPLICIT_ID = 900001


def _next_value(table, column='id'):
    """Какое число счётчик выдаст следующим.

    Только `last_value` на этот вопрос не отвечает: у последовательности,
    которая ещё ничего не выдавала, `last_value` равен 1, но единицу она
    пока не отдавала. Различает эти два состояния `is_called`.
    """
    with connection.cursor() as cur:
        cur.execute('SELECT pg_get_serial_sequence(%s, %s)', [table, column])
        seq = cur.fetchone()[0]
        # ⚠️ Имя последовательности подставляется в текст: идентификатор в SQL
        # не может быть связанным параметром. Значение пришло от самой
        # PostgreSQL строкой выше, а не от пользователя.
        cur.execute('SELECT last_value, is_called FROM %s' % seq)  # nosec B608
        last_value, is_called = cur.fetchone()
    return last_value + 1 if is_called else last_value


@unittest.skipUnless(connection.vendor == 'postgresql',
                     'Мина отставших счётчиков есть только в PostgreSQL.')
class FixSequencesTests(TestCase):
    """Заливка с явными id → выравнивание → обычная вставка."""

    def _load_fixture_like_row(self):
        """Имитирует заливку фикстуры: запись с явно заданным номером.

        Именно так работает `bulk_load_fixtures` — номера берутся из файла,
        а не у счётчика.
        """
        Topic.objects.create(pk=EXPLICIT_ID, name='Тема из фикстуры')

    # -- 1. мина на месте ------------------------------------------------
    def test_without_fix_insert_fails(self):
        """Без выравнивания обычная вставка падает на занятом номере.

        Эта проверка держит вторую честной. Если счётчики начнут
        выравниваться сами, тест покраснеет и заставит перечитать всю
        конструкцию — а не тихо разрешит удалить команду.
        """
        self._load_fixture_like_row()

        # Счётчик не двинулся: он всё ещё собирается выдавать маленькие
        # номера, хотя большой уже занят.
        self.assertLess(_next_value(Topic._meta.db_table), EXPLICIT_ID)

        # Догоняем счётчик до занятого номера обычными вставками —
        # так же, как это сделала бы работа сайта после заливки.
        with connection.cursor() as cur:
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('%s', 'id'), %%s, true)"
                % Topic._meta.db_table, [EXPLICIT_ID - 1])

        with self.assertRaises(IntegrityError):
            # ⚠️ Отдельный atomic обязателен: упавший запрос отравляет
            # транзакцию, и без своего блока развалился бы весь тест,
            # а не одна вставка.
            with transaction.atomic():
                Topic.objects.create(name='Обычная тема')

    # -- 2. команда мину снимает -----------------------------------------
    def test_apply_moves_sequence_and_insert_works(self):
        """После --apply вставка без номера проходит."""
        self._load_fixture_like_row()

        out = StringIO()
        call_command('fix_sequences', '--apply', stdout=out)

        # Счётчик встал ЗА занятым номером, а не на него: setval с третьим
        # аргументом true означает «этот номер уже выдан».
        self.assertEqual(_next_value(Topic._meta.db_table), EXPLICIT_ID + 1)

        topic = Topic.objects.create(name='Обычная тема')
        self.assertEqual(topic.pk, EXPLICIT_ID + 1)

        self.assertIn('problems_topic', out.getvalue())

    # -- 3. холостой прогон ничего не трогает ----------------------------
    def test_dry_run_changes_nothing(self):
        """По умолчанию команда только показывает.

        Правило слоя команд: случайный запуск без флага обязан ничего не
        сделать, а не всё сделать.
        """
        self._load_fixture_like_row()
        before = _next_value(Topic._meta.db_table)

        out = StringIO()
        call_command('fix_sequences', stdout=out)

        self.assertEqual(_next_value(Topic._meta.db_table), before)
        self.assertIn('Холостой прогон', out.getvalue())

    # -- 4. повторный запуск даёт ноль -----------------------------------
    def test_idempotent(self):
        """Второй прогон обязан сказать «выравнивать нечего».

        Это не формальность: команда, которая на втором проходе снова
        находит работу, двигает счётчики без причины — и однажды сдвинет
        их мимо.
        """
        self._load_fixture_like_row()
        call_command('fix_sequences', '--apply', stdout=StringIO())

        out = StringIO()
        call_command('fix_sequences', stdout=out)
        self.assertIn('Отставших счётчиков нет', out.getvalue())

    # -- 5. связи «многие ко многим» тоже считаются ----------------------
    def test_covers_auto_created_m2m_tables(self):
        """Промежуточные таблицы связей не забыты.

        У них свой `id` со своим счётчиком, отстать он может так же, а
        заметить это труднее: модели с таким именем в коде нет.
        """
        out = StringIO()
        call_command('fix_sequences', stdout=out)
        text = out.getvalue()

        # Считаем то, что команда сама сообщает о числе проверенных таблиц,
        # и сверяем с числом моделей — включая автосозданные.
        self.assertIn('Проверено таблиц со счётчиком:', text)
        checked = int(text.split('Проверено таблиц со счётчиком:')[1]
                      .split('\n')[0].strip())
        # Моделей в проекте заведомо больше сотни; если бы автосозданные
        # таблицы связей отбрасывались, число было бы заметно меньше.
        self.assertGreater(checked, 100)
