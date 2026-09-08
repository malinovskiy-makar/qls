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
from django.contrib.auth import get_user_model
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
        # Сводка собирается в ДВА приёма: `build_summary` (чистая функция
        # журнала) и `api_session_finish`, который дописывает зачётность —
        # её сводка знать не может, она решается при сохранении результата.
        served = set(views.build_summary(state).keys())
        served |= set(views.FINISH_EXTRA_FIELDS)
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

    def test_sharing_is_one_button_with_one_path(self):
        """⚠️ ОДНА КНОПКА (08.09.2026, решение владельца).

        Было четыре: «картинкой», «сторис», «скопировать ссылку» и
        системное «Поделиться». Вместе с ними удалено рисование карточки на
        canvas — всё, что было на картинке, есть на публичной странице
        результата, и она к тому же живая. Прежний тест сторожил ловушку
        Web Share «files рядом с text/url» — файлов больше нет вовсе, и
        сторожить нечего.
        """
        for gone in ('btn-share-img', 'btn-share-story', 'btn-share-link',
                     'btn-share-native', 'share-canvas', 'drawShareCard',
                     'shareCard', 'downloadCard', 'CARD_SIZES', 'CARD_LAYOUT',
                     'cardFont', 'withFonts', 'drawCurve', 'drawHearts',
                     'drawDonut', 'drawRecordRibbon'):
            self.assertNotIn(gone, self.src, gone)

        self.assertEqual(self.src.count('id="btn-share"'), 1)
        # Ни одного share с файлом не осталось: файлов нет.
        self.assertNotIn('files:', self.js)

    def test_the_one_button_walks_three_steps_down(self):
        """Системное окно → буфер → prompt. Ссылку скопировать можно всегда."""
        m = re.search(
            r"\$\('btn-share'\)\.addEventListener\('click', function \(\) \{(.*?)\n  \}\);",
            self.js, re.S)
        self.assertIsNotNone(m, 'обработчик btn-share не найден')
        handler = m.group(1)
        self.assertIn('navigator.share', handler)
        self.assertIn('shareText()', handler)
        self.assertIn('navigator.clipboard', handler)
        self.assertIn('prompt(', handler)

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


class SoundCheckPanelTests(TestCase):
    u"""Панель прослушивания звука: служебная, только staff и только по флагу.

    Нужна для приёмки НА СЛУХ: иначе, чтобы услышать «жизнь», надо трижды
    ошибиться, а чтобы услышать «рекорд» — сначала его поставить.
    """

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user('st', password='x',
                                              is_staff=True)
        self.plain = User.objects.create_user('pl', password='x')

    def test_absent_without_the_flag(self):
        self.client.force_login(self.staff)
        html = self.client.get('/game/').content.decode()
        self.assertNotIn('id="sound-check"', html)
        self.assertNotIn('data-sound=', html)

    def test_absent_for_anonymous_even_with_the_flag(self):
        html = self.client.get('/game/?sound_check=1').content.decode()
        self.assertNotIn('id="sound-check"', html)
        self.assertNotIn('data-sound=', html)

    def test_absent_for_a_plain_user_with_the_flag(self):
        u"""Флаг в адресе не даёт прав: панель служебная."""
        self.client.force_login(self.plain)
        html = self.client.get('/game/?sound_check=1').content.decode()
        self.assertNotIn('id="sound-check"', html)
        self.assertNotIn('data-sound=', html)

    def test_present_for_staff_with_the_flag(self):
        self.client.force_login(self.staff)
        html = self.client.get('/game/?sound_check=1').content.decode()
        self.assertIn('id="sound-check"', html)
        for name in ('correct', 'wrong', 'lifeLost', 'record'):
            self.assertIn('data-sound="%s"' % name, html)
        for bpm in ('70', '130', 'stop'):
            self.assertIn('data-hb="%s"' % bpm, html)


class StartScreenShareCardTests(TestCase):
    u"""Карточка ссылки есть и у стартового экрана, не только у результата."""

    def test_open_graph_tags_are_present(self):
        html = self.client.get('/game/').content.decode()
        self.assertIn('property="og:image"', html)
        self.assertIn('game/og_default.png', html)
        self.assertIn('Wecon Rush', html)
        self.assertIn('property="og:image:width" content="1200"', html)


