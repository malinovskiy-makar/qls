"""Серверные ответы каталога «Стол» (часть B ночи 18.09.2026).

Прогресс ученика по задаче (ADR 0119): открытие, «Как прошло?», следы
помощи, статус теста; ленты «Похожие» и «Мои»; живые числа карты.
Шлюз качества — в каждом новом ответе.
"""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from problems.models import ProblemPart
from problems.models_platform import ProblemProgress
from problems.tests.factories import make_problem, make_user


def _parts(problem, labels):
    for i, label in enumerate(labels):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement='Вариант %s' % label, order=i)


class ProgressTests(TestCase):

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Монополист выбирает выпуск.', solution='Решение длиной больше тридцати знаков.')
        self.user = make_user('stol_student')
        self.client.force_login(self.user)

    def _post(self, problem=None, **data):
        url = reverse('catalog:api_progress', args=[(problem or self.problem).pk])
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def _row(self):
        return ProblemProgress.objects.get(user=self.user, problem=self.problem)

    def test_opening_the_problem_creates_opened(self):
        self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertEqual(self._row().status, 'opened')

    def test_guest_opening_creates_nothing(self):
        self.client.logout()
        self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk]))
        self.assertFalse(ProblemProgress.objects.exists())

    def test_guest_gets_401_json(self):
        self.client.logout()
        response = self._post(status='self')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'login')

    def test_mark_and_unmark(self):
        self.assertEqual(self._post(status='hint').json()['status'], 'solved_hint')
        self.assertEqual(self._post(status=None).json()['status'], 'opened')

    def test_solved_self_after_viewing_the_solution_is_refused(self):
        self._post(solution_viewed=True)
        response = self._post(status='self')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._row().status, 'opened')

    def test_hints_only_grow(self):
        self._post(hints_opened=3)
        self._post(hints_opened=1)
        self.assertEqual(self._row().hints_opened, 3)

    def test_opened_hint_is_remembered(self):
        from problems.models import Hint
        for i in range(2):
            Hint.objects.create(problem=self.problem, text='Подсказка %d' % i, order=i)
        self.client.get(reverse('catalog:api_hint', args=[self.problem.pk, 2]))
        self.assertEqual(self._row().hints_opened, 2)

    def test_flagged_problem_is_404(self):
        hidden = make_problem('Скрытая.', flagged=True)
        self.assertEqual(self._post(problem=hidden, status='self').status_code, 404)

    def test_unknown_status_is_refused(self):
        self.assertEqual(self._post(status='genius').status_code, 400)


