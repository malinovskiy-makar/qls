# -*- coding: utf-8 -*-
"""Тексты, знак и экраны Wecon Rush (сессия «Wecon Rush», фаза 1).

Здесь ловится класс «текст поправили в одном месте из двух»: знак набран
картинкой, а не буквами; пункт навигации переименован везде; нативного
диалога на странице нет; подсказка клавиш своя на каждый тип вопроса.

Проверки статические — по исходнику страницы. Инлайн-скрипт game.html
Django не видит, и опечатка в нём отдаёт честные 200 с поломанной игрой.
"""
import io
import re

from django.test import TestCase
from django.urls import reverse

PAGE = 'game/templates/game/game.html'
LOGO = 'templates/_rush_logo.html'
ICONS = 'templates/_icons.html'
NAV = 'templates/_nav.html'


def read(path):
    return io.open(path, encoding='utf-8').read()


class LogoMarkTests(TestCase):
    u"""1.1 «W» — фирменный знак картинкой, а не буква."""

    def setUp(self):
        self.src = read(LOGO)

    def test_mark_is_an_svg_not_a_letter(self):
        self.assertIn('<svg class="w-mark"', self.src)
        self.assertIn('fill="currentColor"', self.src)
        # Слово начинается со знака и сразу переходит в «ECON»: WECON —
        # одно слово, зазору там взяться неоткуда.
        self.assertIn('</svg>ECON', self.src)

    def test_viewbox_is_the_tight_bbox_not_the_circle(self):
        u"""viewBox круга (460.43 307.18 523.88 523.88) означал бы, что знак
        болтается в пустоте: круг-подложку мы не берём."""
        m = re.search(r'viewBox="([\d.\- ]+)"', self.src)
        self.assertIsNotNone(m)
        x, y, w, h = [float(v) for v in m.group(1).split()]
        self.assertAlmostEqual(w, 411.00, delta=0.5)
        self.assertAlmostEqual(h, 298.78, delta=0.5)
        self.assertNotAlmostEqual(w, 523.88, delta=1)

    def test_mark_has_a_readable_name(self):
        u"""Знак — картинка; без подписи чтец экрана прочитал бы «ECON RUSH»
        и потерял бы «W»."""
        self.assertIn('aria-label="Wecon Rush"', self.src)
        self.assertIn('aria-hidden="true"', self.src)

    def test_both_pages_size_and_colour_the_mark(self):
        u"""Партиал общий на две страницы, поэтому размер и цвет задаёт
        КАЖДАЯ из них — иначе знак приедет на статистику голым."""
        for path in (PAGE, 'problems/templates/platform/_stats_style.html'):
            src = read(path)
            # Селектор целиком, а не подстрокой: «.w-mark-OFF» тоже содержит
            # «.w-mark», и проверка на подстроку проспала бы переименование.
            self.assertRegex(src, r'\.rush-logo \.w-mark\s*\{', path)
            self.assertIn('height: .7em', src, path)     # высота заглавных
            self.assertIn('color: var(--', src, path)    # цвет — токеном


