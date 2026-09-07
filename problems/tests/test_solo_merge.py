"""
Ревью 17.08.2026, завершающая сессия, фаза 1 — у индивидуальных занятие и
карточка ученика это ОДИН экран.

Решение владельца: «У индивидуальных занятие и карточка ученика сливаются в
один экран». Здесь проверяется ровно то, чем это решение опасно:

  • редирект обязан срабатывать ТОЛЬКО при одном индивидуальном занятии —
    иначе ученик, который ходит и в группу, и на индивидуальное, теряет
    доступ к своей карточке;
  • заметки сохраняются с ОБОИХ экранов и возвращают туда, откуда отправлены
    (обработчик один — карточка);
  • у групп не меняется ничего.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.models_platform import TutorNote
from problems.tests.factories import make_user
from problems.tests.tree import project_files

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class SoloRedirectTests(TestCase):
    """1.3 — когда карточка уводит на занятие, а когда работает как раньше."""

    def setUp(self):
        self.tutor = make_user('sm_tutor', role='teacher')
        self.client.force_login(self.tutor)

    def _student(self, name):
        return make_user('sm_' + name, role='student', first_name='Имя',
                         last_name=name.title())

    def _lesson(self, student, kind=StudentGroup.Kind.INDIVIDUAL, name='Урок'):
        lesson = StudentGroup.objects.create(name=name, teacher=self.tutor,
                                             kind=kind)
        lesson.students.set([student])
        return lesson

    def test_solo_only_student_is_redirected(self):
        student = self._student('solo')
        lesson = self._lesson(student)
        response = self.client.get(
            reverse('teacher:student_progress', args=[student.pk]))
        self.assertRedirects(
            response, reverse('teacher:group_detail', args=[lesson.pk]))

    def test_group_student_keeps_the_card(self):
        student = self._student('grp')
        self._lesson(student, kind=StudentGroup.Kind.GROUP, name='Группа')
        response = self.client.get(
            reverse('teacher:student_progress', args=[student.pk]))
        self.assertEqual(response.status_code, 200)

    def test_both_lessons_keep_the_card(self):
        """Ученик ходит и в группу, и на индивидуальное — обе двери целы."""
        student = self._student('both')
        solo = self._lesson(student)
        self._lesson(student, kind=StudentGroup.Kind.GROUP, name='Группа')
        response = self.client.get(
            reverse('teacher:student_progress', args=[student.pk]))
        self.assertEqual(response.status_code, 200)
        # И экран занятия при этом остаётся экраном занятия.
        self.assertEqual(
            self.client.get(
                reverse('teacher:group_detail', args=[solo.pk])).status_code,
            200)

    def test_two_solo_lessons_keep_the_card(self):
        """Два индивидуальных занятия — какое из них «то самое», неизвестно."""
        student = self._student('twosolo')
        self._lesson(student, name='Понедельник')
        self._lesson(student, name='Четверг')
        response = self.client.get(
            reverse('teacher:student_progress', args=[student.pk]))
        self.assertEqual(response.status_code, 200)

    def test_second_student_in_a_solo_lesson_keeps_the_card(self):
        """Подсадили второго — занятие перестало быть про одного человека."""
        student = self._student('crowd')
        lesson = self._lesson(student)
        lesson.students.add(self._student('crowd2'))
        response = self.client.get(
            reverse('teacher:student_progress', args=[student.pk]))
        self.assertEqual(response.status_code, 200)

    def test_group_screen_still_links_to_cards(self):
        """1.4 — у ГРУПП ничего не изменилось: в таблице кнопка на карточку."""
        first, second = self._student('g1'), self._student('g2')
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.set([first, second])
        html = self.client.get(
            reverse('teacher:group_detail', args=[group.pk])).content.decode()
        self.assertIn(
            reverse('teacher:student_progress', args=[first.pk]), html)


class NoteFromBothScreensTests(TestCase):
    """1.1 — заметки сохраняются с обоих экранов и возвращают к отправителю."""

    def setUp(self):
        self.tutor = make_user('nb_tutor', role='teacher')
        self.solo = make_user('nb_solo', role='student',
                              first_name='Мария', last_name='Ким')
        self.lesson = StudentGroup.objects.create(
            name='Мария Ким', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.solo])
        # Ученик, у которого карточка осталась отдельным экраном.
        self.grouped = make_user('nb_grouped', role='student',
                                 first_name='Сергей', last_name='Дмитриев')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.grouped, make_user('nb_x',
                                                         role='student')])
        self.client.force_login(self.tutor)

    def test_notes_block_is_on_the_solo_lesson(self):
        html = self.client.get(
            reverse('teacher:group_detail',
                    args=[self.lesson.pk])).content.decode()
        self.assertIn('Заметки об ученике', html)
        self.assertIn('Видно только вам', html)
        self.assertIn('Полезная информация о Марии Ким', html)

    def test_notes_block_is_last_on_the_overview(self):
        """«Последним блоком» — после истории работ, а не над ней."""
        html = self.client.get(
            reverse('teacher:group_detail',
                    args=[self.lesson.pk])).content.decode()
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)
        self.assertLess(html.index('История работ'),
                        html.index('Заметки об ученике'))

    def test_group_overview_has_no_notes(self):
        """У группы заметки об ученике не про кого писать."""
        html = self.client.get(
            reverse('teacher:group_detail',
                    args=[self.group.pk])).content.decode()
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)
        self.assertNotIn('Заметки об ученике', html)

    def test_saving_from_the_lesson_returns_to_the_lesson(self):
        back = reverse('teacher:group_detail', args=[self.lesson.pk])
        response = self.client.post(
            reverse('teacher:student_progress', args=[self.solo.pk]),
            {'note': 'любит графики', 'back': back})
        self.assertRedirects(response, back)
        self.assertEqual(
            TutorNote.objects.get(tutor=self.tutor, student=self.solo).text,
            'любит графики')

    def test_saving_from_the_card_returns_to_the_card(self):
        card = reverse('teacher:student_progress', args=[self.grouped.pk])
        response = self.client.post(card, {'note': 'нужен разбор', 'back': card})
        self.assertRedirects(response, card)
        self.assertEqual(
            TutorNote.objects.get(tutor=self.tutor, student=self.grouped).text,
            'нужен разбор')

    def test_foreign_return_address_is_refused(self):
        """Чужой адрес в поле возврата — это открытый перенаправитель."""
        card = reverse('teacher:student_progress', args=[self.grouped.pk])
        response = self.client.post(
            card, {'note': 'x', 'back': 'https://example.com/steal'})
        self.assertRedirects(response, card)

    def test_ajax_save_answers_json(self):
        response = self.client.post(
            reverse('teacher:student_progress', args=[self.solo.pk]),
            {'note': 'через сеть',
             'back': reverse('teacher:group_detail', args=[self.lesson.pk])},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})


class OneMarkupTests(TestCase):
    """1.1 — разметка блока ОДНА, копии нет."""

    def test_both_screens_include_the_same_partial(self):
        card = read('teacher', 'templates', 'teacher', 'student_progress.html')
        overview = read('teacher', 'templates', 'teacher', 'groups',
                        '_overview.html')
        for page in (card, overview):
            self.assertIn('teacher/_tutor_note.html', page)

    def test_no_second_note_form_in_templates(self):
        """Поле заметки объявлено ровно в одном файле проекта.

        ⚠️ `materials/` исключена как исходники для импорта: их HTML-файлы
        не обязаны подчиняться правилу «одна разметка».

        ⚠️ ПОСТОРОННИЕ РАБОЧИЕ КОПИИ ОТСЕКАЕТ ОБЩИЙ ОБХОДЧИК, И ЭТО УЖЕ
        ВТОРОЙ ЗАХОД. 22.08 проверка упала из-за клона репозитория в
        `materials/`, и тогда хватило исключить `materials`. 02.09 упала
        снова — на этот раз копия лежала в `.claude/worktrees/`, куда
        прежний список не смотрел. Перечислять места, где может оказаться
        чужая копия, бесполезно: их находят по признаку «внутри есть свой
        `.git`». Подробности — `problems/tests/tree.py`.
        """
        found = [
            os.path.relpath(path, ROOT)
            for path in project_files(ROOT, '.html', ('materials',))
            if 'name="note"' in read(path)
        ]
        self.assertEqual(found, [os.path.join('teacher', 'templates',
                                              'teacher', '_tutor_note.html')])

    def test_partial_loads_its_own_filters(self):
        """⚠️ `load` не наследуется во включаемый шаблон — падало бы фильтром."""
        partial = read('teacher', 'templates', 'teacher', '_tutor_note.html')
        self.assertIn('{% load ru %}', partial)

    def test_return_field_is_not_called_action(self):
        """Имя `action` затеняет `form.action` — поле возврата зовётся иначе."""
        partial = read('teacher', 'templates', 'teacher', '_tutor_note.html')
        self.assertNotIn('name="action"', partial)
        self.assertIn('name="back"', partial)
