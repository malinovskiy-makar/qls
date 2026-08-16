"""
Панель «Настройки работы» — один партиал на четыре экрана создания
(сессия 10, фаза 2).

Здесь держится главное, что легко сломать незаметно:
  * панель есть на ВСЕХ четырёх экранах и всюду одна и та же;
  * ИМЕНА ПОЛЕЙ НА СЕРВЕРЕ не изменились ни одно — иначе создание работ
    молча перестанет работать, а страница будет отдавать честные 200;
  * переключатель вида и номер занятия не теряются в ссылках;
  * ряд фильтров ручного поиска не потерял ни одного элемента;
  * нечисловой `?group=` не роняет страницу пятисоткой.

Разбор напечатанной даты проверяется ИСПОЛНЕНИЕМ в node: это JavaScript, и
`TestCase` его не исполняет.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup, User

TEACHER = os.path.join(settings.BASE_DIR, 'teacher', 'templates', 'teacher')
SETTINGS_TPL = os.path.join(TEACHER, '_work_settings.html')
DATE_TPL = os.path.join(TEACHER, '_date_field.html')
DATE_JS = os.path.join(TEACHER, '_date_field_js.html')


def make_tutor(name='ws_tutor'):
    user = User.objects.create_user(username=name, password='x',
                                    email=f'{name}@test.local')
    user.role = 'teacher'
    user.save()
    profile = getattr(user, 'profile', None)
    if profile is not None:
        profile.role = 'tutor'
        profile.save()
    return user


class PanelIsOneOnEveryScreen(TestCase):
    """Панель настроек — один партиал, и он виден на всех экранах создания."""

    def setUp(self):
        self.tutor = make_tutor()
        self.client.force_login(self.tutor)
        self.group = StudentGroup.objects.create(name='Группа А',
                                                 teacher=self.tutor)

    def screens(self):
        return {
            'искать самому': reverse('teacher:assignment_create'),
            'конструктор контрольной': reverse('teacher:exam_create',
                                               args=[self.group.pk]),
            'конструктор подборки (домашка)':
                reverse('teacher:assignment_build') + '?kind=homework',
            'конструктор подборки (контрольная)':
                reverse('teacher:assignment_build') + '?kind=exam',
        }

    def test_panel_on_every_screen(self):
        for name, url in self.screens().items():
            body = self.client.get(url).content.decode()
            self.assertIn('Настройки работы', body, name)
            self.assertIn('Кому выдать', body, name)
            self.assertIn('id="submit-btn"', body, name)
            self.assertIn('id="submit-why"', body, name)

    def test_no_screen_keeps_its_own_copy_of_the_panel(self):
        """Старые заголовки-близнецы обязаны исчезнуть.

        ⚠️ Ищем РАЗМЕТКУ, а не имя класса: набор стилей вклеен в `<style>`
        страницы, и поиск по имени класса краснел бы всегда (урок сессии 9,
        наступали трижды).
        """
        for name, url in self.screens().items():
            body = self.client.get(url).content.decode()
            self.assertNotIn('Настройки домашки', body, name)
            self.assertNotIn('Настройки контрольной', body, name)
            self.assertNotIn('class="sidebar-card"', body, name)


class ServerFieldNamesUnchanged(TestCase):
    """⚠️ ИМЕНА ПОЛЕЙ — ДОГОВОР С ВЬЮХАМИ. Переименование ломает создание."""

    def setUp(self):
        self.tutor = make_tutor('ws_names')
        self.client.force_login(self.tutor)
        self.group = StudentGroup.objects.create(name='Группа А',
                                                 teacher=self.tutor)

    def names_on(self, url):
        body = self.client.get(url).content.decode()
        return set(re.findall(r'name="([a-z_]+)"', body))

    def test_homework_asks_name_deadline_groups(self):
        for url in (reverse('teacher:assignment_create'),
                    reverse('teacher:assignment_build') + '?kind=homework'):
            names = self.names_on(url)
            self.assertLessEqual({'name', 'deadline', 'groups'}, names, url)

    def test_exam_asks_the_whole_time_block(self):
        expected = {'name', 'kind', 'starts_at', 'ends_at', 'deadline',
                    'duration', 'show_results'}
        for url in (reverse('teacher:exam_create', args=[self.group.pk]),
                    reverse('teacher:assignment_build') + '?kind=exam'):
            self.assertLessEqual(expected, self.names_on(url), url)

    def test_exam_inside_a_group_has_no_groups_field(self):
        """Группа задана адресом; вьюха `groups` не читает вовсе.

        Живое поле `groups` здесь не только лишнее — оно попало бы под
        проверку «выберите группу» в `_picker_js` и заперло бы кнопку.
        """
        body = self.client.get(
            reverse('teacher:exam_create', args=[self.group.pk])).content.decode()
        # ⚠️ Ищем ЭЛЕМЕНТ, а не строку `name="groups"`: та же строка стоит
        # селектором внутри `_build_keep.html`, и наивная проверка краснела
        # бы всегда — родня ловушке «класс набора вклеен в <style>».
        self.assertFalse(re.search(r'<input[^>]*name="groups"', body),
                         'поля выбора занятия здесь быть не должно')
        self.assertIn(self.group.name, body)

    def test_deadline_still_travels_as_a_datetime_local(self):
        """Надстройка — лицо, имя остаётся на родном поле.

        Если имя переедет на текстовое поле, сервер получит «14.08.2026»,
        а `datetime.fromisoformat` его не разберёт и срок пропадёт молча.
        """
        body = self.client.get(reverse('teacher:assignment_create')).content.decode()
        self.assertIn('type="datetime-local"', body)
        self.assertRegex(
            body,
            r'type="datetime-local"[^>]*name="deadline"'
            r'|name="deadline"[^>]*type="datetime-local"')


class GroupAndKindSurviveTheSwitchers(TestCase):
    """⚠️ Номер занятия и вид работы не теряются при переключении."""

    def setUp(self):
        self.tutor = make_tutor('ws_switch')
        self.client.force_login(self.tutor)
        self.group = StudentGroup.objects.create(name='Группа А',
                                                 teacher=self.tutor)

    def test_kind_switcher_keeps_the_group_everywhere(self):
        """Терялся в трёх ссылках из шести — поймано сценарием сессии 10."""
        pk = self.group.pk
        for url in (f"{reverse('teacher:assignment_generate')}?group={pk}",
                    f"{reverse('teacher:assignment_create')}?group={pk}",
                    f"{reverse('teacher:problem_new')}?to_cart=1&group={pk}",
                    reverse('teacher:exam_create', args=[pk])):
            body = self.client.get(url).content.decode()
            # ⚠️ Ссылок теперь ДВА вида: плитки способа набора и
            # сегментированный переключатель вида работы (обзор 13.08,
            # п. 57). Проверять надо оба — иначе половина покрытия
            # исчезла бы молча вместе с классом.
            tiles = (re.findall(r'<a class="k-tile[^"]*"\s+href="([^"]+)"', body)
                     + re.findall(r'<a class="bh-kind__opt[^"]*"\s+href="([^"]+)"',
                                  body))
            self.assertTrue(tiles, url)
            for href in tiles:
                self.assertTrue(
                    f'group={pk}' in href or f'/groups/{pk}/' in href,
                    f'{url}: ссылка потеряла занятие — {href}')

    def test_write_your_own_keeps_kind_and_the_cart(self):
        """«Написать свою» вела на голый problem_new: задача не попадала
        в собираемую работу, а вид работы сбрасывался на домашку."""
        body = self.client.get(
            reverse('teacher:exam_create', args=[self.group.pk])).content.decode()
        own = [h for h in re.findall(r'href="([^"]*problems/new/[^"]*)"', body)]
        self.assertTrue(own, 'ссылки «Написать свою» нет вовсе')
        for href in own:
            self.assertIn('to_cart=1', href)
            self.assertIn('kind=exam', href)

    def test_non_numeric_group_does_not_crash(self):
        """⚠️ `?group=abc` отвечал ПЯТИСОТКОЙ: значение уходило прямо в
        `{% url %}`, и Django бросал NoReverseMatch. Дефект был и до
        сведения панели."""
        for url in (reverse('teacher:assignment_generate'),
                    reverse('teacher:assignment_create'),
                    reverse('teacher:problem_new')):
            for bad in ('abc', 'null', '1; drop', ''):
                response = self.client.get(url, {'group': bad, 'to_cart': '1'})
                # ⚠️ ПЕРЕСЧИТАН (ревью 15.08, фаза 15). Требование прежнее —
                # пятисотки быть не должно; но с этой сессии непонятное
                # занятие не «просто игнорируется», а получает внятный
                # отказ с возвратом на «Ученики». Пустое значение законно и
                # по-прежнему открывает экран.
                expected = (200,) if bad == '' else (200, 302)
                self.assertIn(response.status_code, expected,
                              f'{url}?group={bad}')


class ManualSearchFiltersStayComplete(TestCase):
    """Фильтры собраны в карточку — но ни один не потерян."""

    def setUp(self):
        self.tutor = make_tutor('ws_filters')
        self.client.force_login(self.tutor)

    def test_all_seven_controls_are_there(self):
        body = self.client.get(reverse('teacher:assignment_create')).content.decode()
        form = body[body.index('id="filter-form"'):]
        form = form[:form.index('</form>')]
        for field in ('name="q"', 'name="topic"', 'name="difficulty"',
                      'name="type"', 'name="has_solution"'):
            self.assertIn(field, form)
        self.assertIn('>Найти<', form)
        self.assertIn('Сброс', form)

    def test_the_row_lives_in_a_kit_card(self):
        body = self.client.get(reverse('teacher:assignment_create')).content.decode()
        self.assertRegex(body, r'id="filter-form"[^>]*class="k-card k-filters"'
                               r'|class="k-card k-filters"[^>]*id="filter-form"')


class DateFieldMarkup(TestCase):
    """Поле даты — надстройка, а не замена: без скрипта работает родное."""

    def test_partial_keeps_the_native_input_named(self):
        text = open(DATE_TPL, encoding='utf-8').read()
        self.assertIn('name="{{ field_name }}"', text)
        self.assertIn('type="datetime-local"', text)
        self.assertIn('k-date__text', text)

    def test_ready_class_is_set_last(self):
        """Пока скрипта нет, виден родной `datetime-local`."""
        text = open(DATE_JS, encoding='utf-8').read()
        self.assertIn("classList.add('is-ready')", text)
        self.assertLess(text.index('fromNative();'),
                        text.index("classList.add('is-ready')"))

    def test_hidden_guard_for_the_error_line(self):
        """⚠️ `display` из набора СИЛЬНЕЕ браузерного `[hidden]` — на этом
        обжигались трижды. Без явного правила подсказка висела бы всегда."""
        kit = open(os.path.join(settings.BASE_DIR, 'templates', '_kit.html'),
                   encoding='utf-8').read()
        self.assertIn('.k-date__err[hidden]', kit)
        self.assertIn('.ws-part[hidden]', kit)


@unittest.skipIf(shutil.which('node') is None, 'нет node')
class DateParsingRunsInNode(TestCase):
    """Разбор напечатанной даты — ИСПОЛНЕНИЕМ, а не чтением.

    Питон-тест не увидит опечатки в регулярке: страница отдаст 200, а срок
    у работы окажется пустым.
    """

    def run_js(self, body):
        """Чистые функции разбора из боевого скрипта + переданный кусок.

        ⚠️ ПЕРЕСЧИТАН ДВАЖДЫ, ни разу не отключён. Сперва (15.08) разбор
        перестал быть одной регуляркой `toIso` и стал маской из цифр; затем
        (16.08) разделитель снова стал значащим — он ЗАКРЫВАЕТ поле, и
        двузначный год опять понимается. Границы срока передаются явно,
        чтобы проверка формата не зависела от сегодняшнего числа.
        Способ проверки прежний: исполнением в node.
        """
        from problems.tests.test_r15_date import _functions

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as handle:
            handle.write('(function () {\n' + _functions() + '\n'
                         + body + '\n})();')
            path = handle.name
        try:
            done = subprocess.run(['node', path], capture_output=True,
                                  text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            return done.stdout.strip()
        finally:
            os.unlink(path)

    # Широкие границы: этот класс проверяет ФОРМАТ, а не потолок срока.
    WIDE = ("{min: dateFromIso('2000-01-01T00:00'), "
            "max: dateFromIso('2099-12-31T23:59')}")

    def iso(self, text, default='23:59'):
        return self.run_js(
            "var r = parse(%r, %r, %s);"
            "console.log(r.why ? 'null' : r.iso);"
            % (text, default, self.WIDE))

    def test_script_parses(self):
        source = open(DATE_JS, encoding='utf-8').read()
        source = source[source.index('<script>') + len('<script>'):]
        source = source[:source.index('</script>')]
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as handle:
            handle.write(source)
            path = handle.name
        try:
            done = subprocess.run(['node', '--check', path],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
        finally:
            os.unlink(path)

    def test_russian_input_becomes_iso(self):
        self.assertEqual(self.iso('14.08.2026, 20:00'), '2026-08-14T20:00')

    def test_date_without_time_takes_the_default(self):
        self.assertEqual(self.iso('01.09.2026'), '2026-09-01T23:59')

    def test_separators_do_not_matter_at_all(self):
        """⚠️ ГЛАВНОЕ ИЗМЕНЕНИЕ: разделители расставляет поле, а не человек.

        Двузначный год при этом больше не понимается — и не может: в маске
        из одних цифр «14.08.26 20:00» неотличимо от «14.08.2620, ...».
        Цена размена названа вслух: набор без разделителей работает, а
        сокращённый год — нет.
        """
        for text in ('14/08/2026 20:00', '14-08-2026, 20:00',
                     '14082026 2000', '140820262000',
                     # ⚠️ ПЕРЕСЧИТАН 16.08: двузначный год снова понимается.
                     '140826 2000', '14.08.26, 20:00'):
            self.assertEqual(self.iso(text), '2026-08-14T20:00', text)

    def test_impossible_dates_are_refused(self):
        """31 февраля обязано быть ошибкой, а не 3 марта."""
        for text in ('31.02.2026', '32.01.2026', '14.13.2026',
                     '14.08.2026, 25:00', '14.08'):
            # Замечание: границы здесь широкие, значит отказ приходит
            # именно от календаря, а не от потолка срока.
            self.assertEqual(self.iso(text), 'null', text)

    def test_letters_never_reach_the_field(self):
        """⚠️ «вчера» — это не «невозможная дата», это НЕ ДАТА ВОВСЕ.

        Маска пропускает только цифры, поэтому буквы в поле не появляются
        даже вставкой: поле остаётся пустым, и это видно. Пустое поле —
        законный ответ «срока нет», а не молчаливое обнуление набранного.
        """
        self.assertEqual(
            self.run_js("console.log('[' + maskOf(fieldsOf('вчера')) + ']');"),
            '[]')
        self.assertEqual(self.iso('вчера'), '')

    def test_refusal_speaks_words(self):
        """Молчаливый ноль — то, из-за чего затевалась фаза."""
        why = self.run_js("console.log(parse('14.08', '23:59', %s).why);"
                          % self.WIDE)
        self.assertTrue(len(why) > 15, why)

    def test_mask_writes_the_separators(self):
        out = self.run_js("console.log(maskOf(fieldsOf('140820262000')));")
        self.assertEqual(out, '14.08.2026, 20:00')
