"""
Обзор кабинета 13.08.2026, фаза 1 — навигация и сквозные надписи.

Пункты владельца 1, 2, 3, 5, 6, 7:
  • крошка начиналась со слова «Группы», а пункт меню называется «Ученики»;
  • на экранах создания вместо названия занятия стояло слово «занятие»;
  • «Проверять решения (1)» и «Проверить 2 задачи» — две разные единицы
    в двух кликах друг от друга;
  • пункт меню «Подобрать похожие» вёл на «Умный поиск задач»;
  • в пустом состоянии умного поиска стояла эмодзи-лампочка.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def crumbs(html):
    """Текст первой хлебной крошки страницы: звенья через стрелку.

    ⚠️ ПЕРЕСЧИТАНО (ревью 15.08, фаза 2). Крошка стала `<nav>`, а стрелку
    рисует CSS (`::before` у каждого звена, кроме первого) — в разметке её
    больше нет. Собираем ТУ ЖЕ строку, что видит глаз, из текстов звеньев;
    смысл всех проверок ниже не изменился.
    """
    found = re.search(r'<nav class="crumbs"[^>]*>(.*?)</nav>', html, re.S)
    if not found:
        return ''
    parts = re.findall(r'<(?:a|span)\b[^>]*>(.*?)</(?:a|span)>',
                       found.group(1), re.S)
    clean = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', part)).strip()
             for part in parts]
    return ' → '.join(part for part in clean if part)


class CrumbWordTests(TestCase):
    """1.1 — первое слово крошки везде «Ученики», как в меню."""

    def setUp(self):
        from datetime import timedelta

        from decimal import Decimal

        from django.utils import timezone

        from problems.models import Assignment, AssignmentItem, Submission

        self.tutor = make_user('cw_tutor', role='teacher')
        self.student = make_user('cw_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Группа А',
                                                 teacher=self.tutor)
        self.group.students.set([self.student])
        now = timezone.now()
        self.work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=1))
        self.work.students.set([self.student])
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('2'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted', submitted_at=now)
        self.client.force_login(self.tutor)

    def test_assignment_screen_starts_with_uchenikí(self):
        html = self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])).content.decode()
        self.assertTrue(crumbs(html).startswith('Ученики'), crumbs(html))

    def test_review_screen_starts_with_ucheniki(self):
        html = self.client.get(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.sub.pk])).content.decode()
        self.assertTrue(crumbs(html).startswith('Ученики'), crumbs(html))

    def test_work_done_screen_starts_with_ucheniki(self):
        html = self.client.get(
            reverse('teacher:work_done',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()
        self.assertTrue(crumbs(html).startswith('Ученики'), crumbs(html))

    def test_submissions_by_problems_starts_with_ucheniki(self):
        html = self.client.get(
            reverse('teacher:group_submissions',
                    args=[self.group.pk, self.work.pk])
            + '?view=problems').content.decode()
        self.assertTrue(crumbs(html).startswith('Ученики'), crumbs(html))

    def test_no_template_says_gruppy_in_a_crumb(self):
        """Слово «Группы» не осталось ни в одной живой крошке кабинета."""
        import glob

        bad = []
        for path in glob.glob(os.path.join(ROOT, 'teacher', 'templates',
                                           '**', '*.html'), recursive=True):
            text = open(path, encoding='utf-8').read()
            # Комментарии не в счёт: там объясняется, почему было иначе.
            clean = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}',
                           '', text, flags=re.S)
            for line in clean.split('\n'):
                if "teacher:groups' %}" in line and 'Группы' in line:
                    bad.append(os.path.basename(path))
        self.assertEqual(bad, [], 'крошка «Группы» осталась в %s' % bad)


class CrumbGroupNameTests(TestCase):
    """1.2 — вместо слова «занятие» настоящее название."""

    def setUp(self):
        self.tutor = make_user('cg_tutor', role='teacher')
        self.other = make_user('cg_other', role='teacher')
        self.student = make_user('cg_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.group = StudentGroup.objects.create(name='Экономика, вторник',
                                                 teacher=self.tutor)
        self.solo = StudentGroup.objects.create(
            name='Мария Ким', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.solo.students.set([self.student])
        self.client.force_login(self.tutor)

    def test_group_name_instead_of_the_word(self):
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.group.pk).content.decode()
        self.assertIn('Экономика, вторник', crumbs(html))
        self.assertNotIn('занятие', crumbs(html))

    def test_individual_shows_student_name(self):
        html = self.client.get(
            reverse('teacher:assignment_generate')
            + '?group=%d' % self.solo.pk).content.decode()
        self.assertIn('Мария Ким', crumbs(html))

    def test_individual_name_wins_over_renamed_lesson(self):
        """Занятие переименовали — в крошке всё равно имя ученика."""
        self.solo.name = 'Вторник, 18:00'
        self.solo.save()
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.solo.pk).content.decode()
        self.assertIn('Мария Ким', crumbs(html))

    def test_stranger_group_gives_no_crumb(self):
        """Чужое занятие названия не подтверждает — крошки просто нет."""
        alien = StudentGroup.objects.create(name='Секретная', teacher=self.other)
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % alien.pk).content.decode()
        self.assertNotIn('Секретная', html)
        self.assertEqual(crumbs(html), 'Ученики → новая работа')

    def test_garbage_group_param_still_opens(self):
        """`?group=abc` по-прежнему не роняет экран (находка сессии 10)."""
        response = self.client.get(
            reverse('teacher:assignment_create') + '?group=abc')
        self.assertEqual(response.status_code, 200)


class CheckButtonTests(TestCase):
    """1.3 — единица кнопки на экране задания: сданная работа."""

    def setUp(self):
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from problems.models import Assignment, AssignmentItem, Submission

        self.tutor = make_user('cb_tutor', role='teacher')
        self.students = [make_user('cb_s%d' % i, role='student')
                         for i in range(3)]
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set(self.students)
        now = timezone.now()
        self.work = Assignment.objects.create(
            name='ДЗ', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=1))
        self.work.students.set(self.students)
        # Две задачи в работе: если бы считались задачи, число было бы вдвое
        # больше числа сдавших.
        self.items = [AssignmentItem.objects.create(
            assignment=self.work, order=i,
            catalog_problem=make_problem('Условие %d' % i),
            points=Decimal('2')) for i in range(2)]
        self.now = now

    def _submit(self, student):
        from problems.models import Submission
        for item in self.items:
            Submission.objects.create(student=student, assignment=self.work,
                                      problem_item=item, status='submitted',
                                      submitted_at=self.now)

    def _button(self):
        self.client.force_login(self.tutor)
        html = self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])).content.decode()
        found = re.search(r'class="btn-primary">(.*?)</a>', html, re.S)
        return re.sub(r'\s+', ' ', found.group(1)).strip() if found else ''

    def test_one_work_is_declined(self):
        self._submit(self.students[0])
        self.assertEqual(self._button(), 'Проверить 1 работу')

    def test_two_works_are_declined(self):
        self._submit(self.students[0])
        self._submit(self.students[1])
        self.assertEqual(self._button(), 'Проверить 2 работы')

    def test_five_works_are_declined(self):
        """Пять — форма «работ». Учеников трое, поэтому проверяем счётчик."""
        from problems.templatetags.ru import pick
        self.assertEqual(pick(5, 'работу', 'работы', 'работ'), 'работ')

    def test_nothing_waiting_keeps_the_old_wording(self):
        """Нечего проверять — нет и числа: «Проверить 0 работ» было бы ложью."""
        self.assertEqual(self._button(), 'Проверять решения')


class MenuAndIconTests(TestCase):
    """1.4 и 1.5 — пункт меню и контурная иконка вместо эмодзи."""

    def test_menu_item_matches_the_screen_title(self):
        nav = read('templates', '_nav.html')
        self.assertNotIn('Подобрать похожие', nav)
        self.assertEqual(nav.count('>Умный поиск</a>'), 4)

    def test_screen_title_untouched(self):
        """Заголовок экрана точнее описывает суть — его не трогали."""
        page = read('catalog', 'templates', 'catalog', 'smart_search.html')
        self.assertIn('Умный поиск задач', page)

    def test_empty_state_has_no_emoji(self):
        page = read('catalog', 'templates', 'catalog', 'smart_search.html')
        for emoji in ('💡', '🔍'):
            self.assertNotIn(emoji, page)
        self.assertIn("_icon.html' with name='bulb'", page)
        self.assertIn("_icon.html' with name='search'", page)

    def test_new_icons_match_in_both_sources(self):
        """Разметка и скрипты берут ОДНУ строку — иначе наборы разойдутся."""
        markup = read('templates', '_icon.html')
        script = read('templates', '_icons.html')
        for name in ('search', 'bulb', 'clip', 'chart', 'book'):
            found = re.search(
                r"\{%% if name == '%s' %%\}(.*?)\{%% endif %%\}" % name,
                markup, re.S)
            self.assertIsNotNone(found, 'нет иконки %s в разметке' % name)
            self.assertIn(found.group(1).strip(), script,
                          'иконка %s в разметке и в скриптах разная' % name)

    def test_icons_follow_the_house_grid(self):
        markup = read('templates', '_icon.html')
        for line in markup.split('\n'):
            if '<svg' not in line:
                continue
            self.assertIn('viewBox="0 0 24 24"', line)
            self.assertIn('stroke-width="1.75"', line)
            self.assertIn('fill="none"', line)
            self.assertIn('stroke="currentColor"', line)

    def test_no_pictographic_emoji_left_in_the_cabinet(self):
        """Эмодзи запрещены везде: ни одной пиктограммы в живой разметке.

        ⚠️ Стрелки, галочки и звёзды сложности — НЕ эмодзи: это типографские
        знаки, их рисует шрифт, и они подчиняются палитре. Запрещены именно
        цветные пиктограммы, которые рисует операционная система.
        """
        import glob

        picto = re.compile('[\U0001F000-\U0001FAFF]')
        bad = []
        roots = [('teacher', 'templates'), ('student', 'templates'),
                 ('problems', 'templates', 'platform'), ('templates',)]
        for root in roots:
            pattern = os.path.join(ROOT, *(root + ('**', '*.html')))
            for path in glob.glob(pattern, recursive=True):
                if 'achievement' in os.path.basename(path):
                    continue  # блок достижений идёт отдельной переработкой
                text = open(path, encoding='utf-8').read()
                clean = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}',
                               '', text, flags=re.S)
                clean = re.sub(r'\{#.*?#\}', '', clean, flags=re.S)
                clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.S)
                clean = re.sub(r'//[^\n]*', '', clean)
                if picto.search(clean):
                    bad.append('%s: %s' % (os.path.basename(path),
                                           picto.findall(clean)))
        self.assertEqual(bad, [], 'остались эмодзи: %s' % bad)
