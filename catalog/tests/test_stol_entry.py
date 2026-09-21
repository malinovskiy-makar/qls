"""Вход «Стола» (вид `entry` единого шаблона `stol.html`, README §2).

Сервер рисует ленту целиком (без скрипта экран рабочий), заголовок — только
на чистом входе, чипы и окно «Все фильтры» — одно состояние и один адрес,
галереи и модалки «Условие» нет, процента близости и эмодзи нет, поиск
пишет ровно одну строку журнала, у гостя нет колонки статусов.
"""
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from catalog import filters
from problems.models_platform import ProblemProgress, SearchLog
from problems.tests.factories import make_problem, make_topic, make_user

BASE = Path(settings.BASE_DIR)
TOPIC = 'Монополия и ценовая дискриминация'
ROW = re.compile(r'<a class="rail-row\b')


class EntryTests(TestCase):

    def setUp(self):
        cache.clear()
        self.topic = make_topic(TOPIC, is_canonical=True)
        self.problems = [make_problem('Монополист %d выбирает выпуск.' % i, topic=self.topic,
                                      difficulty=3) for i in range(3)]
        make_problem('Задача без темы про налог.')
        self.hidden = make_problem('Скрытая задача про монополию.', flagged=True, topic=self.topic)

    def _get(self, **params):
        return self.client.get(reverse('catalog:problem_list'), params)

    def test_entry_is_the_one_template_and_draws_rows_on_the_server(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalog/stol.html')
        self.assertTemplateUsed(response, 'catalog/stol/_stol_entry.html')
        self.assertTemplateNotUsed(response, 'catalog/problem_list.html')
        html = response.content.decode()
        self.assertEqual(len(ROW.findall(html)), 4)
        self.assertNotIn('/catalog/problem/%d/' % self.hidden.pk, html)
        self.assertIn('data-view="entry"', html)

    def test_title_only_on_a_calm_entry(self):
        self.assertIn('stol-entry is-calm', self._get().content.decode())
        self.assertNotIn('stol-entry is-calm', self._get(topic=self.topic.pk).content.decode())
        with mock.patch('catalog.views._search_ids',
                        return_value=([p.pk for p in self.problems], {}, False)):
            self.assertNotIn('stol-entry is-calm', self._get(q='монополист').content.decode())

    def test_counter_is_filtered_total(self):
        text = self._get(topic=self.topic.pk).content.decode()
        self.assertRegex(text, r'<b>3</b> задачи')
        self.assertRegex(self._get().content.decode(), r'<b>4</b> задачи')

    def test_chip_and_window_give_one_address(self):
        """Вариант темы в выпадашке чипа и в окне — один ключ `data-topic`,
        а адрес после выбора строит только `filters.query()`."""
        html = self._get().content.decode()
        dropdown = html[html.index('id="se-dd-topic"'):html.index('data-dd="difficulty"')]
        window = html[html.index('<dialog class="ct-all"'):html.index('</dialog>')]
        values = set(re.findall(r'data-topic="(\d+)"', dropdown))
        self.assertEqual(values, {str(self.topic.pk)})
        self.assertEqual(values, set(re.findall(r'data-topic="(\d+)"', window)))
        state = self.client.get(reverse('catalog:api_filter_state'), {'topic': self.topic.pk}).json()
        self.assertEqual(state['url'], filters.query({}, filters.parse({'topic': [str(self.topic.pk)]})))
        self.assertEqual(state['counts']['topic'][str(self.topic.pk)], 3)

    def test_old_gallery_and_table_addresses_open_rows(self):
        for view in ('gallery', 'table'):
            html = self._get(view=view).content.decode()
            self.assertEqual(len(ROW.findall(html)), 4, view)
            self.assertNotIn('ct-gallery', html)
            self.assertNotIn('view=', html.split('<section class="ct-results"')[1])

    def test_no_condition_modal_and_no_card_buttons(self):
        html = self._get().content.decode()
        self.assertNotIn('openCatalogModal', html)
        self.assertNotIn('c-modal-backdrop', html)
        self.assertNotIn('ca-btn', html)

    def test_search_has_no_closeness_percent_and_logs_once(self):
        ids = [p.pk for p in self.problems]
        with mock.patch('catalog.views._search_ids',
                        return_value=(ids, {pk: 0.83 for pk in ids}, False)):
            html = self._get(q='монополист выбирает').content.decode()
        results = html.split('<section class="ct-results"')[1].split('</section>')[0]
        self.assertNotRegex(results, r'\d\s*%')
        self.assertEqual(len(ROW.findall(results)), 3)
        self.assertEqual(SearchLog.objects.count(), 1)

    def test_guest_has_no_status_column_student_has(self):
        self.assertNotIn('rail-status', self._get().content.decode())
        student = make_user('entry_student')
        ProblemProgress.objects.create(user=student, problem=self.problems[0], status='failed')
        self.client.force_login(student)
        html = self._get().content.decode()
        self.assertIn('rail-status--failed', html)
        self.assertEqual(html.count('rail-status--none'), 3)

    def test_continue_row_is_on_the_calm_entry_only(self):
        student = make_user('entry_student2')
        ProblemProgress.objects.create(user=student, problem=self.problems[1], status='opened')
        self.client.force_login(student)
        self.assertIn('se-continue', self._get().content.decode())
        self.assertNotIn('se-continue', self._get(topic=self.topic.pk).content.decode())

    def test_map_pill_counts_selection(self):
        html = self._get(topic=self.topic.pk).content.decode()
        self.assertIn('Карта тем: выбрано 1', html)
        self.assertIn('"topics": ["%d"]' % self.topic.pk, html)

    def test_random_button_carries_the_filters(self):
        html = self._get(topic=self.topic.pk).content.decode()
        self.assertIn('href="%s?topic=%d"' % (reverse('catalog:random_problem'), self.topic.pk), html)


class NoEmojiInStolTemplatesTests(SimpleTestCase):
    """Иконки — только SVG из общего набора; эмодзи рисует ОС мимо палитры."""

    RX_EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-⛿✀-➿]')

    RX_COMMENT = re.compile(r'{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}', re.DOTALL)

    def test_no_emoji(self):
        root = BASE / 'catalog/templates/catalog'
        files = [root / 'stol.html', root / '_catalog_results.html', root / '_catalog_chips.html']
        files += sorted((root / 'stol').glob('*.html'))
        offenders = {}
        for path in files:
            # До человека доходит разметка, а не комментарии шаблона («⚠️» в них — договорённость проекта).
            src = self.RX_COMMENT.sub('', path.read_text(encoding='utf-8'))
            # Звёзды сложности ★☆ — это текстовые символы шрифта, не эмодзи.
            hits = {c for c in self.RX_EMOJI.findall(src) if c not in '★☆'}
            if hits:
                offenders[path.name] = sorted(hits)
        self.assertEqual(offenders, {})