class NavigationTests(TestCase):
    u"""1.2 Пункт навигации называется «Wecon Rush».

    ⚠️ ПРОВЕРКА ПЕРЕЕХАЛА С ШАБЛОНА НА ОТРИСОВАННУЮ СТРАНИЦУ (04.09.2026).
    Прежде `_nav.html` держал четыре копии ряда ссылок, и тест считал в нём
    четыре литерала подписи и восемь условий подсветки. Копий больше нет:
    состав меню собирает `config/context_processors.py::site_meta`, а
    разметка — один цикл. Считать литералы стало нечего, и это к лучшему:
    важно, что видит человек, а не сколько раз слово написано в файле.
    """

    def _nav_labels(self, html):
        u"""Подписи пунктов шапки в порядке слева направо."""
        block = html.split('<div class="nav-links">', 1)[-1].split('</div>', 1)[0]
        return re.findall(r'class="nav-link[^"]*"[^>]*>([^<]+)</a>', block)

    def test_rendered_page_shows_the_new_name(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        labels = self._nav_labels(html)
        self.assertEqual(labels.count('Wecon Rush'), 1, labels)
        self.assertNotIn('Игра', labels)
        self.assertNotIn('Тренажёр', labels)

    def test_textbook_stands_right_after_catalog(self):
        u"""Порядок задан владельцем: «Учебник» сразу за «Каталогом»."""
        labels = self._nav_labels(
            self.client.get(reverse('game:page')).content.decode('utf-8'))
        self.assertEqual(labels.count('Учебник'), 1, labels)
        self.assertEqual(labels[labels.index('Каталог') + 1], 'Учебник', labels)

    def test_active_item_is_marked_on_the_game_page(self):
        u"""«Где я сейчас» осталось на месте после переезда логики в питон."""
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        active = re.findall(r'class="nav-link is-active"[^>]*>([^<]+)</a>', html)
        self.assertEqual(set(active), {'Wecon Rush'}, active)


class StartScreenTextTests(TestCase):
    u"""1.3, 1.4, 1.5 — тексты стартового экрана."""

    def setUp(self):
        self.src = read(PAGE)

    def test_subtitle_is_the_owners_wording(self):
        self.assertIn('Решайте тестовые задачи в условиях ограниченного',
                      self.src)
        self.assertIn('тем дольше длится ваша игра!', self.src)
        self.assertNotIn('Четыре режима', self.src)

    def test_click_and_enter_line_is_gone(self):
        u"""Сам Enter как горячая клавиша остаётся, но строки про него нет."""
        self.assertNotIn('best-line', self.src)
        self.assertNotIn('Клик по режиму', self.src)
        self.assertIn("if (e.key === 'Enter' && CFG.pool_counts[mode])", self.src)

    def test_mode_captions(self):
        self.assertIn("kind: 'Данетки: Верно или Неверно'", self.src)
        self.assertIn("kind: 'Один верный ответ'", self.src)
        self.assertIn("kind: 'Несколько верных ответов'", self.src)
        self.assertIn("kind: 'Числовой ответ без решения'", self.src)


class HeartsTests(TestCase):
    u"""1.6 Сердечки красные с заливкой."""

    def test_filled_heart_icon_exists_and_outline_stays(self):
        icons = read(ICONS)
        self.assertIn('heart_fill:', icons)
        self.assertIn('fill="currentColor" stroke="none"', icons)
        # Контурную не удаляем: ею пользуется блок достижений статистики.
        self.assertIn('heart:', icons)

    def test_game_uses_the_filled_heart(self):
        src = read(PAGE)
        self.assertIn('ICONS.heart_fill', src)
        # Запас на карточках режимов и в игре — залитыми.
        self.assertGreaterEqual(src.count('ICONS.heart_fill'), 3)

    def test_lost_life_is_the_same_icon_dimmed(self):
        u"""Погашенная жизнь — та же картинка с прозрачностью, а не другой
        символ: видно, «сколько было и сколько осталось»."""
        src = read(PAGE)
        self.assertIn('.heart.lost {', src)
        self.assertIn('opacity: .45;', src)


class KeyHintTests(TestCase):
    u"""1.7 Подсказка клавиш — своя на каждый тип вопроса."""

    def setUp(self):
        self.src = read(PAGE)

    def test_bullet_hint(self):
        self.assertIn('Используйте клавиши 1–2 для быстрого ответа, '
                      "'\n          + 'а пробел для пропуска задания", self.src)

    def test_single_choice_hint_counts_real_options(self):
        self.assertIn("'Используйте клавиши 1–' + q.options.length\n"
                      "          + ' для быстрого ответа, а пробел для пропуска задания'",
                      self.src)

    def test_multi_hint_mentions_enter(self):
        u"""Без Enter несколько выбранных вариантов не отправить."""
        self.assertIn('для выбора вариантов, Enter для ответа', self.src)

    def test_classic_has_exactly_one_hint(self):
        u"""Вторая строка («Enter — отправить», «дробь как 1/3») убрана."""
        self.assertIn('Дроби можно вводить через слэш, точку или', self.src)
        self.assertNotIn('Дробь можно вводить как 1/3', self.src)
        self.assertNotIn('num-hint', self.src)


class SkipTests(TestCase):
    u"""1.8 Пробел пропускает во всех четырёх режимах, кнопки в Классике нет."""

    def setUp(self):
        self.src = read(PAGE)

    def test_classic_skip_button_is_gone(self):
        self.assertNotIn('btn-num-skip', self.src)
        self.assertIn("id=\"btn-num-submit\"", self.src)   # «Ответить» осталась

    def test_space_skips_in_the_numeric_mode(self):
        self.assertIn("if (e.key === ' ') { e.preventDefault(); skip(); return; }",
                      self.src)

    def test_space_does_nothing_on_the_start_and_final_screens(self):
        u"""Пробел на старте и на финале не должен ничего запускать: обе
        ветки обработчика уходят в return, не дойдя до skip()."""
        m = re.search(r"if \(state === 'start'\) \{(.*?)\n      return;\n    \}",
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("e.key === ' '", m.group(1))
        m2 = re.search(r"if \(state === 'finished'\) \{(.*?)\n      return;\n    \}",
                       self.src, re.S)
        self.assertIsNotNone(m2)
        self.assertNotIn("e.key === ' '", m2.group(1))


class QuitModalTests(TestCase):
    u"""1.9, 1.10 Своё окно выхода вместо нативного диалога."""

    def setUp(self):
        self.src = read(PAGE)

    def test_no_native_dialog(self):
        self.assertNotIn('confirm(', self.src)

    def test_modal_markup_and_wording(self):
        self.assertIn('Закончить игру? Результат не сохранится.', self.src)
        self.assertIn('id="quit-modal"', self.src)
        self.assertIn('aria-modal="true"', self.src)
        self.assertIn('>Нет</button>', self.src)
        self.assertIn('>Да</button>', self.src)

    def test_no_is_the_main_action_and_takes_focus(self):
        self.assertIn("$('quit-no').focus();", self.src)
        self.assertIn('.quit-no { border: none; background: var(--btn-bg);', self.src)

    def test_escape_means_no(self):
        self.assertIn("if (e.key === 'Escape') { e.preventDefault(); closeQuit(); return; }",
                      self.src)

    def test_card_behind_is_blurred_and_timer_keeps_running(self):
        u"""Читать вопрос из-за окна нельзя, а окно не даёт бесплатной паузы:
        цикл таймера при открытии не трогается."""
        self.assertIn('backdrop-filter: blur(6px);', self.src)
        m = re.search(r'function openQuit\(\) \{(.*?)\n  \}', self.src, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn('cancelAnimationFrame', m.group(1))

    def test_hover_on_the_x_has_no_sand_fill(self):
        self.assertNotIn('.quit-x:hover { color: var(--text); background:', self.src)
        self.assertIn('.quit-x:hover { color: var(--text); font-weight: 700;',
                      self.src)


class GeneratedNoteTests(TestCase):
    u"""1.11 Плашка «ТРЕНИРОВОЧНЫЙ» заменена строкой под карточкой."""

    def setUp(self):
        self.src = read(PAGE)

    def test_chip_is_gone_and_note_took_its_place(self):
        # ⚠️ Ищем ПЛАШКУ, а не слово: «тренировочный забег» — это отдельная
        # и законная надпись про зачётность (фаза 4), и проверка на слово
        # запрещала бы её заодно.
        self.assertNotIn('gen-chip', self.src)
        self.assertNotIn('>Тренировочный<', self.src)
        self.assertIn('>Вопрос сгенерирован ИИ</p>', self.src)

    def test_note_is_small_and_quiet_under_the_card(self):
        self.assertIn('.gen-note {', self.src)
        self.assertIn('font-size: 12px;', self.src)
        self.assertIn('color: var(--text3);', self.src)

    def test_note_follows_the_generated_flag(self):
        self.assertIn("$('gen-note').hidden = !q.generated;", self.src)


class FinalScreenTests(TestCase):
    u"""1.12 Правый угол шапки результатов и подпись под графиком убраны."""

    def setUp(self):
        self.src = read(PAGE)

    def test_hearts_and_reason_corner_is_gone(self):
        for dead in ('fin-head-r', 'fin-hearts', 'fin-reason',
                     'paintHearts', 'reasonText'):
            self.assertNotIn(dead, self.src, dead)

    def test_comparison_chart_stays_but_its_caption_is_gone(self):
        u"""⚠️ Подпись переименована 08.09.2026: «Сравнение с прошлыми
        играми» → «Последние раунды». Сам график остался — проверяем его
        по КОРОБКЕ, а не по названию: название владелец меняет, коробка
        держит смысл."""
        self.assertIn('id="chart-history"', self.src)
        self.assertIn('Последние раунды', self.src)
        self.assertNotIn('правый столбец этот забег', self.src)


class DeltaChipTests(TestCase):
    u"""1.13 «−1» от прошлого забега не показывается в начале нового.

    Замер до починки (проба scripts/rush_delta_probe.js): на 100 и 400 мс
    свежего забега в Рапиде плашка показывала «−1» с непрозрачностью 1 при
    трёх целых жизнях. Причина — анимация `forwards` перезапускается, когда
    экран игры снова становится видимым.
    """

    def test_start_run_clears_the_delta_chip(self):
        src = read(PAGE)
        m = re.search(r'function startRun\(opts\) \{(.*?)\n  \}', src, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("deltaChip.className = 'time-delta';", body)
        self.assertIn("deltaChip.innerHTML = '';", body)
        self.assertIn("deltaChip.style.opacity = '';", body)


class EmDashTests(TestCase):
    u"""1.14 В видимых строках game/ длинного тире нет."""

    def test_no_em_dash_in_game_templates(self):
        import subprocess
        import sys
        out = subprocess.run(
            [sys.executable, 'scripts/check_em_dash.py', 'game', '--json'],
            capture_output=True, text=True, encoding='utf-8')
        import json
        data = json.loads(out.stdout)
        self.assertEqual(data['total'], 0, data['files'])

    def test_error_strings_are_clean_too(self):
        u"""Тексты ошибок из JsonResponse человек видит на экране — там тире
        тоже быть не должно. Комментарии и строки документации не в счёт."""
        for line in read('game/views.py').split('\n'):
            if 'JsonResponse' in line or "'error':" in line:
                self.assertNotIn('—', line, line)


class RoundNotRaceTests(TestCase):
    u"""1.15 Слова «забег» человек на экране не видит — только «раунд».

    Решение владельца 04.09.2026: в Wecon Rush «забег» заменён на «раунд»
    во ВСЕХ строках, которые доходят до человека. Комментарии кода, имена
    переменных и docs/GAME.md намеренно оставлены как были — это не экран.

    Поэтому проверка идёт по ОТРЕНДЕРЕННОЙ странице с вырезанными
    комментариями: она ловит и разметку, и строки внутри инлайн-скрипта,
    которые попадают в DOM, и aria-label с data-tip.
    """

    RX = re.compile('забег', re.IGNORECASE)

    def _visible(self, html):
        u"""Текст страницы без того, чего человек не видит."""
        html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        html = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', html, flags=re.S)
        html = re.sub(r'\{#.*?#\}', '', html, flags=re.S)
        html = re.sub(r'/\*.*?\*/', '', html, flags=re.S)
        return '\n'.join(self._strip_line_comment(ln)
                         for ln in html.split('\n'))

    @staticmethod
    def _strip_line_comment(line):
        u"""Отрезать хвостовой `//`-комментарий, не тронув адреса и строки.

        Осторожно: «//» бывает внутри адреса (`https://`) и внутри строкового
        литерала. Режем только там, где перед «//» стоит пробел, кавычки до
        него закрыты и это не двоеточие из адреса. Правило намеренно
        осторожное: пропустить лишний комментарий безопаснее, чем спрятать
        настоящую строку с экрана.
        """
        for m in re.finditer('//', line):
            j = m.start()
            before = line[:j]
            if before.strip() and not before.endswith((' ', '\t')):
                continue
            if before.count("'") % 2 or before.count('"') % 2:
                continue
            if before.rstrip().endswith(':'):
                continue
            return before
        return line

    def _check(self, url, who):
        response = self.client.get(url)
        self.assertIn(response.status_code, (200, 302), '%s: %s' % (who, url))
        if response.status_code != 200:
            return
        found = self.RX.findall(self._visible(response.content.decode('utf-8')))
        self.assertEqual(
            found, [],
            u'%s видит слово «забег» на %s: %d раз. Решение владельца — '
            u'«раунд».' % (who, url, len(found)),
        )

    def test_guest_sees_no_race_word(self):
        for url in ('/game/', '/game/daily/'):
            self._check(url, u'гость')

    def test_logged_in_sees_no_race_word(self):
        from problems.models import User
        User.objects.create_user(username='round_probe', password='x' * 12,
                                 role='student')
        self.client.login(username='round_probe', password='x' * 12)
        for url in ('/game/', '/game/daily/', '/game/stats/'):
            self._check(url, u'вошедший')

    def test_unranked_reasons_say_round(self):
        u"""Причины «почему раунд не в таблице» человек читает на экране."""
        from game.config import UNRANKED_TEXT
        for key, text in UNRANKED_TEXT.items():
            self.assertNotIn('забег', text.lower(), '%s: %s' % (key, text))
