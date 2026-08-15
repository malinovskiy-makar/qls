"""
Путь создания работы: карточки запросов → конструктор подборки → задание.

Проверяем ровно то, что владелец назвал в ревью (пункты 12.1–12.3):
размер выдачи кандидатов, дедупликацию НА ВСЮ ПОДБОРКУ, бесплатность
кнопки «Показать ещё», перенос корзины и экран после создания работы.
"""
import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from problems import hw_generator
from problems.models import (
    AiUsageLog, Assignment, AssignmentItem, Problem, StudentGroup, Topic, User,
)
from teacher.picker import cart_rows, parse_points


def make_user(username, role='teacher'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = role
    user.save()
    return user


def make_problem(text, difficulty=3, ptype=''):
    return Problem.objects.create(
        title=text[:60], statement=text, status=Problem.Status.PUBLISHED,
        difficulty=difficulty, problem_type=ptype)


class CandidatesSizeTests(TestCase):
    """Кандидатов вдвое больше, чем просили, но не меньше пяти."""

    def test_wanted_never_below_five(self):
        self.assertEqual(hw_generator.candidates_wanted(1), 5)
        self.assertEqual(hw_generator.candidates_wanted(2), 5)

    def test_wanted_is_double_when_asked_for_many(self):
        self.assertEqual(hw_generator.candidates_wanted(3), 6)
        self.assertEqual(hw_generator.candidates_wanted(10), 20)

    def test_zero_is_treated_as_one(self):
        """Ноль в поле — не повод показать пустоту."""
        self.assertEqual(hw_generator.candidates_wanted(0), 5)


class PreviewDedupTests(TestCase):
    """⚠️ Дедупликация — НА ВСЮ ПОДБОРКУ, а не внутри строки.

    До правки `preview_rows` звал поиск на каждую строку НЕЗАВИСИМО, общего
    «занято» не было вовсе, и одна задача честно попадала в две строки.
    Настоящий подбор (`find_problems`) дедуплицировал на всю подборку
    всегда — расходились именно эти два места.
    """

    def setUp(self):
        cache.clear()
        self.topic = Topic.objects.create(name='Международная торговля',
                                          slug='mt-dedup')
        for index in range(6):
            problem = make_problem('Импортный тариф и мировая цена %d' % index)
            problem.topics.add(self.topic)

    def rows(self):
        return [
            {'query': 'импортный тариф', 'label': 'первая строка',
             'topic': '', 'difficulty': 3, 'count': 2},
            {'query': 'импортный тариф', 'label': 'вторая строка',
             'topic': '', 'difficulty': 3, 'count': 2},
        ]

    def test_same_problem_is_preselected_once(self):
        previews = hw_generator.preview_rows(self.rows())
        picked = [card['id'] for preview in previews
                  for card in preview['cards'] if card['checked']]
        self.assertEqual(len(picked), len(set(picked)),
                         'одна задача выбрана дважды')

    def test_repeat_is_shown_but_marked(self):
        """Повтор не прячем: иначе непонятно, куда делась задача."""
        previews = hw_generator.preview_rows(self.rows())
        first_ids = {card['id'] for card in previews[0]['cards']
                     if card['checked']}
        marked = [card for card in previews[1]['cards']
                  if card['id'] in first_ids]
        self.assertTrue(marked, 'повтор пропал из второй строки')
        for card in marked:
            self.assertFalse(card['checked'])
            self.assertEqual(card['taken_by'], 'первая строка')

    def test_each_row_preselects_exactly_what_it_asked(self):
        previews = hw_generator.preview_rows(self.rows())
        for preview in previews:
            self.assertEqual(preview['picked'], preview['row']['count'])


class MoreCandidatesTests(TestCase):
    """«Показать ещё 5» — поиск по банку, не обращение к модели."""

    def setUp(self):
        cache.clear()
        self.tutor = make_user('more_tutor')
        self.client.force_login(self.tutor)
        for index in range(14):
            make_problem('Эластичность спроса по цене, случай %d' % index)

    def test_more_does_not_touch_the_daily_counter(self):
        before = AiUsageLog.objects.count()
        response = self.client.post(reverse('teacher:api_more_candidates'), {
            'query': 'эластичность спроса', 'difficulty': 3, 'count': 2,
            'offset': 5,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AiUsageLog.objects.count(), before,
                         'бесплатный поиск списал обращение к модели')

    def test_more_returns_the_next_chunk(self):
        first = hw_generator.row_candidates(
            {'query': 'эластичность спроса', 'label': '', 'topic': '',
             'difficulty': 3, 'count': 2}, offset=0, size=5)[0]
        second = hw_generator.row_candidates(
            {'query': 'эластичность спроса', 'label': '', 'topic': '',
             'difficulty': 3, 'count': 2}, offset=5, size=5)[0]
        self.assertTrue(second, 'вторая порция пуста')
        self.assertFalse({c['id'] for c in first} & {c['id'] for c in second},
                         'вторая порция повторяет первую')

    def test_empty_query_is_rejected(self):
        response = self.client.post(reverse('teacher:api_more_candidates'),
                                    {'query': '  '})
        self.assertEqual(response.status_code, 400)


class BuildScreenTests(TestCase):
    """Конструктор подборки: превью работы + настройки."""

    def setUp(self):
        cache.clear()
        self.tutor = make_user('build_tutor')
        self.client.force_login(self.tutor)
        self.group = StudentGroup.objects.create(name='Группа А',
                                                 teacher=self.tutor)

    def test_screen_opens_for_homework_and_exam(self):
        # ⚠️ «Как идёт время», а не «Как ограничим время»: в сессии 10 панель
        # настроек сведена в один партиал, и два разных заголовка одного и
        # того же блока пришлось свести к одному. Оставлена формулировка
        # конструктора контрольной — экрана, где этот блок главный.
        for kind, marker in (('homework', 'Срок сдачи'),
                             ('exam', 'Как идёт время')):
            body = self.client.get(reverse('teacher:assignment_build'),
                                   {'kind': kind}).content.decode()
            self.assertIn(marker, body, kind)

    def test_exam_keeps_the_group_in_links(self):
        """⚠️ Переключатель вида НЕ теряет группу: у контрольной конструктор
        живёт внутри группы, и без номера адрес не собрать."""
        body = self.client.get(reverse('teacher:assignment_build'),
                               {'kind': 'exam',
                                'group': self.group.pk}).content.decode()
        self.assertIn('?kind=homework&amp;group=%d' % self.group.pk, body)
        self.assertIn('/groups/%d/exams/new/' % self.group.pk, body)

    def test_cart_rows_use_the_shared_order(self):
        """Порядок и подписи частей — та же сборка, что у ученика."""
        test = make_problem('Тестовый вопрос', ptype='тест: один верный')
        task = make_problem('Открытая задача')
        rows = cart_rows([str(task.pk), str(test.pk)], self.tutor)
        self.assertEqual([row['key'] for row in rows],
                         [str(test.pk), str(task.pk)],
                         'тесты обязаны идти первыми')
        # Заголовок части с составом (ревью 15.08, фаза 7).
        self.assertEqual(rows[0]['section']['title'], 'Тестовая часть')
        self.assertEqual(rows[0]['section']['count'], 1)
        self.assertEqual(rows[1]['section']['title'], 'Задачи')

    def test_cart_rows_respect_manual_order(self):
        """Ручной порядок не трогаем — репетитор расставил по смыслу урока."""
        test = make_problem('Тестовый вопрос 2', ptype='тест: один верный')
        task = make_problem('Открытая задача 2')
        rows = cart_rows([str(task.pk), str(test.pk)], self.tutor,
                         manual_order=True)
        self.assertEqual([row['key'] for row in rows],
                         [str(task.pk), str(test.pk)])

    def test_alternating_parts_get_no_section_titles(self):
        """⚠️ Подпись части — правда о том, что под ней лежит.

        При чередовании «тест · задача · тест» подпись «Тестовая часть»
        встала бы перед одним-единственным тестом, обещая часть, которой
        нет. Правило проверяет сам список, а не флаг.
        """
        first = make_problem('Тест A', ptype='тест: один верный')
        middle = make_problem('Задача A')
        last = make_problem('Тест B', ptype='тест: один верный')
        rows = cart_rows([str(first.pk), str(middle.pk), str(last.pk)],
                         self.tutor, manual_order=True)
        self.assertEqual([row['section'] for row in rows],
                         [None, None, None])

    def test_default_points_come_from_one_place(self):
        test = make_problem('Тест 3', ptype='тест: верно/неверно')
        task = make_problem('Задача 3')
        rows = {row['key']: row['points']
                for row in cart_rows([str(task.pk), str(test.pk)], self.tutor)}
        self.assertEqual(rows[str(task.pk)], 10)
        self.assertEqual(rows[str(test.pk)], 3)


class PointsFromBuilderTests(TestCase):
    """Балл, выставленный в конструкторе, доезжает до позиции."""

    def test_parse_points_ignores_junk(self):
        self.assertEqual(parse_points('12:3,c7:10'), {'12': 3.0, 'c7': 10.0})
        self.assertEqual(parse_points('12:абв,:5,13:'), {})
        self.assertEqual(parse_points(''), {})
        self.assertEqual(parse_points('12:-4'), {}, 'отрицательный балл')

    def test_created_work_keeps_the_points(self):
        tutor = make_user('points_tutor')
        self.client.force_login(tutor)
        group = StudentGroup.objects.create(name='Группа Б', teacher=tutor)
        problem = make_problem('Задача с баллом')
        self.client.post(reverse('teacher:assignment_create'), {
            'name': 'Работа с баллами', 'groups': [group.pk],
            'problem_ids': str(problem.pk),
            'problem_points': '%d:7' % problem.pk,
        })
        item = AssignmentItem.objects.get(catalog_problem=problem)
        self.assertEqual(float(item.points), 7.0)


class AfterCreationTests(TestCase):
    """⚠️ После создания — СТРАНИЦА САМОЙ РАБОТЫ (п. 12.3).

    Раньше репетитора уводило на дашборд, и увидеть, что получилось, можно
    было только найдя работу в списке.
    """

    def setUp(self):
        self.tutor = make_user('after_tutor')
        self.client.force_login(self.tutor)
        self.group = StudentGroup.objects.create(name='Группа В',
                                                 teacher=self.tutor)
        self.problem = make_problem('Задача для проверки перехода')

    def test_homework_opens_its_own_page(self):
        response = self.client.post(reverse('teacher:assignment_create'), {
            'name': 'Домашка перехода', 'groups': [self.group.pk],
            'problem_ids': str(self.problem.pk),
        })
        assignment = Assignment.objects.get(name='Домашка перехода')
        self.assertRedirects(
            response,
            reverse('teacher:group_assignment',
                    args=[self.group.pk, assignment.pk]))

    def test_banner_says_what_happened(self):
        response = self.client.post(reverse('teacher:assignment_create'), {
            'name': 'Домашка с плашкой', 'groups': [self.group.pk],
            'problem_ids': str(self.problem.pk),
        }, follow=True)
        body = response.content.decode()
        self.assertIn('создана и выдана группе', body)
        self.assertIn(self.group.name, body)


class SplitOnceTests(TestCase):
    """Квота делится по типу РОВНО ОДИН раз."""

    def test_already_split_rows_are_not_split_again(self):
        from teacher.views_generate import _split

        rows = [{'query': 'a', 'label': 'a', 'topic': '', 'difficulty': 3,
                 'count': 2, 'kind': 'open'}]
        form = {'count_open': 4, 'count_test': 2}
        self.assertEqual(_split(rows, form), rows)

    def test_fresh_rows_are_split(self):
        from teacher.views_generate import _split

        rows = [{'query': 'a', 'label': 'a', 'topic': '', 'difficulty': 3,
                 'count': 2}]
        plan = _split(rows, {'count_open': 3, 'count_test': 1})
        self.assertEqual([row['kind'] for row in plan], ['open', 'test'])
        self.assertEqual([row['count'] for row in plan], [3, 1])


class RowKindSurvivesTests(TestCase):
    """⚠️ Тип строки переживает «Переискать».

    Без этого строка-тест превращалась в обычную, и под ней находились
    открытые задачи — та самая подмена, которую чинили в прошлой сессии.
    """

    def setUp(self):
        cache.clear()
        self.tutor = make_user('kind_tutor')
        self.client.force_login(self.tutor)

    def test_research_keeps_the_kind(self):
        reply = json.dumps({'rows': [], 'note': ''})
        with override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=reply):
            body = self.client.post(reverse('teacher:assignment_generate'), {
                'step_action': 'research', 'text': 'домашка',
                'count_open': 1, 'count_test': 1,
                'min_difficulty': 1, 'max_difficulty': 5,
                'row_keep': ['0'], 'row_query': ['эластичность'],
                'row_label': ['строка — тест'], 'row_topic': [''],
                'row_difficulty': ['3'], 'row_count': ['1'],
                'row_kind': ['test'],
            }).content.decode()
        self.assertIn('name="row_kind" value="test"', body)
