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


def _sequence_name(table, column='id'):
    with connection.cursor() as cur:
        cur.execute('SELECT pg_get_serial_sequence(%s, %s)', [table, column])
        return cur.fetchone()[0]


def _reset_sequence(table, value, column='id'):
    """Ставит счётчик в заведомо известное состояние.

    ⚠️ ЗАЧЕМ ЭТО ВООБЩЕ НУЖНО — САМОЕ ВАЖНОЕ В ФАЙЛЕ. Счётчики в PostgreSQL
    НЕ ОТКАТЫВАЮТСЯ вместе с транзакцией, и это не оплошность, а устройство:
    иначе два одновременных клиента, получив номера, ждали бы друг друга.
    А `TestCase` откатывает каждый тест транзакцией — то есть строки
    исчезают, а сдвинутый счётчик остаётся.

    Итог: тесты этого класса влияют друг на друга, и порядок у них
    алфавитный. Первая версия файла на этом и попалась — проверка
    «без выравнивания вставка падает» получала счётчик, уже сдвинутый
    соседним тестом, и не падала. На SQLite такого не бывает.
    """
    with connection.cursor() as cur:
        # false третьим аргументом — «это значение ещё не выдавали»,
        # то есть следующим придёт ровно `value`.
        cur.execute('SELECT setval(%s, %s, false)',
                    [_sequence_name(table, column), value])


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

    # Низкое значение, с которого начинает каждый тест. Любое, лишь бы
    # заведомо меньше EXPLICIT_ID: смысл в дыре между «что выдаст счётчик»
    # и «что уже занято».
    START = 1000

    def setUp(self):
        # Счётчик транзакцией не откатывается — см. _reset_sequence.
        # Без этой строки тесты класса зависят от порядка запуска.
        _reset_sequence(Topic._meta.db_table, self.START)

    def _load_fixture_like_row(self):
        """Имитирует заливку фикстуры: запись с явно заданным номером.

        Именно так работает `bulk_load_fixtures` — номера берутся из файла,
        а не у счётчика.
        """
        # ⚠️ slug задаётся явно: поле уникальное, и две темы с пустым
        # slug роняют вставку раньше, чем дело дойдёт до проверяемого
        # счётчика — падение было бы не по той причине.
        Topic.objects.create(pk=EXPLICIT_ID, name='Тема из фикстуры',
                             slug='tema-iz-fikstury')

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

        # Догоняем счётчик до занятого номера — так же, как это сделала бы
        # обычная работа сайта после заливки: сотни новых тем, и однажды
        # счётчик доходит до номера, взятого из фикстуры.
        _reset_sequence(Topic._meta.db_table, EXPLICIT_ID)

        with self.assertRaises(IntegrityError):
            # ⚠️ Отдельный atomic обязателен: упавший запрос отравляет
            # транзакцию, и без своего блока развалился бы весь тест,
            # а не одна вставка.
            with transaction.atomic():
                Topic.objects.create(name='Обычная тема',
                                     slug='obychnaya-tema')

    # -- 2. команда мину снимает -----------------------------------------
    def test_apply_moves_sequence_and_insert_works(self):
        """После --apply вставка без номера проходит."""
        self._load_fixture_like_row()

        out = StringIO()
        call_command('fix_sequences', '--apply', stdout=out)

        # Счётчик встал ЗА занятым номером, а не на него: setval с третьим
        # аргументом true означает «этот номер уже выдан».
        self.assertEqual(_next_value(Topic._meta.db_table), EXPLICIT_ID + 1)

        topic = Topic.objects.create(name='Обычная тема',
                                     slug='obychnaya-tema')
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

        ⚠️ Ожидаемое число СЧИТАЕТСЯ ЗДЕСЬ ЖЕ, а не записано числом.
        Записанное число устаревает при первой новой модели, и тест
        начинает краснеть на пустом месте — а чинят такой тест правкой
        числа, не читая, что он проверял.
        """
        from django.apps import apps
        from django.db import models as dj_models

        def count_autofields(include_auto_created):
            total = 0
            for model in apps.get_models(
                    include_auto_created=include_auto_created):
                if model._meta.proxy or not model._meta.managed:
                    continue
                for field in model._meta.local_fields:
                    if isinstance(field, dj_models.AutoField):
                        total += 1
            return total

        plain = count_autofields(False)
        with_m2m = count_autofields(True)

        # Если этого не выполняется, у проекта не осталось ни одной связи
        # «многие ко многим», и проверять здесь стало нечего.
        self.assertGreater(with_m2m, plain,
                           'нет ни одной автосозданной таблицы связей')

        out = StringIO()
        call_command('fix_sequences', stdout=out)
        text = out.getvalue()

        self.assertIn('Проверено таблиц со счётчиком:', text)
        checked = int(text.split('Проверено таблиц со счётчиком:')[1]
                      .split('\n')[0].strip())
        # Команда обязана дойти до ВСЕХ таблиц, а не только до обычных
        # моделей: равенство с plain означало бы, что связи отброшены.
        self.assertEqual(checked, with_m2m)