class NoBrowserBlueTests(TestCase):
    u"""Ни одной ссылки и ни одного поля без своего цвета (08.09.2026).

    ⚠️ ЧТО БЫЛО. `game.html` — самостоятельный шаблон, а не наследник
    базового, и правил для `<a>` на нём не было вовсе: две ссылки в строке
    под режимами («Вызов дня», «Дуэль с другом») браузер красил системным
    синим. Рядом `#code-input` и `#duel-link` не имели `:focus`, и Safari
    обводил их своей синей рамкой. Владелец назвал это «странными синими
    кнопками» — кнопок там нет вовсе.
    """

    # Селектор поля → селектор, под которым живёт правило фокуса. Список
    # ведётся руками намеренно: новое поле обязано попасть сюда вместе с
    # правилом, а не тихо приехать с браузерным синим.
    INPUT_RULES = {
        '.code-form input': '.code-form input:focus',
        '.duel-lobby__row input': '.duel-lobby__row input:focus',
        '.num-input': '.num-input:focus',
        '.tag-search': '.tag-search:focus',
        '.fmodal input': '.fmodal input:focus-visible',
    }

    def setUp(self):
        self.src = page_source()

    def test_links_inside_the_game_have_their_own_colour(self):
        self.assertIn(':where(.rush-wrap a) { color: var(--rush-accent)',
                      self.src)
        self.assertIn(':where(.rush-wrap a:hover)', self.src)

    def test_the_link_rule_does_not_repaint_links_that_have_a_colour(self):
        u"""⚠️ Обёртка :where() обязательна — она и есть смысл правила.

        Без неё `.rush-wrap a` весит (0,1,1) и перебивает `.set-back`,
        `.btn-board`, `.btn-copy` (0,1,0): четыре ссылки со своим осмысленным
        цветом перекрасились бы заодно. Нужен ЗАПАСНОЙ цвет, а не общий.
        """
        self.assertNotIn('\n.rush-wrap a {', self.src)
        for rule in ('.set-back { color: var(--text3); }',
                     '.btn-board:hover { border-color: var(--rush-accent)',
                     '.btn-copy:hover { border-color: var(--rush-accent)'):
            self.assertIn(rule, self.src)

    def test_the_code_field_has_a_focus_rule(self):
        self.assertIn('.code-form input:focus', self.src)
        block = self.src.split('.code-form input:focus,', 1)[1]
        block = block.split('}', 1)[0]
        self.assertIn('var(--rush-accent)', block)

    def test_every_input_selector_has_a_focus_rule(self):
        u"""Числовой инвариант фазы: полей без правила фокуса — ноль.

        Собираем классы всех `<input` разметки, сводим к селектору, под
        которым поле стилизуется, и сверяем со списком правил `:focus`.
        Расхождение печатается поимённо: «каких не хватает» важнее, чем
        «сколько».
        """
        # Классы всех полей ввода в разметке.
        classes = set()
        ids = set()
        for tag in re.findall(r'<input\b[^>]*>', self.src):
            for cls in re.findall(r'class="([^"]+)"', tag):
                classes.update(cls.split())
            ids.update(re.findall(r'id="([^"]+)"', tag))

        # Каждое поле обязано попасть под один из известных селекторов.
        known = {'f-topic', 'f-source', 'f-feature', 'f-character',
                 'tag-search', 'num-input'}
        unknown = classes - known
        self.assertEqual(unknown, set(),
                         'поля с неизвестным классом: %s' % sorted(unknown))

        known_ids = {'code-input', 'duel-link', 'dm-link',
                     'num-input', 'tag-search'}
        self.assertEqual(ids - known_ids, set(),
                         'поля с неизвестным id: %s' % sorted(ids - known_ids))

        missing = [sel for sel, rule in self.INPUT_RULES.items()
                   if rule not in self.src]
        self.assertEqual(missing, [],
                         'нет правила фокуса у: %s' % missing)


class OneShareButtonEverywhereTests(TestCase):
    u"""Кнопка шеринга ровно одна — и в игре, и на публичной странице.

    Решение владельца 08.09.2026: остаётся одна кнопка «Поделиться»,
    ведущая на публичную страницу результата `/game/r/<код>/`. Рисование
    карточки на canvas удалено.

    ⚠️ Проверяются ОБА шаблона одним тестом: пара «Скопировать ссылку» /
    «Поделиться» на `result.html` — та же кнопка в другом месте, и оставь
    её там — у одного действия стало бы два разных поведения.
    """

    RESULT = os.path.join(settings.BASE_DIR, 'game', 'templates', 'game',
                          'result.html')

    def setUp(self):
        self.page = page_source()
        with open(self.RESULT, encoding='utf-8') as f:
            self.result = f.read()

    def test_exactly_one_share_button_in_each_template(self):
        for name, src in (('game.html', self.page),
                          ('result.html', self.result)):
            buttons = re.findall(r'<button[^>]*id="btn-share[^"]*"', src)
            self.assertEqual(len(buttons), 1, '%s: %s' % (name, buttons))
            self.assertNotIn('id="btn-copy"', src, name)

    def test_no_card_words_and_no_canvas(self):
        for name, src in (('game.html', self.page),
                          ('result.html', self.result)):
            # ⚠️ Слово «картинкой» ищем как ПОДПИСЬ КНОПКИ, а не в тексте:
            # в комментариях страницы «объясняется картинкой» встречается
            # трижды и к шерингу отношения не имеет.
            self.assertNotIn('>Поделиться картинкой<', src, name)
            self.assertNotIn('сторис)<', src, name)
            self.assertNotIn('<canvas id="share-canvas"', src, name)

    def test_nothing_draws_on_a_canvas_in_the_share_block(self):
        u"""Числовой инвариант фазы — замер, а не потолок файла.

        Рисование карточки заняло 288 строк (5613 → 5325 по git на момент
        правки), и это записано здесь как факт. Сторожить сам ПОТОЛОК файла
        числом нельзя: следующая же фаза добавила бы строк, тест покраснел
        бы не по делу, и его пришлось бы подкручивать — то есть он перестал
        бы что-либо проверять. Проверяем то, что не должно вернуться:
        никакого холста и никакого рисования в блоке шеринга.
        """
        self.assertNotIn('<canvas id="share-canvas"', self.page)
        self.assertNotIn("getContext('2d')", self.page.split(
            '---------- ШЕРИНГ ----------', 1)[1].split(
            '---------- ПОДРОБНАЯ СТАТИСТИКА', 1)[0])


