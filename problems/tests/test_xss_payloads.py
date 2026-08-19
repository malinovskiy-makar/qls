# -*- coding: utf-8 -*-
"""Активный контент: вредная строка не выполняется в браузере.

Корпус задач — это активное содержимое. 31 690 задач приехали из внешних
источников, свои задачи пишут репетиторы, комментарии пишут ученики, часть
текста дописывает модель. Всё это попадает на экран преподавателя, ученика
и в админку — то есть под учётную запись с полными правами.

⚠️ ПРОВЕРЯЕТСЯ СЫРОЕ ТЕЛО ОТВЕТА. Смотреть «на экране ничего не мигнуло»
бессмысленно: нагрузка либо доехала до браузера открывающим угловым
скобком, либо нет. Поэтому каждая проверка ищет строку в
`response.content` целиком — вместе с data-атрибутами и встроенным JS.

⚠️ ЛОВУШКА `\\uXXXX` (см. docs/TESTING.md). `JsonResponse` экранирует
кириллицу, и русский маркер лежит в теле как `\\u041c...`. Поиск обычной
строки его не найдёт и будет ЗЕЛЁНЫМ на утёкшем ответе. Здесь маркеры
намеренно латинские с цифрами — они выглядят в JSON одинаково; но поиск
всё равно идёт по обеим формам (`_both_forms`), чтобы ловушка не сработала
на том, кто завтра добавит русский маркер.

Как устроена проверка каждой нагрузки:

* `raw` — то, что положили в поле. Его в теле быть НЕ ДОЛЖНО: значит,
  экранирование не сработало и браузер увидит настоящий тег;
* `marker` — редкая строка внутри нагрузки. Её в теле быть ОБЯЗАНО:
  иначе тест зелёный просто потому, что поле не доехало до страницы,
  и не проверяет ничего.

Второе условие — главное. Без него достаточно сломать выборку, и весь
файл станет зелёным на пустых страницах.
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, Problem, ProblemPart, StudentGroup,
)
from problems.models_platform import CustomProblem, ProblemComment, SavedProblem

User = get_user_model()

PASSWORD = 'proverka12345'


class Payload(object):
    """Одна вредная строка и способ узнать её в теле ответа.

    `is_markup` — содержит ли нагрузка угловые скобки. У таких проверка
    строгая: сырой строки в теле быть не должно вовсе.

    Нагрузка на KaTeX (`\\href{javascript:...}`) угловых скобок НЕ содержит,
    поэтому в теле она законно лежит текстом — и должна там лежать: условие
    задачи показывают как есть. Опасной её делает не разметка, а настройка
    `trust` у KaTeX, и проверяется именно она.
    """

    def __init__(self, key, raw, marker, why, is_markup=True):
        self.key = key
        self.raw = raw
        self.marker = marker
        self.why = why
        self.is_markup = is_markup

    def __repr__(self):
        return '<Payload %s>' % self.key


# Набор нагрузок. Каждая — отдельный способ выполнить код в чужом браузере.
PAYLOADS = [
    Payload('script', '<script>alert("XSSMARKA1")</script>', 'XSSMARKA1',
            'прямой тег скрипта'),
    Payload('img_onerror', '<img src=x onerror="alert(1)">XSSMARKB2',
            'XSSMARKB2', 'обработчик события на битой картинке'),
    Payload('svg_onload', '<svg onload="alert(1)"></svg>XSSMARKC3',
            'XSSMARKC3', 'обработчик на SVG — проходит там, где режут script'),
    Payload('iframe', '<iframe src="javascript:alert(1)"></iframe>XSSMARKD4',
            'XSSMARKD4', 'чужая страница внутри нашей'),
    Payload('latex_href', '\\href{javascript:alert(1)}{XSSMARKE5}',
            'XSSMARKE5', 'ссылка средствами KaTeX — работает при trust: true',
            is_markup=False),
    Payload('script_break', 'XSSMARKF6</script><script>alert(1)</script>',
            'XSSMARKF6', 'выход из блока <script> — бьёт по JSON в разметке'),
]

# Нагрузка для полей, куда попадает АДРЕС, а не текст.
JS_URL = 'javascript:alert("XSSMARKG7")'

# Живые открывающие теги: именно они отличают нагрузку от текста.
LIVE_TAGS = (
    '<script>alert',
    '<img src=x onerror',
    '<svg onload',
    '<iframe src="javascript:',
    '</script><script>',
)


def _both_forms(text):
    """Строка и её вид внутри JSON: `JsonResponse` экранирует не только кириллицу."""
    return [text, json.dumps(text, ensure_ascii=True)[1:-1]]


class XssTestCase(TestCase):
    """Общая заготовка: нагрузки уже лежат во всех полях, которые видны."""

    @classmethod
    def setUpTestData(cls):
        raws = dict((p.key, p.raw) for p in PAYLOADS)

        cls.tutor = User.objects.create_user('xss_tutor', password=PASSWORD,
                                             role='teacher')
        cls.student = User.objects.create_user('xss_pupil', password=PASSWORD,
                                               role='student')
        cls.staff = User.objects.create_user('xss_staff', password=PASSWORD,
                                             role='teacher', is_staff=True,
                                             is_superuser=True)
        # Имя пользователя тоже показывается — и репетитору, и в админке.
        cls.student.first_name = raws['img_onerror']
        cls.student.save(update_fields=['first_name'])

        # Название занятия и работы печатает репетитор, а уезжают они
        # в JSON внутри <script> на экране календаря и каталога.
        cls.group = StudentGroup.objects.create(
            name='Группа ' + raws['script_break'], teacher=cls.tutor)
        cls.group.students.add(cls.student)

        cls.problem = Problem.objects.create(
            title='Заголовок ' + raws['script'],
            statement='Условие ' + raws['img_onerror'] + ' $P = 10 - Q$',
            solution='Решение ' + raws['svg_onload'],
            answer='Ответ ' + raws['iframe'],
            status=Problem.Status.PUBLISHED,
        )
        ProblemPart.objects.create(
            problem=cls.problem, label='а', order=0,
            statement='Подпункт ' + raws['latex_href'])

        cls.assignment = Assignment.objects.create(
            name='Работа ' + raws['script_break'],
            author=cls.tutor, group=cls.group)
        cls.assignment.students.add(cls.student)
        cls.assignment.problems.add(cls.problem)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.assignment, catalog_problem=cls.problem, order=0)

        # Своя задача репетитора — текст, который пишет живой человек.
        cls.custom = CustomProblem.objects.create(
            owner=cls.tutor, title='Своя ' + raws['script'],
            statement='Своё условие ' + raws['svg_onload'])

        # Комментарий в паре «ученик ↔ его репетитор».
        ProblemComment.objects.create(
            assignment=cls.assignment, problem_item=cls.item,
            author=cls.student, recipient=cls.tutor,
            text='Комментарий ' + raws['iframe'])

        SavedProblem.objects.create(owner=cls.student,
                                    catalog_problem=cls.problem)

    # ── помощники ───────────────────────────────────────────────────────
    def assert_inert(self, response, where, expect_seen=True):
        """Ни одна нагрузка не доехала живой; но поля на странице ЕСТЬ."""
        body = response.content.decode('utf-8', 'replace')
        seen = []
        for payload in PAYLOADS:
            if payload.is_markup:
                for form in _both_forms(payload.raw):
                    self.assertNotIn(
                        form, body,
                        '%s: нагрузка «%s» (%s) приехала в тело ответа как '
                        'есть — браузер её выполнит.'
                        % (where, payload.key, payload.why),
                    )
            if any(f in body for f in _both_forms(payload.marker)):
                seen.append(payload.key)

        # Ни одна ссылка не должна получить схему javascript:
        for bad_href in ('href="javascript:', "href='javascript:"):
            self.assertNotIn(bad_href, body, '%s: ссылка javascript:' % where)

        # Где страница рисует формулы — там доверие обязано быть выключено
        # ЯВНО. Иначе `\href{javascript:...}` в условии задачи станет рабочей
        # ссылкой, стоит кому-нибудь поставить trust: true.
        if 'renderMathInElement(' in body:
            self.assertIn(
                'trust: false', body,
                '%s: KaTeX вызывается без явного trust: false' % where)

        for bad in LIVE_TAGS:
            for form in _both_forms(bad):
                self.assertNotIn(
                    form, body, '%s: живой тег «%s» в теле' % (where, bad))

        if expect_seen:
            self.assertTrue(
                seen,
                '%s: ни один маркер не найден в теле — страница НЕ показывает '
                'проверяемые поля, и тест ничего не доказывает.' % where,
            )
        return seen

    def login(self, username):
        client = Client()
        self.assertTrue(client.login(username=username, password=PASSWORD))
        return client


class CatalogXssTests(XssTestCase):
    """Публичный каталог — сюда смотрит кто угодно, вход не нужен."""

    def test_problem_list(self):
        # ⚠️ С пустым запросом каталог показывает атлас тем, а не карточки:
        # без `?q=` страница была бы пустой, и проверка ничего не значила бы.
        response = Client().get(
            reverse('catalog:problem_list') + '?q=XSSMARKB2')
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'каталог, список')

    def test_problem_detail(self):
        response = Client().get(
            reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'каталог, страница задачи')

    def test_catalog_json_api_is_json_and_not_sniffable(self):
        """У JSON-ответа защита другая, и проверять надо именно её.

        ⚠️ В теле этого ответа условие задачи лежит КАК ЕСТЬ — вместе с
        угловыми скобками. Это не дыра и не может ею быть: браузер не
        разбирает `application/json` как разметку, а `nosniff` запрещает
        ему передумать. Требовать здесь экранирования было бы требованием
        испортить данные: окно предпросмотра показывает то, что пришло.

        Дыра начиналась ДАЛЬШЕ — там, где эти данные попадали на страницу.
        Раньше окно собирало разметку строкой и клало её в `innerHTML`;
        теперь собирает узлами (`test_modal_builds_nodes_not_html` ниже).
        """
        response = Client().get(
            reverse('catalog:api_problem', args=[self.problem.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.headers.get('X-Content-Type-Options'),
                         'nosniff')

    def test_modal_builds_nodes_not_html(self):
        """Окно предпросмотра не собирает разметку из данных строкой.

        Самая серьёзная находка сессии 3Б: `bodyHtml` склеивался из
        `data.statement` и уезжал в `innerHTML`. Условие приходит прямо из
        банка (31 690 задач из внешних источников), страница публичная,
        вход не нужен. Тест смотрит исходник страницы: возврата к склейке
        не будет незаметно.
        """
        from pathlib import Path

        from django.conf import settings

        source = (Path(settings.BASE_DIR) / 'catalog' / 'templates'
                  / 'catalog' / 'problem_list.html').read_text(encoding='utf-8')
        for bad in ('${data.statement}', '${part.text', '${a.name}',
                    '${t}</span>'):
            self.assertNotIn(
                bad, source,
                'Данные снова склеиваются в строку разметки: %s' % bad)

    def test_catalog_under_tutor(self):
        """Названия работ уезжают в <script> — там `</script>` смертелен."""
        client = self.login('xss_tutor')
        response = client.get(
            reverse('catalog:problem_list') + '?q=XSSMARKB2')
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'каталог под репетитором')


class StudentXssTests(XssTestCase):
    """Кабинет ученика: условие, подпункты, комментарии."""

    def test_dashboard(self):
        client = self.login('xss_pupil')
        response = client.get(reverse('student:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'кабинет ученика, список работ')

    def test_assignment_detail(self):
        """Экран работы: условие задачи ученик видит до сдачи.

        Разбор (`work_review`) до сдачи уводит редиректом сюда — значит,
        именно этот экран и показывает текст задачи ученику.
        """
        client = self.login('xss_pupil')
        response = client.get(
            reverse('student:assignment_detail', args=[self.assignment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'кабинет ученика, экран работы')

    def test_saved_tab(self):
        client = self.login('xss_pupil')
        response = client.get(reverse('profile') + '?tab=saved')
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'профиль, «Сохранённое»')


class TutorXssTests(XssTestCase):
    """Панель репетитора: чужой текст под учёткой с правами на группу."""

    def test_group_detail(self):
        client = self.login('xss_tutor')
        response = client.get(
            reverse('teacher:group_detail', args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'панель репетитора, занятие')

    def test_group_assignment(self):
        client = self.login('xss_tutor')
        response = client.get(reverse(
            'teacher:group_assignment',
            args=[self.group.pk, self.assignment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'панель репетитора, работа')

    def test_calendar(self):
        """Названия групп и работ едут в <script> сырым JSON."""
        client = self.login('xss_tutor')
        response = client.get('/calendar/')
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'календарь')


class AdminXssTests(XssTestCase):
    """Админка — самое опасное место: полные права у того, кто смотрит."""

    def test_problem_changelist(self):
        client = self.login('xss_staff')
        response = client.get('/admin/problems/problem/')
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'админка, список задач')

    def test_problem_change_form(self):
        client = self.login('xss_staff')
        response = client.get(
            '/admin/problems/problem/%s/change/' % self.problem.pk)
        self.assertEqual(response.status_code, 200)
        self.assert_inert(response, 'админка, карточка задачи')


class UrlFieldXssTests(XssTestCase):
    """Адрес со схемой `javascript:` не должен стать ссылкой."""

    def test_javascript_url_not_rendered_as_href(self):
        problem = Problem.objects.create(
            title='Ссылка', statement='Смотри ' + JS_URL,
            status=Problem.Status.PUBLISHED)
        response = Client().get(
            reverse('catalog:problem_detail', args=[problem.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8', 'replace')
        self.assertNotIn('href="javascript:', body)
        self.assertNotIn("href='javascript:", body)


class ControlTests(XssTestCase):
    """Контроль: обычная задача по-прежнему показывается целиком.

    Без этого «починку» можно сделать запретом всего: тесты зелёные,
    продукт пустой.
    """

    def test_normal_problem_is_still_shown(self):
        problem = Problem.objects.create(
            title='Обычная задача про КПВ',
            statement='Постройте КПВ по данным: $Q_1 = 10$.',
            status=Problem.Status.PUBLISHED)
        response = Client().get(
            reverse('catalog:problem_detail', args=[problem.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8', 'replace')
        self.assertIn('Постройте КПВ по данным', body)
        self.assertIn('Q_1 = 10', body)
