# -*- coding: utf-8 -*-
"""Шапка сайта: состав по ролям, метка версии, выход, узкий экран.

⚠️ ПОЧЕМУ ПРОВЕРКИ ПО ОТРИСОВАННОЙ СТРАНИЦЕ, А НЕ ПО ШАБЛОНУ. До 04.09.2026
`_nav.html` держал четыре копии одного ряда ссылок, и старые тесты считали в
файле литералы («ровно четыре подписи», «ровно восемь условий подсветки»).
Копий больше нет: состав собирает `config/context_processors.py::site_meta`.
Считать в файле стало нечего — и это к лучшему: важно, что видит человек.
"""
import re
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from problems.models import User
from vp.config import NEW_BADGE_UNTIL

PASSWORD = 'nav-probe-2026'

# Семь шаблонов подключают `_nav.html`. По одному адресу на каждый — метка
# версии обязана быть на всех: «угол, который ничем не закрыт».
# Роль указана потому, что кабинеты закрыты друг от друга: `/student/`
# отдаёт учителю 403, и это правильно.
TEMPLATE_PAGES = (
    ('/catalog/', 'catalog/base.html', 'student'),
    ('/student/', 'student/base.html', 'student'),
    # `/teacher/` — редирект по устройству (своего экрана у корня нет).
    ('/teacher/groups/', 'teacher/base.html', 'teacher'),
    ('/profile/', 'platform/base.html', 'student'),
    ('/calc2/', 'calc2/calc2.html', 'student'),
    ('/game/', 'game/game.html', 'student'),
    ('/calendar/', 'calendar_stub/calendar.html', 'student'),
)


NAV_LINK = re.compile(r'<a class="(nav-link[^"]*)"[^>]*>(.*?)</a>', re.S)
NAV_FLAG = re.compile(r'<span class="nav-flag">.*?</span>', re.S)


def link_label(inner):
    """Подпись пункта из содержимого `<a>`: без метки NEW и без вложенной разметки.

    ⚠️ МЕТКА ВЫРЕЗАЕТСЯ ЦЕЛИКОМ, А НЕ ТОЛЬКО ТЕГИ. Прежняя регулярка брала текст без
    вложенных тегов, и пункт с `<span class="nav-flag">` пропадал из списка — тесты
    оставались бы зелёными на пустом месте. А если вычищать одни теги, подпись стала бы
    «Тренажёр ВПNEW» и перестала бы совпадать сразу после 1 октября, когда метка гаснет
    по дате: тест сломался бы от календаря, а не от кода.
    """
    return re.sub(r'<[^>]+>', '', NAV_FLAG.sub('', inner)).strip()


def nav_labels(html):
    """Подписи пунктов ряда в шапке (не в панели узкого экрана)."""
    block = html.split('<div class="nav-links">', 1)[-1].split('</div>', 1)[0]
    return [link_label(inner) for _, inner in NAV_LINK.findall(block)]


def active_labels(html):
    """Подписи пунктов с классом is-active по всей странице (шапка и панель).

    Класс ищется среди классов, а не строкой `class="nav-link is-active"`: у пункта с
    меткой их три, и порядок не должен иметь значения.
    """
    return [link_label(inner) for classes, inner in NAV_LINK.findall(html)
            if 'is-active' in classes.split()]


