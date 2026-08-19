# -*- coding: utf-8 -*-
"""Фаза 2 сессии 3А: чужой объект не открывается подстановкой чужого id.

⚠️ ЧТО ЗДЕСЬ ДОКАЗЫВАЕТСЯ И ЧЕГО НЕ ДОКАЗЫВАЮТ ОСТАЛЬНЫЕ 2 416 ТЕСТОВ.
Обычный тест проверяет, что всё работает у ПРАВИЛЬНОГО пользователя. Здесь
наоборот: что всё ломается у неправильного. Зелёный прогон без таких тестов
не говорит ничего о границах доступа.

Субъекты заведены один раз на весь модуль и перебираются по каждому объекту:

    гость · владелец (контроль) · другой той же роли · ученик соседней
    группы того же репетитора · репетитор чужой группы · не та роль ·
    бывший участник, удалённый из группы

Проверяется НЕ ТОЛЬКО код ответа: в теле не должно быть названия чужого
объекта, а в базе после запроса ничего не должно измениться.

⚠️ НИ ОДНА ПРОВЕРКА НЕ ОПИРАЕТСЯ НА КОНКРЕТНЫЕ id — счётчики в PostgreSQL не
откатываются транзакцией.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, Problem, StudentGroup, Submission,
)
from problems.models_platform import (
    CustomProblem, SavedFolder, SavedGraph, SavedProblem,
)

User = get_user_model()

PASSWORD = 'proverka12345'

ALIEN_MARK = 'ЧУЖОЙОБЪЕКТМАРКЕР'


def json_text(response):
    """Тело JSON-ответа с РАСКРЫТОЙ кириллицей.

    ⚠️ `JsonResponse` по умолчанию экранирует не-ASCII в `\\uXXXX`, поэтому
    поиск русской строки в сыром теле её не находит. Проверка «маркера в
    ответе нет», написанная по сырому телу, была бы зелёной на утёкшем
    JSON — то есть беззубой ровно там, где утечку заметить труднее всего.
    """
    import json

    raw = response.content.decode('utf-8', errors='replace')
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False)
    except ValueError:
        return raw


def make_client(user=None):
    client = Client()
    if user is not None:
        assert client.login(username=user.username, password=PASSWORD)
    return client


class AccessFixture(TestCase):
    """Две независимые «вселенные» и набор посторонних."""

    @classmethod
    def setUpTestData(cls):
        # --- вселенная A: наш репетитор, его группа, его ученик ----------
        cls.tutor = User.objects.create_user('acc_tutor', password=PASSWORD,
                                             role='teacher')
        cls.student = User.objects.create_user('acc_student',
                                               password=PASSWORD,
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Группа А',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)

        # Ученик СОСЕДНЕЙ группы того же репетитора: роль та же, репетитор
        # тот же, но работа чужая.
        cls.neighbour = User.objects.create_user('acc_neighbour',
                                                 password=PASSWORD,
                                                 role='student')
        cls.group2 = StudentGroup.objects.create(name='Группа Б',
                                                 teacher=cls.tutor)
        cls.group2.students.add(cls.neighbour)

        # Бывший участник: был в группе, удалён из неё.
        cls.former = User.objects.create_user('acc_former', password=PASSWORD,
                                              role='student')
        cls.group.students.add(cls.former)
        cls.group.students.remove(cls.former)

        # --- вселенная B: чужой репетитор со своим учеником --------------
        cls.other_tutor = User.objects.create_user('acc_other_tutor',
                                                   password=PASSWORD,
                                                   role='teacher')
        cls.other_student = User.objects.create_user('acc_other_student',
                                                     password=PASSWORD,
                                                     role='student')
        cls.other_group = StudentGroup.objects.create(name='Группа чужая',
                                                      teacher=cls.other_tutor)
        cls.other_group.students.add(cls.other_student)

        cls.problem = Problem.objects.create(
            statement='Условие для проверки доступа.',
            status=Problem.Status.PUBLISHED)

        # Работа вселенной A.
        cls.work = Assignment.objects.create(
            name='Работа %s' % ALIEN_MARK, author=cls.tutor, group=cls.group)
        cls.work.students.add(cls.student)
        cls.work.problems.add(cls.problem)
        cls.item = AssignmentItem.objects.create(
            assignment=cls.work, catalog_problem=cls.problem, order=0)

    # -- помощники --------------------------------------------------------
    def assert_refused(self, response, where, marker=ALIEN_MARK):
        """Отказ — это 403, 404 или уход на вход. И без утечки названия."""
        self.assertIn(
            response.status_code, (302, 403, 404),
            '%s: ожидался отказ, получено %s' % (where, response.status_code))
        if response.status_code == 302:
            self.assertIn('/login/', response['Location'],
                          '%s: редирект не на вход' % where)
        body = response.content.decode('utf-8', errors='replace')
        self.assertNotIn(marker, body,
                         '%s: в теле отказа найдено название чужого объекта'
                         % where)


class AssignmentAccessTests(AccessFixture):
    """Работу видит только тот, кому она выдана, и её репетитор."""

    def _urls(self):
        return [
            reverse('student:assignment_detail', args=[self.work.pk]),
            reverse('student:work_review', args=[self.work.pk]),
        ]

    def test_outsiders_are_refused(self):
        subjects = [
            ('гость', None),
            ('ученик соседней группы', self.neighbour),
            ('ученик чужого репетитора', self.other_student),
            ('бывший участник', self.former),
        ]
        for label, user in subjects:
            client = make_client(user)
            for url in self._urls():
                with self.subTest(subject=label, url=url):
                    self.assert_refused(client.get(url), '%s -> %s'
                                        % (label, url))

    def test_owner_still_gets_in(self):
        """Контроль: своему ученику работа открывается."""
        client = make_client(self.student)
        response = client.get(
            reverse('student:assignment_detail', args=[self.work.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ALIEN_MARK)

    def test_alien_tutor_cannot_open_group_screens(self):
        """Чужой репетитор не открывает работу через групповые адреса."""
        client = make_client(self.other_tutor)
        urls = [
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk]),
            reverse('teacher:group_submissions',
                    args=[self.group.pk, self.work.pk]),
            reverse('teacher:assignment_print',
                    args=[self.group.pk, self.work.pk]),
            reverse('teacher:assignment_export',
                    args=[self.group.pk, self.work.pk]),
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk, self.student.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assert_refused(client.get(url), url)

    def test_alien_tutor_cannot_use_the_groupless_route(self):
        """Безгрупповой адрес разбора — та же граница, что групповой.

        Этот обработчик один на два адреса, и во втором нет `group_id`:
        права там проверяются по автору работы, а не по группе.
        """
        client = make_client(self.other_tutor)
        url = reverse('teacher:student_work_review_plain',
                      args=[self.work.pk, self.student.pk])
        self.assert_refused(client.get(url), url)


class SubmissionAccessTests(AccessFixture):
    """Чужую попытку нельзя ни прочитать, ни изменить."""

    def setUp(self):
        self.submission = Submission.objects.create(
            student=self.student, assignment=self.work, problem=self.problem,
            problem_item=self.item, submitted_answer='мой ответ',
            status='submitted')

    def test_other_student_cannot_read(self):
        client = make_client(self.neighbour)
        url = reverse('student:submission_detail', args=[self.submission.pk])
        response = client.get(url, follow=False)
        self.assertIn(response.status_code, (302, 403, 404))
        if response.status_code == 302:
            self.assertNotIn('/student/work/%d/' % self.work.pk,
                             response['Location'],
                             'редирект увёл соседнего ученика в чужой разбор')

    def test_alien_tutor_cannot_grade(self):
        """Чужой репетитор не выставляет оценку по номеру попытки."""
        client = make_client(self.other_tutor)
        response = client.post(
            reverse('teacher:api_grade_submission'),
            data='{"submission_id": %d, "score": 5}' % self.submission.pk,
            content_type='application/json')
        self.assertIn(response.status_code, (400, 403, 404))

        self.submission.refresh_from_db()
        self.assertFalse(
            hasattr(self.submission, 'feedback')
            and self.submission.feedback.score == 5,
            'чужой репетитор выставил оценку')

    def test_alien_tutor_cannot_approve_answers(self):
        """Утверждение эталона — тоже право репетитора ЭТОЙ работы."""
        client = make_client(self.other_tutor)
        response = client.post(
            reverse('teacher:api_item_answers'),
            data='{"item_id": %d, "answers": {"": "подделка"}}' % self.item.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 403)

        self.item.refresh_from_db()
        self.assertIsNone(self.item.answer_override,
                          'чужой репетитор утвердил эталон ответа')

    def test_alien_tutor_cannot_change_points(self):
        client = make_client(self.other_tutor)
        before = self.item.points
        response = client.post(
            reverse('teacher:api_item_points'),
            data='{"item_id": %d, "points": 99}' % self.item.pk,
            content_type='application/json')
        self.assertIn(response.status_code, (400, 403, 404))
        self.item.refresh_from_db()
        self.assertEqual(self.item.points, before,
                         'чужой репетитор изменил максимальный балл')


class GroupAccessTests(AccessFixture):
    """Чужая группа не открывается и не пополняется."""

    def test_alien_tutor_cannot_open_group(self):
        client = make_client(self.other_tutor)
        for url in (reverse('teacher:group_detail', args=[self.group.pk]),
                    reverse('teacher:group_stats', args=[self.group.pk]),
                    reverse('teacher:exam_create', args=[self.group.pk])):
            with self.subTest(url=url):
                self.assert_refused(client.get(url, follow=False),
                                    url, marker='Группа А')

    def test_alien_tutor_cannot_see_student_card(self):
        """Карточка чужого ученика — 403, а не «пустой экран»."""
        client = make_client(self.other_tutor)
        url = reverse('teacher:student_progress', args=[self.student.pk])
        self.assertEqual(client.get(url).status_code, 403)


class CustomProblemAccessTests(AccessFixture):
    """Своя задача репетитора видна только автору."""

    def setUp(self):
        self.own = CustomProblem.objects.create(
            owner=self.tutor, statement='Своя задача %s' % ALIEN_MARK,
            kind=CustomProblem.Kind.OPEN)

    def test_alien_tutor_cannot_open_edit_form(self):
        client = make_client(self.other_tutor)
        self.assert_refused(
            client.get(reverse('teacher:problem_edit', args=[self.own.pk])),
            'форма правки чужой задачи')

    def test_alien_tutor_cannot_read_via_preview_api(self):
        """Окно предпросмотра не отдаёт чужую задачу по ключу «c<id>»."""
        client = make_client(self.other_tutor)
        response = client.get(
            reverse('teacher:api_problem_detail', args=['c%d' % self.own.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(ALIEN_MARK, json_text(response))

    def test_owner_reads_own(self):
        """Контроль: автору своя задача отдаётся."""
        client = make_client(self.tutor)
        response = client.get(
            reverse('teacher:api_problem_detail', args=['c%d' % self.own.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(ALIEN_MARK, json_text(response))


class SavedItemsAccessTests(AccessFixture):
    """«Сохранённое» — строго своё."""

    def setUp(self):
        self.folder = SavedFolder.objects.create(
            owner=self.tutor, kind=SavedFolder.Kind.PROBLEMS,
            name='Папка %s' % ALIEN_MARK)
        self.saved = SavedProblem.objects.create(
            owner=self.tutor, catalog_problem=self.problem,
            folder=self.folder)
        self.graph = SavedGraph.objects.create(
            owner=self.tutor, name='График %s' % ALIEN_MARK, scene={})

    def test_stranger_cannot_rename_folder(self):
        client = make_client(self.other_tutor)
        response = client.post(
            reverse('api_folder_rename'),
            data='{"folder_id": %d, "name": "захвачено"}' % self.folder.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.folder.refresh_from_db()
        self.assertIn(ALIEN_MARK, self.folder.name)

    def test_stranger_cannot_delete_saved(self):
        client = make_client(self.other_tutor)
        response = client.post(
            reverse('api_saved_delete'),
            data='{"id": %d}' % self.saved.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.saved.refresh_from_db()
        self.assertFalse(self.saved.is_deleted)

    def test_stranger_cannot_move_graph(self):
        client = make_client(self.other_tutor)
        response = client.post(
            reverse('api_saved_move'),
            data='{"kind": "graph", "id": %d}' % self.graph.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_saving_an_unpublished_problem_is_refused(self):
        """Черновик нельзя положить себе в «Сохранённое».

        Раньше эндпоинт брал задачу без фильтра по статусу, и любой вошедший
        подставлял номер черновика: задача ложилась в «Сохранённое» и
        показывалась на `/profile/?tab=saved` вместе с условием — в обход
        шлюза качества.
        """
        draft = Problem.objects.create(
            statement='Черновик %s' % ALIEN_MARK,
            status=Problem.Status.DRAFT)
        client = make_client(self.student)
        response = client.post(
            reverse('api_save_problem'),
            data='{"catalog_problem_id": %d}' % draft.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            SavedProblem.objects.filter(owner=self.student,
                                        catalog_problem=draft).exists(),
            'черновик попал в «Сохранённое»')

    def test_flagged_problem_is_refused_too(self):
        """Забракованная шлюзом — тоже."""
        flagged = Problem.objects.create(
            statement='Забракованная %s' % ALIEN_MARK,
            status=Problem.Status.PUBLISHED, needs_quality_review=True)
        client = make_client(self.student)
        response = client.post(
            reverse('api_save_problem'),
            data='{"catalog_problem_id": %d}' % flagged.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_published_problem_still_saves(self):
        """Контроль: обычную задачу сохранить по-прежнему можно."""
        client = make_client(self.student)
        response = client.post(
            reverse('api_save_problem'),
            data='{"catalog_problem_id": %d}' % self.problem.pk,
            content_type='application/json')
        self.assertEqual(response.status_code, 200)


class UnpublishedProblemTests(AccessFixture):
    """Черновик, скрытая и забракованная не выходят наружу."""

    def test_catalog_hides_them(self):
        cases = {
            'черновик': Problem.objects.create(
                statement='Ч %s' % ALIEN_MARK, status=Problem.Status.DRAFT),
            'скрытая': Problem.objects.create(
                statement='С %s' % ALIEN_MARK, status=Problem.Status.HIDDEN),
            'забракованная': Problem.objects.create(
                statement='З %s' % ALIEN_MARK,
                status=Problem.Status.PUBLISHED, needs_quality_review=True),
        }
        for label, problem in cases.items():
            for url in (reverse('catalog:problem_detail', args=[problem.pk]),
                        reverse('catalog:api_problem', args=[problem.pk])):
                with self.subTest(kind=label, url=url):
                    self.assertEqual(Client().get(url).status_code, 404)

    def test_tutor_preview_api_hides_them_too(self):
        """Окно предпросмотра кабинета — та же граница, что каталог.

        Раньше здесь фильтра не было вовсе: `.get(pk=...)` отдавал и
        черновик, и забракованную.
        """
        draft = Problem.objects.create(statement='Ч2 %s' % ALIEN_MARK,
                                       status=Problem.Status.DRAFT)
        client = make_client(self.tutor)
        response = client.get(
            reverse('teacher:api_problem_detail', args=[str(draft.pk)]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(ALIEN_MARK,
                         response.content.decode('utf-8', errors='replace'))


class MissingObjectTests(AccessFixture):
    """Несуществующий номер не роняет сервер и ничего не подтверждает.

    Номер берём как «заведомо больше всех» от максимума в таблице, а не
    константой: счётчики в PostgreSQL живут вне транзакции, и жёсткое число
    однажды совпало бы с реальной записью.
    """

    def test_absent_ids_give_clean_refusal(self):
        gone = Assignment.objects.order_by('-pk').first().pk + 1000
        client = make_client(self.student)
        for url in (reverse('student:assignment_detail', args=[gone]),
                    reverse('student:work_review', args=[gone])):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertNotEqual(response.status_code, 500)
                self.assertIn(response.status_code, (302, 403, 404))
