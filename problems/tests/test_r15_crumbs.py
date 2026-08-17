"""
Объединённое ревью 15.08, фаза 2 — крошки.

Пункт 20 владельца и маршрут 11.

⚠️ ЧТО ЗАМЕРЕНО ПЕРЕД ПРАВКОЙ. Прежняя сборка (коммит 45b5780, до обзора
13.08) была поднята рядом на своём порту и обойдена тем же скриптом: правила
`.crumbs` и вычисленные цвета совпали С НЫНЕШНИМИ ДО ЕДИНОГО ЗНАЧЕНИЯ —
контейнер `rgb(91,100,114)` 13px, ссылки `rgb(190,24,93)` без подчёркивания,
а три экрана создания в ОБЕИХ сборках рисовали крошку голой браузерной синью
`rgb(0,0,238)` подчёркиванием и кеглем 15. То есть обзор 13.08 крошки не
портил: он изменил ровно одно слово («Группы» → «Ученики»), а дыра в покрытии
была и до него.

Поэтому «вернуть прежний вид» здесь означает не откат, а то, что владелец
описал словами: звенья и стрелки акцентом, последнее звено обычным цветом
текста — и один и тот же вид на ВСЕХ экранах.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.tests.factories import make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def markup_files():
    for folder in ('templates', 'teacher', 'student', 'problems/templates',
                   'catalog/templates'):
        for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            if 'node_modules' in base:
                continue
            for name in files:
                if name.endswith('.html'):
                    path = os.path.join(base, name)
                    with open(path, encoding='utf-8') as handle:
                        yield os.path.relpath(path, ROOT), handle.read()


class RulesLiveInTheKitTests(TestCase):
    """Класс стоит больше чем на одном экране — правила живут в наборе."""

    def test_kit_defines_crumbs(self):
        kit = read('templates', '_kit.html')
        self.assertIn('.crumbs {', kit)
        self.assertIn('.crumbs a {', kit)
        self.assertIn('.crumbs__here', kit)

    def test_group_style_no_longer_defines_them(self):
        style = read('teacher', 'templates', 'teacher', 'groups',
                     '_style.html')
        self.assertNotIn('.crumbs {', style)
        self.assertNotIn('.crumbs a', style)

    def test_only_one_place_defines_crumbs(self):
        """⚠️ Второй набор правил на тот же класс — всегда мина (обзор 13.08)."""
        owners = [path for path, text in markup_files()
                  if re.search(r'^\.crumbs[\s{,:>]', text, re.M)]
        self.assertEqual(owners, ['templates/_kit.html'], owners)

    def test_last_link_is_not_muted(self):
        """Последнее звено — обычный текст, а не приглушённый серый."""
        kit = read('templates', '_kit.html')
        line = [l for l in kit.split('\n') if l.startswith('.crumbs__here')][0]
        self.assertIn('var(--text)', line)
        self.assertNotIn('--text2', line)
        self.assertNotIn('--text3', line)

    def test_arrow_is_drawn_by_css_and_is_accent(self):
        kit = read('templates', '_kit.html')
        block = kit.split('.crumbs > * + *::before')[1].split('}')[0]
        self.assertIn("content: '→'", block)
        self.assertIn('var(--accent)', block)

    def test_arrow_does_not_catch_the_hover_underline(self):
        """⚠️ Подчёркивание наследуется; `inline-block` его останавливает."""
        kit = read('templates', '_kit.html')
        block = kit.split('.crumbs > * + *::before')[1].split('}')[0]
        self.assertIn('inline-block', block)


class NoHandTypedArrowsTests(TestCase):
    """Стрелку рисует CSS — в разметке её быть не должно."""

    def test_no_literal_arrow_inside_crumbs(self):
        bad = []
        for path, text in markup_files():
            for chunk in re.findall(r'<nav class="crumbs".*?</nav>', text,
                                    re.S):
                if '→' in chunk:
                    bad.append(path)
            if 'class="crumbs"' in text and '<div class="crumbs"' in text:
                bad.append('%s (крошка осталась <div>)' % path)
        self.assertEqual(bad, [], bad)


class EveryScreenIsCoveredTests(TestCase):
    """Правила доезжают до КАЖДОГО экрана с крошками, а не до части."""

    def setUp(self):
        from problems.models import Assignment, AssignmentItem, Submission
        from problems.tests.factories import make_problem

        self.tutor = make_user('cr_tutor', role='teacher')
        self.student = make_user('cr_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.work = Assignment.objects.create(name='Домашка',
                                              author=self.tutor,
                                              group=self.group)
        self.work.students.set([self.student])
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted')
        self.client.force_login(self.tutor)

    def _screens(self):
        g, a, s = self.group.pk, self.work.pk, self.student.pk
        return [
            (reverse('teacher:group_detail', args=[g]), 'обзор занятия'),
            (reverse('teacher:group_assignment', args=[g, a]), 'задание'),
            (reverse('teacher:group_submissions', args=[g, a]), 'сводка'),
            (reverse('teacher:student_work_review', args=[g, a, s]),
             'глазами ученика'),
            (reverse('teacher:work_done', args=[g, a, s]), 'итоги'),
            (reverse('teacher:group_review_submission', args=[g, self.sub.pk]),
             'проверка задачи'),
            # ⚠️ ПЕРЕСЧИТАН (ревью 17.08, п. 4.5): прежние конструкторы
            # удалены, набор задач живёт в потоке. Крошка обязана быть на
            # каждом его шаге — это и проверяется.
            (reverse('teacher:work_pick') + '?group=%d' % g, 'что кладём'),
            # ⚠️ Панель «Описать словами» живёт на шаге «Что кладём»
            # (визуальная сессия 17.08, п. 2.1) — и он в списке уже есть.
            (reverse('teacher:work_pick') + '?group=%d&tab=ai' % g,
             'описать словами'),
            (reverse('teacher:work_compose') + '?group=%d' % g, 'состав'),
            (reverse('teacher:work_give') + '?group=%d' % g, 'выдача'),
            (reverse('teacher:work_give') + '?group=%d&kind=exam' % g,
             'контрольная'),
            (reverse('teacher:problem_new'), 'своя задача'),
            (reverse('teacher:problem_list'), 'мои задачи'),
            (reverse('teacher:student_progress', args=[s]), 'карточка ученика'),
            (reverse('teacher:group_create'), 'новая группа'),
        ]

    def test_every_screen_shows_crumbs(self):
        missing = []
        for url, name in self._screens():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, '%s: %s' % (name, url))
            if 'class="crumbs"' not in response.content.decode():
                missing.append(name)
        self.assertEqual(missing, [], 'без крошек: %s' % missing)

    def test_every_screen_loads_the_kit(self):
        """Крошка без правил — голая браузерная ссылка. Ищем сами правила."""
        naked = []
        for url, name in self._screens():
            html = self.client.get(url).content.decode()
            if '.crumbs__here' not in html:
                naked.append(name)
        self.assertEqual(naked, [], 'крошка без стиля: %s' % naked)

    def test_first_link_always_leads_to_students(self):
        first = reverse('teacher:groups')
        for url, name in self._screens():
            html = self.client.get(url).content.decode()
            crumbs = html.split('class="crumbs"')[1].split('</nav>')[0]
            self.assertIn(first, crumbs, name)


class NoHistoryBackTests(TestCase):
    """Ссылок «назад по истории браузера» в кабинете не осталось."""

    def test_no_javascript_history_back(self):
        """⚠️ Ищем САМУ ССЫЛКУ, а не слова: объяснение, почему её убрали,
        стоит в комментарии того же файла и краснело бы вечно."""
        bad = [path for path, text in markup_files()
               if 'href="javascript:' in text or "href='javascript:" in text]
        self.assertEqual(bad, [], bad)


class StudentCardCrumbTests(TestCase):
    """Второе звено карточки ученика — занятие, а не «Назад»."""

    def setUp(self):
        self.tutor = make_user('sc_tutor', role='teacher')
        self.other = make_user('sc_other', role='teacher')
        self.student = make_user('sc_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.beta = StudentGroup.objects.create(name='Бета',
                                                teacher=self.tutor)
        self.alpha = StudentGroup.objects.create(name='Альфа',
                                                 teacher=self.tutor)
        for group in (self.alpha, self.beta):
            group.students.set([self.student])
        self.client.force_login(self.tutor)

    def _crumbs(self, query=''):
        html = self.client.get(
            reverse('teacher:student_progress', args=[self.student.pk])
            + query).content.decode()
        return html.split('class="crumbs"')[1].split('</nav>')[0]

    def test_falls_back_to_the_first_lesson_by_name(self):
        self.assertIn('Альфа', self._crumbs())
        self.assertNotIn('Бета', self._crumbs())

    def test_uses_the_lesson_we_came_from(self):
        self.assertIn('Бета', self._crumbs('?group=%d' % self.beta.pk))

    def test_someone_elses_lesson_is_ignored(self):
        """⚠️ Чужой номер в адресе не подписывает крошку чужим названием."""
        theirs = StudentGroup.objects.create(name='Чужая', teacher=self.other)
        theirs.students.set([self.student])
        crumbs = self._crumbs('?group=%d' % theirs.pk)
        self.assertNotIn('Чужая', crumbs)
        self.assertIn('Альфа', crumbs)

    def test_lesson_without_this_student_is_ignored(self):
        empty = StudentGroup.objects.create(name='Пустая', teacher=self.tutor)
        crumbs = self._crumbs('?group=%d' % empty.pk)
        self.assertNotIn('Пустая', crumbs)

    def test_student_name_is_the_last_link(self):
        self.assertIn('Мария Ким', self._crumbs())

    def test_no_lesson_at_all_still_renders(self):
        for group in (self.alpha, self.beta):
            group.students.clear()
        self.tutor.is_staff = True
        self.tutor.save(update_fields=['is_staff'])
        response = self.client.get(
            reverse('teacher:student_progress', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Мария Ким', response.content.decode())


class SoloLessonNameTests(TestCase):
    """У занятия один на один в крошке стоит ИМЯ УЧЕНИКА."""

    def test_crumb_shows_the_student_not_the_lesson_name(self):
        tutor = make_user('sl_tutor', role='teacher')
        student = make_user('sl_student', role='student',
                            first_name='Тимур', last_name='Ахметов')
        lesson = StudentGroup.objects.create(name='Занятие 17', teacher=tutor,
                                             kind='individual')
        lesson.students.set([student])
        # ⚠️ ПЕРЕСЧИТАНО 17.08: у ученика, чьё ЕДИНСТВЕННОЕ занятие
        # индивидуальное, карточка уводит на экран занятия (решение
        # владельца). Крошка живёт там, где карточка осталась экраном, —
        # у ученика, который ходит ещё и в группу. Второе занятие названо
        # так, чтобы выбор `lesson_for_student` («первое по алфавиту среди
        # видимых названий») оставался устойчивым: «Тимур» < «Ярославль».
        other = StudentGroup.objects.create(name='Ярославль', teacher=tutor)
        other.students.set([student])
        self.client.force_login(tutor)
        html = self.client.get(
            reverse('teacher:student_progress', args=[student.pk])
        ).content.decode()
        crumbs = html.split('class="crumbs"')[1].split('</nav>')[0]
        self.assertIn('Тимур Ахметов', crumbs)
        self.assertNotIn('Занятие 17', crumbs)