class MenuByRoleTests(TestCase):
    """Состав меню зависит от роли — и только от неё."""

    def _labels(self, user=None, url='/catalog/'):
        if user is not None:
            self.client.force_login(user)
        return nav_labels(self.client.get(url).content.decode('utf-8'))

    def test_guest(self):
        self.assertEqual(
            self._labels(),
            ['Каталог', 'Учебник', 'Олимпиады', 'Тренажёр ВП', 'Графики', 'Wecon Rush'])

    def test_student_has_lessons_and_no_stats(self):
        user = User.objects.create_user(username='nav_st', password=PASSWORD,
                                        role='student')
        labels = self._labels(user)
        self.assertEqual(
            labels,
            ['Занятия', 'Каталог', 'Учебник', 'Олимпиады', 'Тренажёр ВП',
             'Графики', 'Wecon Rush'])
        # Статистика живёт в профиле; двух входов в одно место быть не должно.
        self.assertNotIn('Статистика', labels)

    def test_teacher(self):
        user = User.objects.create_user(username='nav_tu', password=PASSWORD,
                                        role='teacher')
        self.assertEqual(
            self._labels(user),
            ['Ученики', 'Каталог', 'Учебник', 'Олимпиады', 'Тренажёр ВП',
             'Графики', 'Wecon Rush'])

    def test_staff_gets_admin_item(self):
        user = User.objects.create_user(username='nav_ad', password=PASSWORD,
                                        role='teacher', is_staff=True)
        self.assertIn('Админка', self._labels(user))

    def test_textbook_stands_right_after_catalog_for_every_role(self):
        """Порядок задан владельцем и одинаков у всех ролей."""
        users = [
            None,
            User.objects.create_user(username='nav_o1', password=PASSWORD, role='student'),
            User.objects.create_user(username='nav_o2', password=PASSWORD, role='teacher'),
        ]
        for user in users:
            self.client.logout()
            labels = self._labels(user)
            self.assertEqual(labels.count('Учебник'), 1, labels)
            self.assertEqual(labels[labels.index('Каталог') + 1], 'Учебник', labels)

    def test_every_item_appears_once(self):
        user = User.objects.create_user(username='nav_once', password=PASSWORD,
                                        role='teacher')
        labels = self._labels(user)
        self.assertEqual(len(labels), len(set(labels)), labels)

    def test_counts_are_six_seven_seven(self):
        """Числовой инвариант состава: гость 6, ученик 7, учитель 7.

        Было 5 / 7 / 7 — «Календарь» ушёл из шапки 08.09.2026; стало на один больше у
        всех — «Тренажёр ВП» (до 22.09.2026 «Высшая проба») встал после «Олимпиад» (сезонный пункт, сессия 4).
        """
        student = User.objects.create_user(username='nav_c1', password=PASSWORD,
                                           role='student')
        teacher = User.objects.create_user(username='nav_c2', password=PASSWORD,
                                           role='teacher')
        self.client.logout()
        self.assertEqual(len(self._labels()), 6)
        self.client.logout()
        self.assertEqual(len(self._labels(student)), 7)
        self.client.logout()
        self.assertEqual(len(self._labels(teacher)), 7)

    def test_calendar_left_the_menu_but_the_page_is_alive(self):
        """⚠️ Убрана ССЫЛКА, а не раздел.

        Решение владельца 08.09.2026: пункта «Календарь» в шапке нет ни у
        одной роли, но маршрут `/calendar/` и приложение `calendar_stub`
        живы — страница открывается по прямому адресу. Два утверждения
        держатся вместе: без второго правка выглядела бы как удаление
        раздела, без первого — как будто ничего не сделано.
        """
        users = [
            None,
            User.objects.create_user(username='nav_k1', password=PASSWORD,
                                     role='student'),
            User.objects.create_user(username='nav_k2', password=PASSWORD,
                                     role='teacher'),
            User.objects.create_user(username='nav_k3', password=PASSWORD,
                                     role='teacher', is_staff=True),
        ]
        for user in users:
            self.client.logout()
            self.assertNotIn('Календарь', self._labels(user))

        for user in users:
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            self.assertNotEqual(self.client.get('/calendar/').status_code, 404)


