# -*- coding: utf-8 -*-
"""Сторож бага 07.09: в поле записано ИМЯ ПОЛЯ вместо значения.

Баг стоил дорого не сам по себе, а тем, что был НЕВИДИМ: `merge_enrichment_v2`
считал покрытие как `exclude(title_candidate='')`, а литерал `'title_candidate'`
— непустая строка, и 882 задачи прошли как «покрыты». Поэтому сторож проверяет
не «поле непусто», а «поле не равно своему имени».

Причина бага разобрана в шапке `clear_field_name_values`: перестройка таблицы
SQLite, когда колонка есть в состоянии модели, но её нет в физической таблице.
Здесь это воспроизведено отдельным тестом — иначе объяснение осталось бы
словами.
"""
import sqlite3

from django.core.management import call_command
from django.test import TestCase

from problems.management.commands.clear_field_name_values import FIELDS, broken_ids
from problems.models import Problem


class FieldNameGuardTests(TestCase):
    """Сторож: ни у одной задачи значение поля не равно имени этого поля."""

    def test_чистая_база_сторожем_не_краснеет(self):
        Problem.objects.create(statement='Условие.', title='Монополия',
                               title_candidate='Монополия и налог',
                               title_source='kept')
        for поле in FIELDS:
            self.assertEqual(broken_ids(поле), [])

    def test_сторож_смотрит_на_все_четыре_поля(self):
        """Список полей закреплён отдельно, а не только перебирается ниже:
        тест, который сам ходит по `FIELDS`, при сужении списка стал бы
        пустым и остался зелёным — то есть перестал быть тестом."""
        self.assertEqual(set(FIELDS), {'title_candidate', 'title_source',
                                       'enrichment_source', 'text_quality'})

    #: Поля, куда имя поля физически ВЛЕЗАЕТ. `enrichment_source` — это
    #: `CharField(max_length=8)`, а само имя длиной 17: PostgreSQL такую
    #: строку не принимает вовсе (`value too long for type character
    #: varying(8)`), SQLite принимает молча. Список закреплён здесь, а не
    #: вычисляется на лету рядом с проверкой: сузят колонку — тест назовёт
    #: расхождение, а не подстроится под него.
    ПОЛЯ_ГДЕ_БАГ_ВОЗМОЖЕН = {'title_candidate', 'title_source', 'text_quality'}

    def test_длина_колонки_решает_где_баг_вообще_возможен(self):
        """Свидетельство под списком выше: сверяем его с самой схемой."""
        влезает = {поле for поле in FIELDS
                   if Problem._meta.get_field(поле).max_length >= len(поле)}
        self.assertEqual(влезает, self.ПОЛЯ_ГДЕ_БАГ_ВОЗМОЖЕН)

    def test_сторож_ловит_имя_поля_в_каждом_поле_куда_оно_влезает(self):
        """Тест обязан краснеть, пока баг в базе. Проверяется по одному полю
        за раз: сторож, который смотрит только на `title_candidate`, пропустил
        бы повтор той же ошибки на соседнем поле.

        ⚠️ ЗАПИСЬ ИДЁТ НЕ ВО ВСЕ ЧЕТЫРЕ ПОЛЯ, И ЭТО НЕ ПОСЛАБЛЕНИЕ. В
        `enrichment_source` имя поля не помещается по длине колонки —
        значит, и баг там завестись не может; проверяем, что сторож на
        таком поле молчит. Раньше тест пытался записать туда имя, на
        SQLite это проходило, а на PostgreSQL роняло вставку И ЛОМАЛО
        ТРАНЗАКЦИЮ, из-за чего краснело заодно следующее поле.
        """
        for поле in FIELDS:
            with self.subTest(поле=поле):
                if поле not in self.ПОЛЯ_ГДЕ_БАГ_ВОЗМОЖЕН:
                    self.assertEqual(broken_ids(поле), [])
                    continue
                p = Problem.objects.create(statement='Условие.', **{поле: поле})
                self.assertEqual(broken_ids(поле), [p.id])
                p.delete()

    def test_команда_чистит_и_revert_возвращает(self):
        p = Problem.objects.create(statement='Условие.',
                                   title_candidate='title_candidate',
                                   title_source='title_source')
        путь = str(self._снимок())
        call_command('clear_field_name_values', '--apply', '--snapshot', путь)
        p.refresh_from_db()
        self.assertEqual(p.title_candidate, '')
        self.assertEqual(p.title_source, '')

        call_command('clear_field_name_values', '--revert', '--apply',
                     '--snapshot', путь)
        p.refresh_from_db()
        self.assertEqual(p.title_candidate, 'title_candidate')
        self.assertEqual(p.title_source, 'title_source')

    def test_без_apply_база_не_меняется(self):
        p = Problem.objects.create(statement='Условие.',
                                   title_candidate='title_candidate')
        call_command('clear_field_name_values')
        p.refresh_from_db()
        self.assertEqual(p.title_candidate, 'title_candidate')

    def test_чистка_не_трогает_соседние_задачи(self):
        плохая = Problem.objects.create(statement='Раз.',
                                        title_candidate='title_candidate')
        хорошая = Problem.objects.create(statement='Два.',
                                         title_candidate='Дуополия Курно',
                                         title_source='kept')
        call_command('clear_field_name_values', '--apply',
                     '--snapshot', str(self._снимок()))
        плохая.refresh_from_db()
        хорошая.refresh_from_db()
        self.assertEqual(плохая.title_candidate, '')
        self.assertEqual(хорошая.title_candidate, 'Дуополия Курно')
        self.assertEqual(хорошая.title_source, 'kept')

    def _снимок(self):
        import tempfile
        import os
        return os.path.join(tempfile.mkdtemp(), 'snapshot.json')


class SqliteRemakeTableTests(TestCase):
    """Как именно имя колонки попало в данные — воспроизведение, а не версия.

    Django при `AddField` пересоздаёт таблицу SQLite и переносит данные
    запросом `INSERT INTO new (...) SELECT "col", ... FROM old`, где список
    колонок берётся из СОСТОЯНИЯ МОДЕЛИ. Колонки нет в старой таблице —
    SQLite по legacy-правилу считает двойные кавычки строковым литералом и
    молча заливает имя колонки во все строки.
    """

    def test_двойные_кавычки_становятся_строкой_если_колонки_нет(self):
        conn = sqlite3.connect(':memory:')
        conn.executescript(
            'CREATE TABLE old_t (id INTEGER PRIMARY KEY, title TEXT NOT NULL);'
            "INSERT INTO old_t VALUES (1, 'Монополия');"
            'CREATE TABLE new_t (id INTEGER PRIMARY KEY, title TEXT NOT NULL,'
            ' title_candidate varchar(60) NOT NULL);')
        conn.execute('INSERT INTO new_t (id, title, title_candidate) '
                     'SELECT "id", "title", "title_candidate" FROM old_t')
        строка = conn.execute('SELECT title, title_candidate FROM new_t').fetchone()
        conn.close()
        self.assertEqual(строка, ('Монополия', 'title_candidate'))