class ScoreboardTests(TestCase):
    u"""Табло: вы, разрыв, вторая сторона (08.09.2026).

    ⚠️ ОДНА ВЁРСТКА НА ДВА СЛУЧАЯ. Прежняя `.duel-bar` показывала одну
    строку про соперника и ни одного своего числа: сравнивать было не с
    чем. Теперь слева всегда «вы», посередине разрыв, справа в дуэли
    соперник, в обычном забеге личный рекорд. Второго вида табло нет.
    """

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    def test_the_old_one_line_bar_is_gone(self):
        u"""⚠️ Ищем СЕЛЕКТОРЫ и id, а не слово: комментарий у новой вёрстки
        объясняет, что и почему заменило `.duel-bar`, и проверка по слову
        краснела бы на объяснении."""
        for gone in ('.duel-bar {', 'class="duel-bar', '.duel-bar__',
                     'id="duel-score"', 'id="duel-correct"',
                     'id="duel-lives"', 'id="duel-state"', 'id="duel-who"'):
            self.assertNotIn(gone, self.src, gone)

    def test_one_markup_serves_both_cases(self):
        u"""Блок `.vs` в разметке ровно один: второго вида табло нет."""
        self.assertEqual(self.src.count('<div class="vs" id="vs"'), 1)
        self.assertIn('function isDuelRun()', self.js)
        # Обе ветки правой карточки ходят через один и тот же блок.
        self.assertIn('if (isDuelRun()) { paintRival(); } else { paintBest(); }',
                      self.js)

    def test_the_rival_clock_keeps_running_between_events(self):
        u"""⚠️ Событие приходит только на ОТВЕТ соперника.

        Думает он полминуты — все его числа стоят, а время течёт. Клиент
        обязан продолжать отсчёт сам: запомнить `seconds_left` и серверную
        метку `at`, дальше вычитать разницу СВОИХ часов. Присвоения
        пришедшего значения мало — это и проверяем.
        """
        m = re.search(r'function rivalSeconds\(\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m, 'rivalSeconds не найден')
        body = m.group(1)
        self.assertIn('Date.now() - vsRivalAt', body)
        self.assertIn('vsRival.seconds_left - gone', body)
        # Метку ставит приход события, а не отрисовка.
        self.assertIn('vsRivalAt = Date.now();', self.js)
        # Рисует игровой цикл: время идёт кадрами, а не событиями.
        self.assertRegex(self.js, r'paintAlarm\(\);\s*\n(?:\s*//[^\n]*\n)*\s*paintVs\(\);')

    def test_a_finished_or_absent_rival_stops_the_clock(self):
        u"""Досчитывать финишировавшего до нуля значит показывать неправду."""
        self.assertIn('vsRivalDone = true;', self.js)
        self.assertIn('if (vsRivalDone) return 0;', self.js)

    def test_without_a_record_the_right_card_has_no_number(self):
        u"""Первый раунд в режиме: выдуманного числа-заглушки быть не должно."""
        m = re.search(r'function paintBest\(\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m, 'paintBest не найден')
        branch = m.group(1).split('if (!vsBest) {', 1)[1].split('return;', 1)[0]
        self.assertIn("$('vs-them-score').textContent = '';", branch)
        self.assertIn('Первый раунд в этом режиме', branch)
        self.assertIn('Войдите, чтобы рекорды сохранялись', branch)
        # Ни одной цифры в ветке «рекорда нет».
        self.assertNotRegex(branch, r'\d')

    def test_the_gap_disappears_when_there_is_nothing_to_compare(self):
        m = re.search(r'function paintGap\(\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('if (other == null) { gap.hidden = true; return; }', body)
        self.assertIn('вы ведёте', body)
        self.assertIn('отстаёте', body)

    def test_the_record_comes_from_the_server_not_from_local_storage(self):
        u"""Рекорды не должны теряться при смене браузера."""
        self.assertIn('vsBest = d.best || null;', self.js)
        m = re.search(r'function paintBest\(\) \{(.*?)\n  \}', self.js, re.S)
        self.assertNotIn('localStorage', m.group(1))

    def test_lives_are_still_drawn_from_config(self):
        u"""Тест механики не обойдён новой вёрсткой: запас жизней из CFG."""
        m = re.search(r'function livesHtml\(n\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m, 'livesHtml не найден')
        body = m.group(1)
        self.assertIn('m.lives', body)
        self.assertNotRegex(body, r'i < 3;')
