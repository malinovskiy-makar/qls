"""
Статические тесты страницы игры.

Инлайн-скрипт game.html — полторы тысячи строк, которых не видит ни
`manage.py check`, ни рендер шаблона: страница отдаёт 200 с любой опечаткой
в JS, а ломается уже в браузере у игрока. Тут ловим ровно этот класс:
- скрипт вообще парсится (node --check);
- каждый getElementById имеет элемент с таким id в разметке;
- каждое поле сводки, которое читает клиент, сервер действительно кладёт
  (иначе на экране результатов молча появится «undefined»);
- мёртвых переменных и функций не осталось.

Тот же приём, что у «Штриха» (shtrikh/tests/test_page_js.py).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase

TEMPLATE = os.path.join(
    settings.BASE_DIR, 'game', 'templates', 'game', 'game.html')

# Заглушка конфига вместо {{ config_json|safe }} — форма как у _mode_payload.
FAKE_CONFIG = (
    '{"modes":{"blitz":{"key":"blitz","title":"Блиц","question_type":"single",'
    '"duration":120,"time_correct":5,"time_wrong":0,"time_skip":0,"lives":3}},'
    '"default_mode":"blitz","pool_counts":{"blitz":10},"base_points":100,'
    '"combo_steps":[[9,4],[6,3],[3,2]],"mistakes_run_size":10,'
    '"difficulty_min":1,"difficulty_max":5,'
    '"topic_groups":[{"key":"micro","title":"Микро","topics":["Эластичность"]}],'
    '"source_groups":[{"key":"vsosh","title":"ВсОШ"}],'
    '"has_daily":false,"has_duel":false}'
)


def page_source():
    with open(TEMPLATE, encoding='utf-8') as f:
        return f.read()


def inline_js(src):
    """Инлайн-скрипт страницы с подставленным конфигом."""
    m = re.search(r'<script>\n(.*?)\n</script>', src, re.S)
    assert m, 'инлайн-скрипт не найден'
    js = m.group(1).replace('{{ config_json|safe }}', FAKE_CONFIG)
    # Забег по набору: на обычной странице сервер кладёт сюда null.
    return js.replace('{{ auto_set_json|safe }}', 'null')


class PageJsTests(TestCase):

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    @unittest.skipIf(shutil.which('node') is None, 'node не установлен')
    def test_inline_script_parses(self):
        """node --check: опечатку в JS рендер шаблона не заметит."""
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(self.js)
            path = f.name
        try:
            p = subprocess.run(['node', '--check', path],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.unlink(path)

    def test_every_getElementById_has_an_element(self):
        """$('id') без элемента в разметке = молчаливый null и падение."""
        ids_html = set(re.findall(r'id="([^"]+)"', self.src))
        ids_js = set(re.findall(r"\$\('([^']+)'\)", self.js))
        self.assertEqual(sorted(ids_js - ids_html), [])

    def test_summary_fields_read_by_client_are_sent_by_server(self):
        """Клиент читает сводку по именам полей — сверяем с build_summary.

        Разъехавшееся имя даёт «undefined» на экране результатов, и ни
        один питон-тест этого не увидит."""
        from game import views
        state = {'mode': 'blitz', 'topic': None, 'seen': [], 'answered': {},
                 'lives': 3, 'score': 0, 'streak': 0, 'best_streak': 0,
                 'ended': None, 'log': []}
        served = set(views.build_summary(state).keys())
        # поля, которые клиент берёт у сводки: s.<имя>
        read = set(re.findall(r'\bs\.([a-z_]+)\b', self.js))
        # offline — поле запасной сводки клиента, сервер его не шлёт
        read.discard('offline')
        self.assertEqual(sorted(read - served), [])

    def test_no_dead_functions(self):
        """Объявленная и никем не вызванная функция — недоделка или мусор."""
        declared = set(re.findall(r'\n  function ([a-zA-Z_]\w*)\(', self.js))
        dead = []
        for name in declared:
            # объявление + хотя бы одно упоминание где-то ещё
            uses = len(re.findall(r'\b%s\b' % re.escape(name), self.js))
            if uses < 2:
                dead.append(name)
        self.assertEqual(sorted(dead), [])

    def test_image_share_sends_only_the_file(self):
        """Кнопка «Поделиться картинкой» отдаёт в share ТОЛЬКО файл.

        Если рядом с files положить text/url, системное окно «Поделиться»
        на десктопе берёт текст и ВЫБРАСЫВАЕТ картинку — кнопка начинает
        делиться подписью вместо карточки. Ровно этот баг ловили в браузере
        2026-07-16: уходило {files, text, url}. Ссылка не теряется — она
        нарисована на самой карточке и живёт на соседних кнопках."""
        calls = re.findall(r'navigator\.share\(\{(.*?)\}\)', self.js, re.S)
        with_files = [c for c in calls if 'files' in c]
        self.assertEqual(len(with_files), 1,
                         'ожидался ровно один share с файлом')
        self.assertNotIn('text:', with_files[0])
        self.assertNotIn('url:', with_files[0])

    def test_image_button_falls_back_to_download_not_text(self):
        """Запасной путь кнопки-картинки — скачивание PNG, никогда не текст.

        Нажали «картинкой» — получите картинку: текст и ссылка живут на
        своих кнопках."""
        # обе кнопки карточки (широкая и вертикальная) ходят через один
        # shareCard — запасной путь у них общий
        m = re.search(r'function shareCard\(btn, kind, label\) \{(.*?)\n  \}\n',
                      self.js, re.S)
        self.assertIsNotNone(m, 'shareCard не найден')
        handler = m.group(1)
        self.assertIn('downloadCard', handler)
        self.assertNotIn('shareText', handler)
        for btn in ('btn-share-img', 'btn-share-story'):
            self.assertRegex(
                self.js,
                r"\$\('%s'\)\.addEventListener\('click', function \(\) \{\s*"
                r"shareCard\(" % btn)

    def test_filter_state_is_persisted_and_sent(self):
        """Фильтр живёт в localStorage и уезжает на сервер — иначе выбор
        игрока сбрасывался бы на каждом «сыграть ещё раз»."""
        self.assertIn("var FILTER_KEY = 'econ_rush_filter';", self.js)
        self.assertIn('filterQuery()', self.js)
        self.assertIn('localStorage.setItem(FILTER_KEY', self.js)

    def test_all_four_endings_have_their_own_text(self):
        """Развилка исходов забега четырёхветочная: lives / time /
        pool_empty / set_done. Пропущенная ветка молча показала бы
        «время вышло» там, где время не при чём."""
        # ⚠️ Строку причины в углу шапки результатов владелец убрал
        # (сессия «Wecon Rush», 1.12) вместе с функцией `reasonText`.
        # Развилка исходов при этом обязана остаться четырёхветочной —
        # теперь её сторожит только заголовок.
        self.assertNotIn('function reasonText', self.js)
        m2 = re.search(r'function titleText\(s\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m2)
        for reason in ('lives', 'set_done', 'pool_empty'):
            self.assertIn("'%s'" % reason, m2.group(1))

    def test_clean_badge_requires_at_least_one_correct_answer(self):
        """«Чисто! Ошибок нет» ошибочно показывалась и при 0/0 (пустой
        забег из нуля вопросов) — s.wrong > 0 у пустого забега тоже false.
        Ловим регрессию: условие обязано требовать s.correct > 0."""
        m = re.search(r'var clean = (.*?);', self.js)
        self.assertIsNotNone(m, 'условие clean не найдено')
        self.assertIn('s.correct > 0', m.group(1))

    def test_start_refusal_shows_a_calm_banner_not_an_alert(self):
        """Отказ сервера начать забег (режим за флагом, пустой пул под
        фильтром — Задачи 2 и 3) — спокойная строка на стартовом экране,
        а не alert() и не переход на игровой экран."""
        # ни одного ИСПОЛНЯЕМОГО вызова alert( — только упоминания в
        # комментариях (тексте самого регресс-теста этой ошибки).
        code_alerts = [line for line in self.js.splitlines()
                      if 'alert(' in line and not line.strip().startswith(('*', '//'))
                      and 'НЕ alert' not in line and 'не alert' not in line]
        self.assertEqual(code_alerts, [])
        self.assertIn('showStartNotice', self.js)
        self.assertIn('hideStartNotice', self.js)
        m = re.search(r'if \(!d\.ok\) \{ showStartNotice\(', self.js)
        self.assertIsNotNone(m, 'startRun не показывает баннер на !d.ok')

    def test_mechanics_numbers_come_from_config(self):
        """Числа механики клиент не выдумывает: 3 жизни и размер целевого
        забега приходят из config.py, а не написаны в шаблоне руками."""
        self.assertIn('CFG.mistakes_run_size', self.js)
        self.assertIn('MODE.lives', self.js)
        # запас жизней не захардкожен в отрисовке сердец
        self.assertNotRegex(self.js, r'for \(var i = 0; i < 3;')


class FigureModuleTests(TestCase):
    """Модуль чертежей — общий у страницы игры и HTML-предпросмотра.

    Он вынесен в static именно ради этого: второй рисователь «только для
    превью» разошёлся бы с боевым, и преподаватель смотрел бы не то, что
    увидит игрок. Тесты держат эту связку.
    """
    JS = os.path.join(settings.BASE_DIR, 'game', 'static', 'game', 'figure.js')
    CSS = os.path.join(settings.BASE_DIR, 'game', 'static', 'game', 'figure.css')

    @unittest.skipIf(shutil.which('node') is None, 'node не установлен')
    def test_figure_js_parses(self):
        p = subprocess.run(['node', '--check', self.JS],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_figure_js_exposes_only_draw_figure(self):
        """Наружу торчит одна функция: остальное — в замыкании."""
        with open(self.JS, encoding='utf-8') as f:
            src = f.read()
        self.assertIn('window.drawFigure = drawFigure;', src)
        self.assertEqual(len(re.findall(r'\bwindow\.\w+\s*=', src)), 1)

    def test_game_page_includes_the_module(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            src = f.read()
        self.assertIn("{% static 'game/figure.js' %}", src)
        self.assertIn("{% static 'game/figure.css' %}", src)
        self.assertIn('{% load static %}', src)

    def test_preview_command_inlines_the_same_module(self):
        """Предпросмотр инлайнит те же файлы, а не свою копию."""
        from game.management.commands import preview_generated as cmd
        with open(cmd.__file__, encoding='utf-8') as f:
            src = f.read()
        # вызов может быть перенесён по строкам — ищем с учётом переносов
        self.assertRegex(src, r"_read_static\(\s*'figure\.js'\s*\)")
        self.assertRegex(src, r"_read_static\(\s*'figure\.css'\s*\)")
        # своей копии рисователя у превью быть не должно
        self.assertNotIn('function drawFigure', src)

    def test_roles_of_python_schema_are_known_to_the_renderer(self):
        """Каждая роль из _figure.ROLES имеет цвет у рисователя.

        Разъехались — питон отдаст роль, которой рисователь не знает, и
        кривая молча уедет в цвет «ghost»."""
        from game.generators import _figure
        with open(self.JS, encoding='utf-8') as f:
            src = f.read()
        block = re.search(r'var FIG_ROLES = \{(.*?)\};', src, re.S).group(1)
        known = set(re.findall(r'(\w+)\s*:', block))
        self.assertEqual(sorted(set(_figure.ROLES) - known), [])