class ActiveItemTests(TestCase):
    """«Где я сейчас» — цвет подписи и линия под словом (08.09.2026).

    Отменяет ADR 0072 «подчёркивание плюс фон»: заливка красила прямоугольник
    во всю высоту полосы, и активный пункт отличался от пункта под курсором
    только плотностью серого.
    """

    def test_only_the_current_item_is_active(self):
        for url, expected in (('/catalog/', 'Каталог'),
                              ('/olympiads/', 'Олимпиады'),
                              ('/vp/', 'Тренажёр ВП'),
                              ('/game/', 'Wecon Rush'),
                              ('/textbook/', 'Учебник')):
            html = self.client.get(url).content.decode('utf-8')
            active = active_labels(html)
            self.assertEqual(set(active), {expected}, '%s → %s' % (url, active))

    def test_active_style_is_colour_and_underline_without_fill(self):
        """Цвет подписи и линия под словом; заливки во всю высоту нет."""
        html = self.client.get('/catalog/').content.decode('utf-8')

        rule = html.split('.nav-link.is-active {', 1)[1].split('}', 1)[0]
        self.assertIn('color: var(--nav-accent)', rule)
        # ⚠️ Заливки быть НЕ должно: именно она делала активный пункт похожим
        # на пункт под курсором — .12 против .08, отличие только в плотности.
        self.assertNotIn('background:', rule)

        after = html.split('.nav-link.is-active::after {', 1)[1].split('}', 1)[0]
        self.assertIn('background: var(--nav-accent)', after)
        self.assertIn('box-shadow', after)

    def test_nav_accent_is_one_colour_for_both_themes(self):
        """⚠️ Токен объявлен ДВАЖДЫ и одинаково — светлая тема и тёмная.

        Шапка не меняется по темам, а `--accent` меняется: в светлой он даёт
        на графите #3c3531 контраст 2,30 при пороге 4,5. Если значения
        разойдутся, подпись активного пункта в одной из тем станет
        нечитаемой — и разойтись они могут молча, при следующей правке
        палитры. Поэтому смысл «один цвет на обе темы» сторожится числом.
        """
        html = self.client.get('/catalog/').content.decode('utf-8')
        values = re.findall(r'--nav-accent:\s*([^;]+);', html)
        self.assertEqual(len(values), 2, values)
        self.assertEqual(len(set(v.strip() for v in values)), 1, values)

        glow = re.findall(r'--nav-accent-glow:\s*([^;]+);', html)
        self.assertEqual(len(glow), 2, glow)
        self.assertEqual(len(set(v.strip() for v in glow)), 1, glow)