class TestProgressTests(TestCase):
    """Тест ставит статус сам (решение владельца 17.09: тест без потока)."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Выберите верные.', problem_type='тест: все верные',
                                    answer='аб')
        _parts(self.problem, 'абв')
        self.user = make_user('stol_tester')
        self.client.force_login(self.user)

    def _check(self, labels):
        return self.client.post(reverse('catalog:api_test_check', args=[self.problem.pk]),
                                json.dumps({'labels': labels}), content_type='application/json')

    def _status(self):
        return ProblemProgress.objects.get(user=self.user, problem=self.problem).status

    def test_first_try_is_solved_self(self):
        self._check(['а', 'б'])
        self.assertEqual(self._status(), 'solved_self')

    def test_second_try_is_solved_with_hint(self):
        self._check(['в'])
        self._check(['а', 'б'])
        self.assertEqual(self._status(), 'solved_hint')

    def test_reveal_is_failed(self):
        self.client.post(reverse('catalog:api_test_reveal', args=[self.problem.pk]))
        self.assertEqual(self._status(), 'failed')


class StatusesForPageTests(TestCase):

    def test_one_query_for_a_page_of_rows(self):
        from catalog import progress
        user = make_user('stol_rows')
        problems = [make_problem('Задача %d.' % i) for i in range(5)]
        for p in problems[:2]:
            ProblemProgress.objects.create(user=user, problem=p, status='failed')
        with self.assertNumQueries(1):
            statuses = progress.statuses_for(user, [p.pk for p in problems])
        self.assertEqual(statuses, {problems[0].pk: 'failed', problems[1].pk: 'failed'})

    def test_guest_gets_no_statuses(self):
        from django.contrib.auth.models import AnonymousUser

        from catalog import progress
        self.assertEqual(progress.statuses_for(AnonymousUser(), [1, 2]), {})



class MapNumbersTests(TestCase):
    """Узлы карты несут ключ справочника и живое число (P1.5)."""

    def setUp(self):
        cache.clear()

    def _nodes(self):
        data = json.loads(self.client.get(reverse('catalog:topic_map_data')).content)
        return {n['l']: n for n in data['nodes']}

    def test_theme_node_gets_its_topic_key_and_live_count(self):
        from problems.tests.factories import make_topic
        topic = make_topic('Эластичность', is_canonical=True)
        make_problem('Эластичность спроса.', topic=topic)
        make_problem('Скрытая эластичность.', topic=topic, flagged=True)
        node = self._nodes()['Эластичность']
        self.assertEqual((node['db'], node['c']), (topic.pk, 1))

    def test_live_count_equals_the_catalog_filter_count(self):
        from catalog import filters
        from problems.tests.factories import make_topic
        topic = make_topic('Эластичность', is_canonical=True)
        for i in range(3):
            make_problem('Задача %d.' % i, topic=topic)
        groups = filters.build(filters.base_queryset('catalog'), filters.parse({}),
                               mode='strip')[1]['groups']
        topic_group = next(g for g in groups if g['key'] == 'topic')
        count = next(o['count'] for block in topic_group['groups'] for o in block['options']
                     if o['value'] == str(topic.pk))
        self.assertEqual(self._nodes()['Эластичность']['c'], count)

    def test_node_without_canonical_twin_is_not_selectable(self):
        node = self._nodes()['Эластичность']
        self.assertIsNone(node['db'])
        self.assertIsNone(node['c'])


class RailTests(TestCase):
    """Ленты «Похожие» и «Мои ★»: шлюз качества, статусы, вход."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Открытая задача.')
        self.similar = make_problem('Похожая задача.')
        self.hidden = make_problem('Скрытая похожая.', flagged=True)
        self.problem.similar_problems.add(self.similar, self.hidden)
        self.user = make_user('stol_rail')

    def _similar(self):
        return self.client.get(reverse('catalog:api_rail_similar', args=[self.problem.pk])).json()

    def test_similar_skips_flagged(self):
        html = self._similar()['rows_html']
        self.assertIn('/catalog/problem/%d/' % self.similar.pk, html)
        self.assertNotIn('/catalog/problem/%d/' % self.hidden.pk, html)

    def test_guest_rows_have_no_status_column(self):
        self.assertNotIn('class="rail-status', self._similar()['rows_html'])

    def test_logged_in_rows_carry_the_status(self):
        ProblemProgress.objects.create(user=self.user, problem=self.similar, status='failed')
        self.client.force_login(self.user)
        self.assertIn('rail-status--failed', self._similar()['rows_html'])

    def test_rows_show_no_similarity_percent(self):
        self.assertNotIn('%', self._similar()['rows_html'].replace('%}', ''))

    def test_saved_needs_login(self):
        self.assertEqual(self.client.get(reverse('catalog:api_rail_saved')).status_code, 401)

    def test_saved_lists_own_visible_problems(self):
        from problems.models_platform import SavedProblem
        SavedProblem.objects.create(owner=self.user, catalog_problem=self.similar)
        SavedProblem.objects.create(owner=self.user, catalog_problem=self.hidden)
        self.client.force_login(self.user)
        data = self.client.get(reverse('catalog:api_rail_saved')).json()
        self.assertEqual(data['total'], 1)
        self.assertIn('/catalog/problem/%d/' % self.similar.pk, data['rows_html'])

    def test_similar_of_a_flagged_problem_is_404(self):
        response = self.client.get(reverse('catalog:api_rail_similar', args=[self.hidden.pk]))
        self.assertEqual(response.status_code, 404)


class StolProblemPageTests(TestCase):
    """«Стол» на странице задачи: лента сервером, теги свёрнуты, «Как прошло?»."""

    def setUp(self):
        cache.clear()
        from problems.models import Tag
        from problems.tests.factories import make_topic
        topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        self.problem = make_problem('Монополист выбирает выпуск.', topic=topic)
        self.problem.tags.add(Tag.objects.create(name='Курно', slug='kurno', kind='canonical'))
        self.similar = make_problem('Похожая задача.')
        self.problem.similar_problems.add(self.similar)
        self.url = reverse('catalog:problem_detail', args=[self.problem.pk])

    def _html(self):
        return self.client.get(self.url).content.decode('utf-8')

    def test_rail_is_rendered_by_the_server(self):
        html = self._html()
        self.assertIn('id="stol-rail-list"', html)
        self.assertIn('/catalog/problem/%d/' % self.similar.pk, html)

    def test_tags_are_folded_for_everyone(self):
        html = self._html()
        self.assertIn('<details class="pp-tags">', html)
        self.assertIn('Теги · 1', html)

    def test_guest_has_no_how_block_and_no_status_column(self):
        html = self._html()
        self.assertNotIn('id="how"', html)
        self.assertNotIn('class="rail-status', html)

    def test_student_sees_how_block(self):
        self.client.force_login(make_user('stol_page_student'))
        self.assertIn('id="how"', self._html())

    def test_teacher_has_no_how_block(self):
        self.client.force_login(make_user('stol_page_teacher', role='teacher'))
        self.assertNotIn('id="how"', self._html())

    def test_solution_viewed_disables_solved_self(self):
        user = make_user('stol_page_viewed')
        ProblemProgress.objects.create(user=user, problem=self.problem, solution_viewed=True)
        self.client.force_login(user)
        self.assertRegex(self._html(), r'data-how="self" disabled')


