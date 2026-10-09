"""Кнопка «Построить в «Графиках»»: выбор модели по тегам задачи (ADR 0145).

Таблицы `catalog/calc2_link.py` утверждены владельцем 10.10.2026. Здесь
сторожим три вещи: строки таблиц есть в `data/taxonomy.json` (опечатка
означала бы кнопку, которая не появится никогда), ключи и имена моделей
совпадают с `SCENE_NAMES` Графиков, и порядок выбора моделей.
"""
import io
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from catalog import calc2_link as L
from problems.models import Tag
from problems.tests.factories import make_problem, make_topic

TAXONOMY = json.loads((Path(settings.BASE_DIR) / 'data' / 'taxonomy.json').read_text(encoding='utf-8'))
WORKSPACE_JS = Path(settings.BASE_DIR) / 'calc2' / 'static' / 'calc2' / '86-workspace.js'


def scene_names():
    """`SCENE_NAMES` Графиков, прочитанный из файла текстом."""
    text = WORKSPACE_JS.read_text(encoding='utf-8')
    body = text[text.index('const SCENE_NAMES = {'):]
    body = body[:body.index('\n};')]
    return dict(re.findall(r"'?([\w-]+)'?:\s*'([^']*)'", body))


class TablesMatchDataTests(SimpleTestCase):

    def test_every_tag_row_is_in_taxonomy(self):
        tags = {name for theme in TAXONOMY['themes'] for name in theme['tags']}
        self.assertEqual([name for name in L.TAG_TO_MODEL if name not in tags], [])

    def test_every_topic_row_is_in_taxonomy(self):
        topics = {theme['name'] for theme in TAXONOMY['themes']}
        self.assertEqual([name for name in L.TOPIC_TO_MODEL if name not in topics], [])

    def test_every_model_is_a_scene_with_the_same_name(self):
        scenes = scene_names()
        used = set(L.TAG_TO_MODEL.values()) | set(L.TOPIC_TO_MODEL.values())
        self.assertEqual(sorted(k for k in used if k not in scenes), [])
        self.assertEqual(set(L.MODEL_NAMES), used)
        for key in used:
            self.assertEqual(L.MODEL_NAMES[key], scenes[key], key)

    def test_levels_name_real_models(self):
        used = set(L.TAG_TO_MODEL.values()) | set(L.TOPIC_TO_MODEL.values())
        self.assertLessEqual(L.BASE | L.GENERAL, used)
        self.assertFalse(L.BASE & L.GENERAL)


class ModelsForTests(SimpleTestCase):

    def test_single_specific_tag(self):
        self.assertEqual(L.models_for({'Потолок цены и его последствия'}, []), ['ceil'])

    def test_general_before_base(self):
        self.assertEqual(L.models_for({'Поиск рыночного равновесия',
                                       'Потоварный налог на продавца и на покупателя'}, []),
                         ['taxes', 'sd'])

    def test_specific_before_general(self):
        self.assertEqual(L.models_for({'Оптимум монополиста: MR = MC',
                                       'Ценовая дискриминация третьей степени по сегментам'}, []),
                         ['mono-d3', 'mono'])

    def test_two_at_most_table_order_breaks_ties(self):
        self.assertEqual(L.models_for({'Потолок цены и его последствия',
                                       'Квота, лицензирование и количественные ограничения',
                                       'Поиск рыночного равновесия'}, []),
                         ['ceil', 'quota'])

    def test_more_votes_win_inside_a_level(self):
        # Два тега за `ext`, один за `ceil`: обе частные, у `ext` больше голосов.
        self.assertEqual(L.models_for(['Потолок цены и его последствия',
                                       'Отрицательные внешние эффекты',
                                       'Положительные внешние эффекты'], []),
                         ['ext', 'ceil'])

    def test_topic_fallback_without_tags(self):
        self.assertEqual(L.models_for([], ['Вмешательство государства']), ['taxes'])

    def test_no_topic_fallback_when_tags_exist(self):
        self.assertEqual(L.models_for({'Прогрессивное и регрессивное налогообложение'},
                                      ['Вмешательство государства']), [])

    def test_oligopoly_tag_has_no_model(self):
        theme = next(t for t in TAXONOMY['themes'] if t['name'] == 'Олигополия и теория игр')
        self.assertEqual(L.models_for({theme['tags'][0]}, []), [])

    def test_nothing(self):
        self.assertEqual(L.models_for([], []), [])

    def test_url(self):
        self.assertEqual(L.calc2_url('mono-d3', 42), '/calc2/?m=mono-d3&from=42')


class CoverageCommandTests(TestCase):
    """`manage.py calc2_link_coverage`: верные числа на тестовых данных, записей 0."""

    def setUp(self):
        names = ('Потолок цены и его последствия', 'Поиск рыночного равновесия',
                 'Потоварный налог на продавца и на покупателя', 'Модель Курно: две фирмы')
        canon = {name: Tag.objects.create(name=name, slug='c%d' % i, kind='canonical')
                 for i, name in enumerate(names)}
        Tag.objects.create(name='монополия', slug='legacy-1', kind='legacy')
        state = make_topic('Вмешательство государства', is_canonical=True)
        make_problem('Потолок.').tags.add(canon['Потолок цены и его последствия'])
        both = make_problem('Налог и равновесие.')
        both.tags.add(canon['Поиск рыночного равновесия'],
                      canon['Потоварный налог на продавца и на покупателя'])
        make_problem('Курно.').tags.add(canon['Модель Курно: две фирмы'])
        make_problem('Только тема.', topic=state)
        make_problem('Ничего.').tags.add(Tag.objects.get(name='монополия'))
        make_problem('Скрытая.', flagged=True).tags.add(canon['Потолок цены и его последствия'])

    def test_numbers_and_no_writes(self):
        out = io.StringIO()
        with CaptureQueriesContext(connection) as ctx:
            call_command('calc2_link_coverage', stdout=out)
        text = out.getvalue()
        writes = [q['sql'] for q in ctx.captured_queries
                  if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])
        self.assertIn('Видимых задач: 5', text)
        self.assertIn('С каноническим тегом: 3', text)
        self.assertIn('С сопоставленным тегом: 2', text)
        self.assertIn('Кнопка по запасному пути темы: 1', text)
        self.assertIn('Теги есть, модели нет (кнопки нет): 1', text)
        self.assertIn('С кнопкой: 3 (60.0 %)', text)
        self.assertIn('С двумя моделями: 1', text)
        self.assertRegex(text, r'taxes\s+2\s+Налоги и субсидии')
        self.assertRegex(text, r'ceil\s+1\s+Пол и потолок цены')
        missing = len(L.TAG_TO_MODEL) - 3
        self.assertIn('Строк таблицы тегов нет среди канонических тегов базы: %d' % missing, text)
        self.assertIn('Порог выкатки 10 %: выкатываем.', text)