class VpItemTests(TestCase):
    """Пункт «Тренажёр ВП»: подпись, метка NEW, состояние «раздел открыт» (22.09.2026).

    ⚠️ ДАТЫ ВЫВЕДЕНЫ ИЗ `NEW_BADGE_UNTIL`, А НЕ ВПИСАНЫ. Метка гаснет по календарю,
    и тест с вписанным «сегодня» сломался бы сам, в тот день, когда её срок выйдет. Время
    двигается тем же патчем `timezone.now`, что и в тестах ВП (`vp/tests/helpers.at`);
    граница считается по местной полуночи (`localdate()`), а не по UTC.
    """

    @staticmethod
    def _edge():
        """Местная полночь дня, когда метка гаснет."""
        return timezone.make_aware(datetime.combine(NEW_BADGE_UNTIL, time.min))

    def _get(self, url, moment, user=None):
        if user is not None:
            self.client.force_login(user)
        # Настоящий `timezone.now()` отдаёт время в UTC — патчим им же, иначе проверка «по UTC
        # вместо местной даты» проходила бы: `.date()` московского момента и так московский.
        with mock.patch('django.utils.timezone.now', return_value=moment.astimezone(dt_timezone.utc)):
            return self.client.get(url)

    def _html(self, url='/catalog/', moment=None):
        moment = moment or self._edge() - timedelta(days=1)
        return self._get(url, moment).content.decode('utf-8')

    @staticmethod
    def _rows(html):
        """Ряды ссылок страницы: в шапке и в панели ☰ (циклов ровно два)."""
        return [block.split('</div>', 1)[0]
                for block in html.split('<div class="nav-links">')[1:]]

    def _vp_links(self, html):
        """Пункт ВП в каждом из рядов: список множеств классов."""
        links = []
        for row in self._rows(html):
            found = [set(classes.split()) for classes, inner in NAV_LINK.findall(row)
                     if link_label(inner) == 'Тренажёр ВП']
            self.assertEqual(len(found), 1, row)
            links.append(found[0])
        return links

    def test_label_is_the_trainer_and_the_old_name_is_gone(self):
        users = [None,
                 User.objects.create_user(username='nav_vp_st', password=PASSWORD, role='student'),
                 User.objects.create_user(username='nav_vp_te', password=PASSWORD, role='teacher')]
        moment = self._edge() - timedelta(days=1)      # метка горит: хелперы обязаны её пережить
        for user in users:
            self.client.logout()
            rows = self._rows(self._get('/catalog/', moment, user).content.decode('utf-8'))
            self.assertEqual(len(rows), 2)
            for row in rows:
                labels = [link_label(inner) for _, inner in NAV_LINK.findall(row)]
                self.assertIn('Тренажёр ВП', labels)
                self.assertNotIn('Высшая проба', labels)

    def test_flag_is_drawn_once_per_row(self):
        """Ожидаемое число — ДВА на страницу: одна метка в шапке, одна в панели ☰."""
        html = self._html()
        self.assertEqual(html.count('<span class="nav-flag">NEW</span>'), 2)
        for row in self._rows(html):
            self.assertEqual(row.count('<span class="nav-flag">NEW</span>'), 1, row)

    def test_helpers_see_the_flagged_item(self):
        """Хелперы подписей видят пункт с меткой — иначе он пропадал бы из списков молча."""
        html = self._html()
        self.assertEqual(nav_labels(html),
                         ['Каталог', 'Учебник', 'Олимпиады', 'Тренажёр ВП', 'Графики', 'Wecon Rush'])

    def test_only_the_trainer_carries_the_new_class(self):
        """Состав остальных пунктов не тронут: is-new только у ВП, в обоих рядах."""
        html = self._html()
        for row in self._rows(html):
            marked = [link_label(inner) for classes, inner in NAV_LINK.findall(row)
                      if 'is-new' in classes.split()]
            self.assertEqual(marked, ['Тренажёр ВП'], row)
        for classes in self._vp_links(html):
            self.assertIn('is-new', classes)

    def test_context_keys_are_defaulted_for_every_other_item(self):
        response = self._get('/catalog/', self._edge() - timedelta(days=1))
        items = {i['label']: i for i in response.context['nav_items']}
        self.assertEqual((items['Тренажёр ВП']['is_new'], items['Тренажёр ВП']['flag']), (True, 'NEW'))
        for label, item in items.items():
            if label != 'Тренажёр ВП':
                self.assertEqual((item['is_new'], item['flag']), (False, ''), label)

    def test_flag_goes_out_by_date_and_the_item_stays_a_plain_link(self):
        """С этого дня — ни класса is-new, ни метки; пункт на месте, с той же подписью."""
        for moment in (self._edge(), self._edge() + timedelta(days=30)):
            response = self._get('/catalog/', moment)
            html = response.content.decode('utf-8')
            self.assertNotIn('<span class="nav-flag"', html, moment)
            for classes in self._vp_links(html):
                self.assertNotIn('is-new', classes, moment)
            self.assertIn('<a class="nav-link" href="/vp/">Тренажёр ВП</a>', html, moment)
            item = [i for i in response.context['nav_items'] if i['label'] == 'Тренажёр ВП'][0]
            self.assertEqual((item['is_new'], item['flag']), (False, ''), moment)

    def test_the_boundary_is_local_midnight_not_utc(self):
        """Секундой раньше границы метка ещё горит, на границе — уже нет.

        Москва — UTC+3: местная полночь наступает в 21:00 UTC предыдущего дня. Проверка
        по `now().date()` вместо `localdate()` ошиблась бы на три часа."""
        one_second = timedelta(seconds=1)
        self.assertIn('<span class="nav-flag">', self._html(moment=self._edge() - one_second))
        self.assertNotIn('<span class="nav-flag"', self._html(moment=self._edge()))

    def test_open_section_keeps_new_class_and_gets_the_canon_colour(self):
        """На странице раздела пункт несёт is-active И is-new, а подпись — бирюзовая."""
        html = self._html('/vp/')
        for classes in self._vp_links(html):
            self.assertLessEqual({'is-active', 'is-new'}, classes)
        self.assertEqual(set(active_labels(html)), {'Тренажёр ВП'})
        # Метка у открытого раздела остаётся: «новое» дальше несёт только она.
        self.assertEqual(html.count('<span class="nav-flag">NEW</span>'), 2)

        # ⚠️ Правило ищется от НАЧАЛА СТРОКИ: подстрока `.nav-link.is-new.is-active {` есть и в
        # панельном `.nav-panel .nav-link.is-new.is-active {`, а у того цвет тот же — тест на
        # подстроку проспал бы удаление общего правила (нашла проверка зубастости).
        rule = re.search(r'^\.nav-link\.is-new\.is-active \{([^}]*)\}', html, re.M)
        self.assertIsNotNone(rule, 'нет общего правила .nav-link.is-new.is-active')
        self.assertIn('color: var(--nav-accent)', rule.group(1))

    def test_hover_rules_of_the_new_item_do_not_beat_the_open_one(self):
        """⚠️ Наведение на НОВЫЙ пункт не должно красить линию ОТКРЫТОГО раздела в янтарь.

        Специфичность `.nav-link.is-new:hover::after` (0,3,1) выше, чем у
        `.nav-link.is-active::after` (0,2,1): без `:not(.is-active)` неоновая линия
        открытого раздела при наведении желтела бы."""
        html = self._html()
        self.assertNotIn('.nav-link.is-new:hover', html)
        self.assertIn('.nav-link.is-new:not(.is-active):hover {', html)
        self.assertIn('.nav-link.is-new:not(.is-active):hover::after {', html)

    def test_panel_bar_belongs_to_the_open_section_only(self):
        """В панели ☰: у открытого нового пункта риска бирюзовая, у невыбранного — прозрачная."""
        html = self._html()
        open_rule = html.split('.nav-panel .nav-link.is-new.is-active {', 1)[1].split('}', 1)[0]
        self.assertIn('border-left-color: var(--nav-accent)', open_rule)
        self.assertIn('color: var(--nav-accent)', open_rule)

        new_rule = html.split('.nav-panel .nav-link.is-new {', 1)[1].split('}', 1)[0]
        self.assertIn('color: var(--brand-amber)', new_rule)
        # Риску новому пункту НЕ ставим: она осталась бы второй одинаковой в панели.
        self.assertNotIn('border-left', new_rule)
        base = html.split('.nav-panel .nav-link {', 1)[1].split('}', 1)[0]
        self.assertIn('border-left: 2px solid transparent', base)

    def test_flag_is_ink_on_amber_and_the_numbers_hold(self):
        """Метка — чернила на янтаре (AAA 7,0), янтарная подпись на графите шапки (AA 4,5)."""
        html = self._html()
        rule = html.split('.nav-flag {', 1)[1].split('}', 1)[0]
        self.assertIn('background: var(--brand-amber)', rule)
        self.assertIn('color: var(--brand-amber-ink)', rule)

        def token(name):
            return re.search(r'--%s:\s*(#[0-9a-fA-F]{6})' % name, html).group(1)

        def luminance(hex_colour):
            channels = []
            for i in (1, 3, 5):
                c = int(hex_colour[i:i + 2], 16) / 255
                channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        def contrast(a, b):
            hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)

        self.assertGreaterEqual(contrast(token('brand-amber-ink'), token('brand-amber')), 7.0)
        self.assertGreaterEqual(contrast(token('brand-amber'), token('nav-bg')), 4.5)
        self.assertGreaterEqual(contrast(token('brand-amber-hover'), token('nav-bg')), 4.5)


