# -*- coding: utf-8 -*-
"""Что гостю открыли, а что оставили закрытым.

01.09.2026 решением владельца два раздела открыты без входа: графический
калькулятор `/calc2/` и календарь `/calendar/`. Повод — лендинг: карточки
«Графический калькулятор» и «Календарь олимпиадника» вели гостя не в раздел,
а в форму входа, то есть две карточки из пяти были тупиком.

⚠️ ЭТОТ ФАЙЛ ЕСТЬ ПОТОМУ, ЧТО БЕЗ НЕГО ПРАВКА БЫЛА БЫ НЕ ПРОВЕРЕНА. Открыть
страницу легко, а вот НЕ открыть заодно всё остальное — это и есть работа.
Проверок здесь два сорта, и вторые важнее:
  · «своё открылось» — гость видит калькулятор и календарь;
  · «чужое не открылось» — гость не пишет в базу, не тратит процессор
    сервера на pdflatex и не видит ни одного события, кроме общих.

⚠️ Тест «свой прошёл» без парного «чужой не прошёл» не считается закрытым.
Поэтому у каждой открытой двери здесь стоит отрицательная пара.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import CalendarEvent, StudentGroup

User = get_user_model()

PASSWORD = 'proverka12345'


class GuestOpenPagesTests(TestCase):
    """Гость видит обе страницы, ради которых всё и затевалось."""

    def setUp(self):
        self.client = Client()

    def test_calculator_page_is_open(self):
        self.assertEqual(self.client.get('/calc2/').status_code, 200)

    def test_calendar_page_is_open(self):
        self.assertEqual(self.client.get('/calendar/').status_code, 200)

    def test_landing_cards_lead_where_they_promise(self):
        """Карточки лендинга ведут гостя в раздел, а не в форму входа.

        Проверяется ИМЕННО связка «адрес из карточки → код 200»: разойдись
        адрес в шаблоне с открытым маршрутом, тупик вернулся бы молча.
        """
        home = self.client.get('/').content.decode()
        for href in ('/calc2/', '/calendar/', '/game/', '/catalog/'):
            self.assertIn('href="%s"' % href, home,
                          'на лендинге нет карточки на %s' % href)
            self.assertEqual(self.client.get(href).status_code, 200,
                             'карточка ведёт в тупик: %s' % href)


class GuestIsStillLockedOutTests(TestCase):
    """Открыли страницы — но не запись и не чужие данные."""

    def setUp(self):
        self.client = Client()

    def _is_login_redirect(self, resp):
        return resp.status_code == 302 and '/login/' in resp['Location']

    def test_pdf_export_stays_closed(self):
        """pdflatex по команде анонима не запускается.

        Это не про данные, а про процессор: эндпоинт компилирует присланный
        клиентом файл, и открытый наружу он становится рычагом нагрузки.
        """
        resp = self.client.post('/calc2/export/pdf/',
                                data={'tex': 'x'})
        self.assertTrue(self._is_login_redirect(resp),
                        'export_pdf ответил %s' % resp.status_code)

    def test_graph_save_stays_closed(self):
        resp = self.client.post(reverse('api_graph_save'),
                                data='{}', content_type='application/json')
        self.assertTrue(self._is_login_redirect(resp),
                        'api_graph_save ответил %s' % resp.status_code)

    def test_event_create_stays_closed(self):
        resp = self.client.post(reverse('calendar_stub:event_create'),
                                data='{"title": "Гостевое"}',
                                content_type='application/json')
        self.assertTrue(self._is_login_redirect(resp),
                        'event_create ответил %s' % resp.status_code)
        self.assertFalse(CalendarEvent.objects.filter(title='Гостевое').exists(),
                         'гость записал событие в базу')

    def test_event_update_stays_closed(self):
        resp = self.client.post(
            reverse('calendar_stub:event_update', args=[1]),
            data='{"title": "Переименовано"}',
            content_type='application/json')
        self.assertTrue(self._is_login_redirect(resp),
                        'event_update ответил %s' % resp.status_code)

    def test_event_delete_stays_closed(self):
        resp = self.client.post(
            reverse('calendar_stub:event_delete', args=[1]),
            data='{}', content_type='application/json')
        self.assertTrue(self._is_login_redirect(resp),
                        'event_delete ответил %s' % resp.status_code)

    def test_event_detail_stays_closed(self):
        """Карточка одного события гостю не нужна: интерфейс её не зовёт.

        Открывать эндпоинт «за компанию» нельзя — правило наименьших прав.
        """
        resp = self.client.get(
            reverse('calendar_stub:event_detail', args=[1]))
        self.assertTrue(self._is_login_redirect(resp),
                        'event_detail ответил %s' % resp.status_code)


class GuestSeesOnlyGlobalEventsTests(TestCase):
    """Лента событий открыта на чтение, но гостю уходят только общие.

    ⚠️ ГЛАВНАЯ ПРОВЕРКА ФАЙЛА. Отбор делает `_visible_qs`, и до 01.09.2026
    аноним в неё не заходил вовсе: вью стояла за `@login_required`, и ветка
    «всё остальное» ловила бы его по случайности. Теперь ветка для гостя
    написана явно, а этот тест сторожит, что она именно такая.
    """

    @classmethod
    def setUpTestData(cls):
        teacher = User.objects.create_user('guest_t', password=PASSWORD,
                                           role='teacher')
        student = User.objects.create_user('guest_s', password=PASSWORD,
                                           role='student')
        group = StudentGroup.objects.create(name='Группа', teacher=teacher)
        group.students.add(student)
        now = timezone.now()
        cls.public = CalendarEvent.objects.create(
            title='ВсОШ, региональный этап', author=teacher,
            start_datetime=now, is_global=True)
        cls.private = CalendarEvent.objects.create(
            title='СЕКРЕТНОЕ занятие группы', author=teacher,
            start_datetime=now, is_global=False)
        cls.private.groups.add(group)

    def setUp(self):
        self.client = Client()

    def _titles(self):
        """Названия событий из ответа — РАЗБОРОМ JSON, а не поиском по телу.

        ⚠️ ПРОВЕРКА ПО СЫРОМУ ТЕЛУ ЗДЕСЬ НЕ РАБОТАЕТ И МОЛЧА ЗЕЛЕНЕЕТ.
        `JsonResponse` уводит кириллицу в `\\uXXXX`, поэтому
        `assertNotIn('СЕКРЕТНОЕ', resp.content)` проходит ВСЕГДА — и когда
        событие не уехало, и когда уехало. Первая версия этого файла так и
        была написана; поймал соседний тест, который тем же способом искал
        событие и не нашёл его там, где оно точно есть.
        """
        data = self.client.get(reverse('calendar_stub:events_api')).json()
        return [e['extendedProps']['full_title'] for e in data]

    def test_guest_gets_the_global_event(self):
        self.assertTrue(any('ВсОШ' in t for t in self._titles()))

    def test_guest_does_not_get_the_group_event(self):
        self.assertFalse(any('СЕКРЕТНОЕ' in t for t in self._titles()),
                         'гостю уехало событие группы')

    def test_guest_gets_exactly_one_event(self):
        """Число, а не только отсутствие строки: подсчёт ловит и то, что
        событие уехало под другим именем."""
        data = self.client.get(reverse('calendar_stub:events_api')).json()
        self.assertEqual(len(data), 1, 'гостю уехало %d событий' % len(data))

    def test_guest_cannot_edit_what_he_sees(self):
        """У общего события гостю не приходит признак «можно править»."""
        data = self.client.get(reverse('calendar_stub:events_api')).json()
        self.assertFalse(data[0]['extendedProps']['can_edit'])

    def test_student_still_sees_his_group_event(self):
        """Регрессия: правка для гостя не отняла событие у своего ученика."""
        self.assertTrue(
            self.client.login(username='guest_s', password=PASSWORD))
        self.assertTrue(any('СЕКРЕТНОЕ' in t for t in self._titles()),
                        'ученик перестал видеть событие своей группы')
