# -*- coding: utf-8 -*-
"""Календарь: кнопка добавления вернулась, и чужой текст не стал кодом.

Две починки 01.09.2026, обе стерегутся здесь.

1. **Кнопка была мёртвой.** Весь экран календаря — один инлайн-скрипт,
   который НАЧИНАЛСЯ с `new FullCalendar.Calendar(…)` и только двадцатью
   строками ниже вешал обработчик кнопки. Библиотека тянется с чужого CDN;
   стоило ему не доехать, скрипт умирал на первой же строке, и кнопка
   «+ Добавить» оставалась на экране, ничего не делая. Ни ошибки, ни
   сообщения — ровно «добавлять события больше нельзя».
   Замер обеих веток — `reports/CALENDAR_AUDIT.md`.

2. **Право считалось в двух местах по-разному.** Шаблон смотрел на СТАРОЕ
   поле `user.role`, а API пускает по `is_tutor`, который знает обе системы
   ролей. ⚠️ ЭТО НЕ БЫЛО ПРИЧИНОЙ ПОЛОМКИ, вопреки первоначальной догадке:
   `UserProfile.save` зовёт `sync_user_role`, и репетитора, у которого
   профиль говорит «tutor», а старое поле — что-то другое, попросту не
   существует. Расхождение всё равно снято: право теперь считается в одном
   месте и той же проверкой, что на сервере, — экран больше не зависит от
   того, продолжает ли работать синхронизация.

⚠️ JSON РАЗБИРАЕТСЯ, А НЕ ИЩЕТСЯ ПО СЫРОМУ ТЕЛУ. Прошлая сессия обожглась
на этом: кириллица в JSON закодирована escape-последовательностями, и
проверка «текста нет в ответе» молча зеленела бы и при утечке.
"""
import io
import json
import os

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import CalendarEvent

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE = os.path.join(ROOT, 'calendar_stub', 'templates',
                    'calendar_stub', 'calendar.html')
User = get_user_model()


def read_page():
    with io.open(PAGE, encoding='utf-8') as handle:
        return handle.read()


def tutor_via_profile(name='profile_tutor'):
    """Репетитор, заведённый через новую систему ролей (`UserProfile`)."""
    user = User.objects.create_user(username=name, password='x')
    user.role = 'viewer'
    user.save()
    profile = getattr(user, 'profile', None)
    if profile is not None:
        profile.role = 'tutor'
        profile.save()
    user.refresh_from_db()
    return user


class AddButtonMatchesTheServerTests(TestCase):
    """Кнопку видит ровно тот, кому сервер разрешает создавать."""

    def _button_shown(self, user=None):
        if user is not None:
            self.client.force_login(user)
        html = self.client.get(reverse('calendar_stub:calendar')).content.decode()
        # Ищем сам ЭЛЕМЕНТ, а не строку `btn-add-event`: она встречается и
        # в скрипте, и такая проверка была бы зелёной для гостя тоже.
        return '<button class="btn btn-primary" id="btn-add-event"' in html

    def _can_create(self, user=None):
        if user is not None:
            self.client.force_login(user)
        return self.client.post(
            reverse('calendar_stub:event_create'),
            data=json.dumps({'title': 'Проверочное событие',
                             'date': '2026-09-12', 'time_start': '10:00'}),
            content_type='application/json').status_code

    def test_репетитор_из_профиля_видит_кнопку_и_создаёт(self):
        tutor = tutor_via_profile()
        self.assertEqual(self._can_create(tutor), 200,
                         'Сервер обязан пускать репетитора из UserProfile.')
        self.assertTrue(self._button_shown(tutor),
                        'Сервер пускает, а кнопки нет: экран врёт, что '
                        'добавлять нельзя.')

    def test_две_системы_ролей_синхронизируются(self):
        """⚠️ ПОЧЕМУ ЭТО ЗДЕСЬ: гипотеза о причине поломки была ДРУГОЙ.

        Считалось, что репетитор из `UserProfile` не видит кнопку, потому
        что шаблон смотрел старое поле `user.role`, а API — `is_tutor`.
        Проверка показала: такого человека не существует. `UserProfile.save`
        зовёт `sync_user_role`, и `profile.role = 'tutor'` сам ставит
        `user.role = 'teacher'`. Расхождение шаблона и API было настоящим,
        но недостижимым, а причина поломки оказалась в другом (порядок
        строк в скрипте — см. класс ниже).

        Проверка сторожит саму синхронизацию: пока она работает, старое
        поле остаётся верным; сломается — покраснеет здесь, а не молча
        на экране календаря.
        """
        tutor = tutor_via_profile('sync_probe')
        self.assertEqual(tutor.profile.role, 'tutor')
        self.assertEqual(tutor.role, 'teacher',
                         'Синхронизация ролей сломалась: старое поле '
                         'разошлось с профилем.')

    def test_право_на_экране_и_на_сервере_из_одного_места(self):
        """Разметка не считает право сама, а берёт готовый признак.

        ⚠️ ЭТО СТРУКТУРНАЯ ПРОВЕРКА, И НАЗВАНА ОНА ЧЕСТНО. Поведением её
        не выразить: пока роли синхронизируются, оба способа дают один
        ответ, и подмена одного на другой ничего не меняет на экране.
        Сторожим именно то, что можно: в шаблоне ровно один источник
        права, и это тот же `is_tutor`, которым пускает API.
        """
        page = read_page()
        self.assertIn('{% if can_create %}', page)
        self.assertNotIn("user_role == 'teacher' or user_role == 'admin'", page)
        views = io.open(os.path.join(ROOT, 'calendar_stub', 'views.py'),
                        encoding='utf-8').read()
        self.assertIn('can_create = bool(user.is_superuser or is_tutor(user))',
                      views)

    def test_старый_репетитор_тоже_видит(self):
        tutor = User.objects.create_user(username='old_tutor', password='x')
        tutor.role = 'teacher'
        tutor.save()
        self.assertEqual(self._can_create(tutor), 200)
        self.assertTrue(self._button_shown(tutor))

    def test_ученику_кнопки_нет_и_сервер_отказывает(self):
        student = User.objects.create_user(username='pupil', password='x')
        student.role = 'student'
        student.save()
        self.assertEqual(self._can_create(student), 403)
        self.assertFalse(self._button_shown(student))

    def test_гостю_кнопки_нет(self):
        """У кого права нет — кнопки НЕТ ВОВСЕ, а не серая неактивная."""
        self.assertFalse(self._button_shown())


