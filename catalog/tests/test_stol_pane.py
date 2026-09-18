"""Задача в «Столе»: прямая ссылка и панель одним ответом `?pane=1` (README §1, §3).

Прямая ссылка рисует весь экран на сервере (работает без скрипта); `?pane=1`
отдаёт JSON с теми же партиалами центра и помощи — им сценарий подменяет
задачу без перезагрузки. Шлюз качества — одинаковый. Позиция и соседи без
запроса считаются по фильтрам адреса, в порядке входа (`-id`).
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from problems.models import ProblemPart
from problems.tests.factories import make_problem, make_topic, make_user

TOPIC = 'Монополия и ценовая дискриминация'


class PaneTests(TestCase):

    def setUp(self):
        cache.clear()
        self.topic = make_topic(TOPIC, is_canonical=True)
        self.a = make_problem('Первая задача о монополисте.', topic=self.topic, title='Первый тариф монополиста')
        self.b = make_problem('Вторая задача о монополисте.', topic=self.topic, title='Второй тариф монополиста',
                              solution='Решение длиной больше тридцати знаков, честное.')
        self.c = make_problem('Третья задача о монополисте.', topic=self.topic, title='Третий тариф монополиста')
        ProblemPart.objects.create(problem=self.b, label='а', order=0, statement='Найдите цену.')
        self.hidden = make_problem('Скрытая задача.', topic=self.topic, flagged=True)

    def _pane(self, problem, **params):
        params['pane'] = '1'
        return self.client.get(reverse('catalog:problem_detail', args=[problem.pk]), params)

    def test_pane_returns_all_keys(self):
        data = self._pane(self.b).json()
        self.assertEqual(set(data), {'id', 'title', 'url', 'center_html', 'help_html', 'similar_html', 'meta'})
        self.assertEqual(set(data['meta']), {'position', 'total', 'prev', 'next', 'saved', 'status', 'is_test'})
        self.assertEqual(data['id'], self.b.pk)
        self.assertEqual(data['title'], 'Второй тариф монополиста')
        self.assertEqual(data['url'], '/catalog/problem/%d/' % self.b.pk)
        self.assertIn('Вторая задача о монополисте.', data['center_html'])
        self.assertIn('class="stol-cfg"', data['center_html'])
        self.assertIn('class="help-panel"', data['help_html'])
        self.assertFalse(data['meta']['is_test'])

    def test_flagged_problem_is_404_in_both_forms(self):
        self.assertEqual(self._pane(self.hidden).status_code, 404)
        url = reverse('catalog:problem_detail', args=[self.hidden.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_position_and_neighbours_follow_the_filtered_list(self):
        # Вход по фильтру темы идёт по убыванию id: c, b, a.
        meta = self._pane(self.b, topic=self.topic.pk).json()['meta']
        self.assertEqual((meta['position'], meta['total']), (2, 3))
        self.assertEqual((meta['prev'], meta['next']), (self.c.pk, self.a.pk))
        first = self._pane(self.c, topic=self.topic.pk).json()['meta']
        self.assertEqual((first['position'], first['prev'], first['next']), (1, None, self.b.pk))

    def test_search_position_is_left_to_the_client(self):
        meta = self._pane(self.b, q='монополист').json()['meta']
        self.assertEqual((meta['position'], meta['total'], meta['prev'], meta['next']), (None, None, None, None))

    def test_direct_link_draws_statement_and_help_without_script(self):
        response = self.client.get(reverse('catalog:problem_detail', args=[self.b.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalog/stol.html')
        self.assertTemplateUsed(response, 'catalog/stol/_stol_center.html')
        self.assertTemplateUsed(response, 'catalog/stol/_stol_help.html')
        html = response.content.decode()
        self.assertIn('data-view="stol"', html)
        self.assertIn('Вторая задача о монополисте.', html)
        self.assertIn('class="help-panel"', html)
        self.assertIn('<h1 class="pd-title">Второй тариф монополиста</h1>', html)
        # Похожих под условием больше нет (README §3): они во вкладке ленты.
        self.assertNotIn('class="sim"', html)
        # Окно «Все фильтры» прямой ссылке не нужно: лента ведёт в каталог ссылкой.
        self.assertNotIn('<dialog class="ct-all"', html)

    def test_pane_opening_is_recorded_like_the_direct_link(self):
        from problems.models_platform import ProblemProgress
        student = make_user('pane_student')
        self.client.force_login(student)
        self._pane(self.a)
        self.assertEqual(ProblemProgress.objects.get(user=student, problem=self.a).status, 'opened')

    def test_neighbours_carry_titles(self):
        html = self._pane(self.b, topic=self.topic.pk).json()['center_html']
        self.assertIn('<small>← предыдущая</small><b>Третий тариф монополиста</b>', html)
        self.assertIn('<small>следующая →</small><b>Первый тариф монополиста</b>', html)