class ContinueRowTests(TestCase):
    """«Продолжить» на входе каталога (P3): правило нуля, шлюз, свежие первыми."""

    def setUp(self):
        cache.clear()
        self.user = make_user('stol_continue')
        self.failed = make_problem('Не получилось.')
        self.opened = make_problem('Открывал.')
        self.solved = make_problem('Решил.')
        self.hidden = make_problem('Скрытая.', flagged=True)
        for problem, status in ((self.failed, 'failed'), (self.opened, 'opened'),
                                (self.solved, 'solved_self'), (self.hidden, 'failed')):
            ProblemProgress.objects.create(user=self.user, problem=problem, status=status)

    def _html(self, **params):
        return self.client.get('/catalog/', params).content.decode('utf-8')

    def test_student_sees_failed_and_opened_but_not_solved_or_hidden(self):
        self.client.force_login(self.user)
        html = self._html()
        block = html.split('class="se-continue"', 1)[1].split('</nav>', 1)[0]
        for problem in (self.failed, self.opened):
            self.assertIn('/catalog/problem/%d/' % problem.pk, block)
        for problem in (self.solved, self.hidden):
            self.assertNotIn('/catalog/problem/%d/' % problem.pk, block)

    def test_no_rows_no_block(self):
        self.client.force_login(make_user('stol_continue_empty'))
        self.assertNotIn('class="se-continue"', self._html())

    def test_guest_has_no_block(self):
        self.assertNotIn('class="se-continue"', self._html())

    def test_search_hides_the_block(self):
        self.client.force_login(self.user)
        self.assertNotIn('class="se-continue"', self._html(q='монополия'))


class MapApplyIsAFilterTests(TestCase):
    """«Показать задачи» на карте — фильтр каталога, а не текстовый поиск (P7)."""

    def test_script_builds_topic_and_tag_params_from_db_keys(self):
        import io
        src = io.open('catalog/static/catalog/js/topic_map.js', encoding='utf-8').read()
        handler = src.split("getElementById('tmap-apply').addEventListener", 1)[1]
        handler = handler.split('\n});', 1)[0]
        self.assertIn("node.k === 'theme' ? 'topic=' : 'tag='", handler)
        self.assertIn('node.db', handler)
        self.assertNotIn('?q=', handler)


class PhoneBarTests(TestCase):
    """Нижняя панель телефона: кнопка — только при данных (правило нуля)."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Условие без подсказок и решения.')

    def _bar(self, problem=None):
        html = self.client.get(reverse('catalog:problem_detail',
                                       args=[(problem or self.problem).pk])).content.decode()
        return html.split('class="stol-phonebar"', 1)[1].split('</nav>', 1)[0]

    def test_bare_problem_has_no_hint_solution_or_next(self):
        bar = self._bar()
        for absent in ('data-phone="hint"', 'data-phone="sol"', 'Дальше'):
            self.assertNotIn(absent, bar)

    def test_hint_solution_and_next_appear_with_data(self):
        from problems.models import Hint
        problem = make_problem('С подсказкой.', solution='Длинное решение этой задачи по шагам.')
        Hint.objects.create(problem=problem, text='Подсказка', order=1)
        problem.similar_problems.add(self.problem)
        bar = self._bar(problem)
        for present in ('data-phone="hint"', 'data-phone="sol"',
                        '/catalog/problem/%d/' % self.problem.pk):
            self.assertIn(present, bar)

    def test_no_emoji_on_the_hint_button(self):
        from problems.models import Hint
        Hint.objects.create(problem=self.problem, text='Подсказка', order=1)
        html = self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk])).content.decode()
        self.assertNotIn('💡', html)


class TestNextButtonTests(TestCase):
    """После ответа у теста главная кнопка — «Дальше ›» (P6), при похожих."""

    def _html(self, with_similar):
        problem = make_problem('Выберите верное.', problem_type='тест: один ответ', answer='а')
        _parts(problem, 'аб')
        if with_similar:
            problem.similar_problems.add(make_problem('Похожая.'))
        return self.client.get(reverse('catalog:problem_detail', args=[problem.pk])).content.decode()

    def test_next_is_the_main_button_when_there_is_somewhere_to_go(self):
        done = self._html(True).split('id="row-done"', 1)[1].split('</div>', 1)[0]
        self.assertIn('class="btn btn--main"', done)
        self.assertIn('Дальше ›', done)

    def test_no_next_without_similar(self):
        done = self._html(False).split('id="row-done"', 1)[1].split('</div>', 1)[0]
        self.assertNotIn('Дальше ›', done)