class ButtonSurvivesTheLibraryTests(TestCase):
    """Обработчик кнопки не зависит от чужой библиотеки."""

    def test_обработчик_вешается_раньше_построения_календаря(self):
        """⚠️ ИМЕННО ПОРЯДОК И БЫЛ ПРИЧИНОЙ ПОЛОМКИ.

        Если `new FullCalendar.Calendar(…)` снова встанет выше привязки,
        любой сбой CDN опять оставит на экране кнопку, которая ничего не
        делает, — без единой ошибки на виду.
        """
        page = read_page()
        привязка = page.index("getElementById('btn-add-event')")
        построение = page.index('new FullCalendar.Calendar(')
        self.assertLess(привязка, построение,
                        'Обработчик кнопки снова вешается ПОСЛЕ построения '
                        'календаря — падение CDN опять убьёт кнопку.')

    def test_отсутствие_библиотеки_объясняется_словами(self):
        """Пустой прямоугольник неотличим от «сайт сломался».

        ⚠️ ПРОВЕРКА ЖДЁТ ДВА ВХОЖДЕНИЯ, И ЭТО НЕ ПРИДИРКА. Признак нужен
        в двух местах: одно решает, строить ли календарь, второе — писать
        ли человеку, что сетка не приехала. Первая версия проверки искала
        одно вхождение и оставалась зелёной, когда объяснение отключали.
        """
        page = read_page()
        self.assertGreaterEqual(
            page.count("typeof FullCalendar === 'undefined'"), 2,
            'Признак «библиотека не доехала» перестал прикрывать оба '
            'места: либо построение, либо объяснение человеку.')
        self.assertIn('cal-offline', page)
        self.assertIn('Сетка календаря не загрузилась', page)


class ForeignTextNeverBecomesMarkupTests(TestCase):
    """Название, описание и имя группы — данные, а не код."""

    ЯД = '<img src=x onerror=alert(1)>'

    def setUp(self):
        self.tutor = User.objects.create_user(username='xss_tutor', password='x')
        self.tutor.role = 'teacher'
        self.tutor.save()
        self.event = CalendarEvent.objects.create(
            title='Событие ' + self.ЯД,
            description='http://example.com/"' + self.ЯД,
            start_datetime=timezone.now(),
            author=self.tutor, is_global=True,
        )

    def test_в_скрипте_нет_ни_одной_сборки_разметки(self):
        """⚠️ ЗАПРЕТ НА САМ СПОСОБ, А НЕ НА КОНКРЕТНОЕ МЕСТО.

        Дыр было две, и обе одинаковые: чужая строка склеивалась в
        разметку и вставлялась целиком. Стеречь два места по отдельности
        значит ждать третьего.
        """
        page = read_page()
        for приём in ('innerHTML', 'insertAdjacentHTML', 'outerHTML',
                      'document.write'):
            self.assertNotIn(приём, page,
                             'В скрипте календаря снова собирается разметка '
                             'через %s.' % приём)

    def test_адрес_не_склеивается_строкой(self):
        page = read_page()
        for образец in ('href="${', "href='${", 'href=${'):
            self.assertNotIn(образец, page)
        # Схема проверяется разрешённым списком, а не запрещённым.
        self.assertIn('safeLink', page)

    def test_разметка_уезжает_в_json_данными(self):
        """⚠️ РАЗБИРАЕМ JSON, А НЕ ИЩЕМ ПО СЫРОМУ ТЕЛУ.

        В сыром теле кириллица и угловые скобки закодированы, и поиск
        подстроки молча зеленел бы при любом поведении.
        """
        self.client.force_login(self.tutor)
        данные = self.client.get(reverse('calendar_stub:events_api')).json()
        наше = [e for e in данные
                if e['extendedProps']['full_title'].endswith(self.ЯД)]
        self.assertEqual(len(наше), 1,
                         'Событие не вернулось — проверять нечего.')
        props = наше[0]['extendedProps']
        # Значение доезжает ЦЕЛИКОМ и не искажается: экран обязан
        # положить его текстом, а не разобрать как разметку.
        self.assertEqual(props['full_title'], 'Событие ' + self.ЯД)
        self.assertIn(self.ЯД, props['description'])