class VersionBadgeTests(TestCase):
    """Метка версии — строкой внизу страницы (решение владельца 17.09.2026).

    До 17.09 «beta 0.0» стояла в шапке и на экранах входа; теперь «Beta 1.0»
    одним партиалом `_site_version.html` во всех базовых шаблонах и в игре
    (подключена в редизайне Wecon Rush, фаза P8)."""

    BASES = (
        'templates/registration/login.html', 'templates/registration/register.html',
        'catalog/templates/catalog/base.html', 'student/templates/student/base.html',
        'teacher/templates/teacher/base.html', 'calc2/templates/calc2/calc2.html',
        'problems/templates/platform/base.html',
        'calendar_stub/templates/calendar_stub/calendar.html',
        'game/templates/game/game.html',
    )
    # Шаблоны, где метка обязана стоять внизу окна и на короткой странице.
    COLUMN_BASES = (
        'catalog/templates/catalog/base.html', 'student/templates/student/base.html',
        'teacher/templates/teacher/base.html', 'problems/templates/platform/base.html',
        'game/templates/game/game.html', 'templates/registration/_auth_style.html',
    )

    def setUp(self):
        self.users = {
            'student': User.objects.create_user(
                username='nav_ver_st', password=PASSWORD, role='student'),
            'teacher': User.objects.create_user(
                username='nav_ver_tu', password=PASSWORD, role='teacher'),
        }

    def test_version_at_the_bottom_of_every_template(self):
        for url, template, role in TEMPLATE_PAGES:
            self.client.force_login(self.users[role])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200,
                             '%s (%s, %s)' % (url, template, role))
            html = response.content.decode('utf-8')
            self.assertFalse('beta 0.0' in html, url)
            self.assertFalse('nav-version' in html, url)
            self.assertEqual(html.count('<div class="site-version">%s</div>' % settings.SITE_VERSION), 1, url)

    def test_login_and_register_have_it_below(self):
        self.client.logout()
        for url in ('/login/', '/register/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertTrue('<div class="site-version">%s</div>' % settings.SITE_VERSION in html, url)
            self.assertFalse('auth-version' in html, url)

    def test_partial_is_included_in_every_base_template(self):
        for path in self.BASES:
            with open(path, encoding='utf-8') as fh:
                self.assertTrue("{% include '_site_version.html' %}" in fh.read(), path)

    def test_version_stands_at_the_bottom_of_a_short_page(self):
        """На бою 17.09 «Beta 1.0» висела посреди окна у короткой страницы кабинета:
        строка шла сразу за содержимым. Теперь `body` — колонка во всю высоту окна,
        а метку прижимает вниз `margin-top: auto`. Как это выглядит в браузере —
        `game/tests/browser_teacher_sets.mjs`, проверка `version_at_the_bottom_of_short_pages`."""
        with open('templates/_site_version.html', encoding='utf-8') as fh:
            partial = fh.read()
        rule = partial.split('.site-version {', 1)[1].split('}', 1)[0]
        self.assertIn('margin-top: auto;', rule)
        for path in self.COLUMN_BASES:
            with open(path, encoding='utf-8') as fh:
                css = fh.read()
            body = css.split('\nbody {', 1)[1].split('\n}', 1)[0]
            self.assertIn('display: flex;', body, path)
            self.assertIn('flex-direction: column;', body, path)
            self.assertIn('min-height: 100vh;', body, path)
        for path in self.COLUMN_BASES[:4]:
            with open(path, encoding='utf-8') as fh:
                self.assertIn('body > main { width: 100%; }', fh.read(), path)
        # Метка — последний видимый в потоке элемент страницы: за ней только скрипты,
        # закреплённые кнопки обратной связи, скрытая форма, закреплённый стек плашек
        # угла (`_corner_stack.html`, position: fixed — вне потока) и инертные
        # `<template>` плашек (18.09.2026).
        self.client.force_login(self.users['teacher'])
        html = self.client.get('/teacher/game-sets/').content.decode('utf-8')
        tail = html.split('<div class="site-version">', 1)[1].split('</div>', 1)[1]
        tail = re.sub(r'<script\b.*?</script>|<style\b.*?</style>|<template\b.*?</template>',
                      '', tail, flags=re.S)
        tail = tail.replace('<div class="corner-stack" id="corner-stack"', '')
        self.assertEqual(re.findall(r'<(main|section|div|nav|footer)\b', tail), [])

    def test_version_comes_from_settings(self):
        self.client.force_login(self.users['student'])
        with self.settings(SITE_VERSION='Beta 9.9'):
            html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertTrue('Beta 9.9' in html, 'значение не из настроек')
        self.assertFalse('Beta 1.0' in html, 'значение зашито в шаблон')


class LogoutTests(TestCase):
    """Выход — POST. Прежняя GET-ссылка отдавала 405: это и была «ошибка»."""

    def setUp(self):
        self.user = User.objects.create_user(username='nav_out',
                                             password=PASSWORD, role='student')

    def test_post_logs_out_and_goes_home(self):
        self.client.force_login(self.user)
        response = self.client.post('/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_get_is_405_and_that_is_normal(self):
        """Так решил Django 5. Чинить нечего — чинить надо было ссылку."""
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/logout/').status_code, 405)

    def test_header_shows_guest_buttons_after_logout(self):
        self.client.force_login(self.user)
        self.client.post('/logout/')
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('class="nav-login"', html)
        self.assertIn('Создать аккаунт', html)
        self.assertNotIn('class="nav-user"', html)

    def test_header_form_is_post_with_csrf(self):
        self.client.force_login(self.user)
        html = self.client.get('/catalog/').content.decode('utf-8')
        form = html.split('<form class="nav-logout"', 1)[1].split('</form>', 1)[0]
        self.assertIn('method="post"', form)
        self.assertIn('csrfmiddlewaretoken', form)


class ProfileChipTests(TestCase):
    """Плашка профиля: круг с инициалами и имя, всё — одна ссылка."""

    def test_initials_from_first_and_last_name(self):
        user = User.objects.create_user(username='nav_chip', password=PASSWORD,
                                        role='student', first_name='Иван',
                                        last_name='Петров')
        self.client.force_login(user)
        html = self.client.get('/catalog/').content.decode('utf-8')
        chip = html.split('<a class="nav-user"', 1)[1].split('</a>', 1)[0]
        self.assertIn('ИП', chip)
        self.assertIn('Иван Петров', chip)
        self.assertIn('href="/profile/"', html.split('<a class="nav-user"', 1)[0][-40:]
                      + '<a class="nav-user"' + chip)

    def test_initials_fall_back_to_username(self):
        user = User.objects.create_user(username='zebra', password=PASSWORD,
                                        role='student')
        self.client.force_login(user)
        html = self.client.get('/catalog/').content.decode('utf-8')
        chip = html.split('<a class="nav-user"', 1)[1].split('</a>', 1)[0]
        self.assertIn('Z', chip)


class NavMarkupTests(TestCase):
    """Разметка: инлайновых стилей почти не осталось."""

    def test_almost_no_inline_styles(self):
        """Было 32 атрибута `style`, договорились не больше трёх."""
        import io
        src = io.open('templates/_nav.html', encoding='utf-8').read()
        self.assertLessEqual(src.count('style="'), 3, 'инлайновые стили вернулись')

    def test_no_four_copies_of_the_row(self):
        """Ряд ссылок в разметке ровно один цикл на шапку и один на панель."""
        import io
        src = io.open('templates/_nav.html', encoding='utf-8').read()
        self.assertEqual(src.count('{% for item in nav_items %}'), 2)


class TextbookTests(TestCase):
    """Учебник — заглушка «Скоро», и ничего больше."""

    def test_page_opens_for_guest(self):
        response = self.client.get('/textbook/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Скоро.', html)
        self.assertIn('Мы уже пишем.', html)

    def test_no_forms_or_buttons_on_the_stub(self):
        """Обещать на заглушке нечего: ни формы почты, ни кнопки."""
        html = self.client.get('/textbook/').content.decode('utf-8')
        body = html.split('<div class="tb">', 1)[1].split('</div>', 1)[0]
        self.assertNotIn('<form', body)
        self.assertNotIn('<button', body)
        self.assertNotIn('<input', body)


class ContentWidthTests(TestCase):
    """П10: 960 везде, 860 только на страницах чтения.

    Страницы задачи в списке чтения НЕТ: у неё своя полоса 1120 с карточкой
    чата справа — ADR 0078 и решение владельца 05.09.2026 («1120 для
    страницы задачи — исключение из „960/860“»).
    """

    def test_tokens_are_actually_read(self):
        import io
        for path in ('catalog/templates/catalog/base.html',
                     'student/templates/student/base.html'):
            src = io.open(path, encoding='utf-8').read()
            self.assertIn('max-width: var(--w-page);', src, path)
            self.assertNotIn('max-width: 860px;', src, path)

    def test_reading_pages_narrow_themselves(self):
        import io
        for path in ('student/templates/student/assignment_detail.html',
                     'student/templates/student/work_review.html',
                     'student/templates/student/submission_detail.html',
                     'student/templates/student/exam_take.html'):
            src = io.open(path, encoding='utf-8').read()
            self.assertIn('.page-wrap { max-width: var(--w-read); }', src, path)
