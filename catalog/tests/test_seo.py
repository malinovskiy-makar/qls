"""SEO: robots.txt, sitemap.xml, боты без платного реранжирования и без
журнала, заголовки и описания страниц (19.09.2026, Notion «Решения»
«SEO-фикс: боты не тратят бюджет умного поиска…»)."""
import re
from unittest import mock

from django.test import RequestFactory, TestCase
from django.urls import reverse

from catalog import seo
from problems.models import OlympiadRef, Problem
from problems.models_platform import SearchLog
from problems.tests.factories import make_problem, make_topic

GOOGLEBOT = ('Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/125.0 Mobile Safari/537.36 '
             '(compatible; Googlebot/2.1; +http://www.google.com/bot.html)')
GOOGLEOTHER = ('Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/125.0 Mobile Safari/537.36 (compatible; GoogleOther)')
AMAZONBOT = ('Mozilla/5.0 AppleWebKit/600.2.5 (KHTML, like Gecko) Version/8.0.2 Safari/600.2.5 '
             '(Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot)')
BROWSER = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
           'Chrome/125.0.0.0 Safari/537.36')

TITLE = re.compile(r'<title>(.*?)</title>', re.S)
DESCRIPTION = re.compile(r'<meta name="description" content="(.*?)">', re.S)


def _title(html):
    return TITLE.search(html).group(1)


def _description(html):
    return DESCRIPTION.search(html).group(1)


def _meta(html, prop):
    found = re.search(r'<meta property="%s" content="(.*?)">' % re.escape(prop), html, re.S)
    return found.group(1) if found else None


class RobotsTests(TestCase):
    def test_robots_txt_closes_search_pages_and_points_to_sitemap(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        text = response.content.decode()
        self.assertIn('User-agent: *', text)
        self.assertIn('Disallow: /catalog/?q=*', text)
        self.assertIn('Sitemap: https://weconomics.ai/sitemap.xml', text)
        # Остальное разрешено: общего запрета быть не должно.
        self.assertNotIn('Disallow: /\n', text)

    def test_robots_txt_is_get_only(self):
        self.assertEqual(self.client.post('/robots.txt').status_code, 405)


class SitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.visible = make_problem('Видимая задача про монополию.', title='Монополия — 1')
        cls.draft = make_problem('Черновик.', status=Problem.Status.DRAFT)
        cls.dupe = make_problem('Копия.', status=Problem.Status.DUPLICATE)
        cls.flagged = make_problem('Брак.', flagged=True)
        cls.unreviewed = make_problem('Человек ещё не смотрел.', hidden_pending_review=True)
        cls.broken = make_problem('Битый текст.', content_status=Problem.ContentStatus.NEEDS_FIX)

    def _urls(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('xml', response['Content-Type'])
        return re.findall(r'<loc>(.*?)</loc>', response.content.decode())

    def test_only_visible_problems_are_listed(self):
        urls = self._urls()
        listed = {u for u in urls if '/catalog/problem/' in u}
        self.assertEqual(listed, {'https://testserver/catalog/problem/%d/' % self.visible.pk})

    def test_permanent_entries_are_listed(self):
        urls = self._urls()
        for path in ('/', '/catalog/', '/catalog/map/', '/calc2/', '/game/'):
            self.assertIn('https://testserver' + path, urls)

    def test_search_pages_are_not_in_the_map(self):
        self.assertFalse([u for u in self._urls() if '?q=' in u])


class CrawlerDetectionTests(TestCase):
    def _request(self, agent):
        return RequestFactory().get('/catalog/', HTTP_USER_AGENT=agent) if agent is not None \
            else RequestFactory().get('/catalog/')

    def test_known_crawlers(self):
        for agent in (GOOGLEBOT, GOOGLEOTHER, AMAZONBOT, 'Mozilla/5.0 (compatible; bingbot/2.0)',
                      'Mozilla/5.0 (compatible; YandexBot/3.0)', 'SemrushBot/7', 'AhrefsBot/7.0',
                      'MJ12bot/v1.4.8', 'CCBot/2.0', 'GPTBot/1.0', 'ClaudeBot/1.0'):
            self.assertTrue(seo.is_crawler(self._request(agent)), agent)

    def test_people_and_empty_agent_are_not_crawlers(self):
        for agent in (BROWSER, '', None):
            self.assertFalse(seo.is_crawler(self._request(agent)), repr(agent))


class BotsDoNotSpendTheBudgetTests(TestCase):
    """Краулер не вызывает платное переранжирование и не пишет `SearchLog`."""

    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Монополия и ценовая дискриминация')
        cls.problems = [make_problem('Монополист выбирает цену %d.' % i, title='Монополия %d' % i,
                                     topic=cls.topic) for i in range(3)]

    def _search(self, agent=None):
        ids = [p.pk for p in self.problems]
        extra = {'HTTP_USER_AGENT': agent} if agent else {}
        with mock.patch('catalog.views._search_ids', return_value=(ids, {}, False)), \
                mock.patch('catalog.rerank.apply', return_value=(None, 'fallback')) as apply:
            response = self.client.get(reverse('catalog:problem_list'),
                                       {'q': 'монополист выбирает цену'}, **extra)
        return response, apply

    def test_bot_gets_results_but_no_rerank_and_no_log(self):
        for agent in (GOOGLEBOT, GOOGLEOTHER, AMAZONBOT):
            response, apply = self._search(agent)
            self.assertEqual(response.status_code, 200, agent)
            self.assertIn('Монополия 0', response.content.decode(), agent)
            apply.assert_not_called()
            self.assertEqual(response['X-Smart-Search'], 'off')
        self.assertEqual(SearchLog.objects.count(), 0)

    def test_person_still_reranks_and_is_logged(self):
        response, apply = self._search(BROWSER)
        self.assertEqual(response.status_code, 200)
        apply.assert_called_once()
        self.assertEqual(response['X-Smart-Search'], 'fallback')
        self.assertEqual(SearchLog.objects.count(), 1)

    def test_filter_state_endpoint_does_not_log_a_bot_either(self):
        ids = [p.pk for p in self.problems]
        with mock.patch('catalog.views._search_ids', return_value=(ids, {}, False)), \
                mock.patch('catalog.rerank.apply', return_value=(None, 'fallback')) as apply:
            self.client.get(reverse('catalog:api_filter_state'),
                            {'q': 'монополист', 'log': '1'}, HTTP_USER_AGENT=GOOGLEBOT)
        apply.assert_not_called()
        self.assertEqual(SearchLog.objects.count(), 0)


class NoindexOnSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Монополия и ценовая дискриминация')
        cls.problem = make_problem('Монополист выбирает цену.', title='Монополия 1', topic=cls.topic)

    def test_search_results_are_noindex_and_plain_catalog_is_not(self):
        with mock.patch('catalog.views._search_ids', return_value=([self.problem.pk], {}, False)):
            searched = self.client.get(reverse('catalog:problem_list'), {'q': 'test'}).content.decode()
        self.assertIn('<meta name="robots" content="noindex, nofollow">', searched)
        plain = self.client.get(reverse('catalog:problem_list')).content.decode()
        self.assertNotIn('noindex', plain)

    def test_problem_page_is_not_noindex(self):
        html = self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk])).content.decode()
        self.assertNotIn('noindex', html)


class PageMetadataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Монополия и ценовая дискриминация')
        cls.plain = make_problem('На ярмарке спрос $Q = 120 - P$.', title='Вмешательство — 5',
                                 topic=cls.topic)
        cls.with_olympiad = make_problem('Задача школьного тура.', title='Налог на продавца',
                                         topic=cls.topic)
        OlympiadRef.objects.create(problem=cls.with_olympiad, source_site='solvehub',
                                   olympiad_slug='vseros',
                                   olympiad_name='Всероссийская олимпиада школьников по экономике')
        cls.unknown_olympiad = make_problem('Задача из редкой олимпиады.', title='Редкая задача',
                                            topic=cls.topic)
        OlympiadRef.objects.create(problem=cls.unknown_olympiad, source_site='ile',
                                   olympiad_slug='kondrat',
                                   olympiad_name='Межрегиональная олимпиада школьников имени Н. Д. Кондратьева')
        cls.cut = make_problem('Известно, что монополист получает максимальную выручку в точке '
                               '$P=20$, $Q=40$. Найдите функцию спроса.',
                               title='Известно, что монополист получает максимальную выр',
                               topic=cls.topic)
        cls.bare = make_problem('Задача без всего.')
        cls.formula = make_problem('Условие.', title='Спрос $Q = 10 - P$ линейный', topic=cls.topic)

    def _page(self, problem):
        html = self.client.get(reverse('catalog:problem_detail', args=[problem.pk])).content.decode()
        return html, _title(html), _description(html)

    def test_problem_without_olympiad(self):
        html, title, description = self._page(self.plain)
        self.assertEqual(title, 'Вмешательство — 5 — олимпиадная задача по экономике | Weconomics.ai')
        self.assertEqual(
            description,
            'Задача по теме «Монополия и ценовая дискриминация» с подробным решением и '
            'ИИ-ассистентом. Weconomics.ai — база из 14 000+ задач для подготовки к '
            'олимпиадам по экономике.')
        self.assertEqual(_meta(html, 'og:title'), title)
        self.assertEqual(_meta(html, 'og:description'), description)

    def test_problem_with_olympiad(self):
        _html, title, description = self._page(self.with_olympiad)
        self.assertEqual(title, 'Налог на продавца — задача ВсОШ по экономике | Weconomics.ai')
        self.assertEqual(
            description,
            'Задача по «Монополия и ценовая дискриминация» с олимпиады ВсОШ, с подробным '
            'решением и ИИ-ассистентом. Weconomics.ai — база из 14 000+ задач для подготовки '
            'к олимпиадам по экономике.')

    def test_olympiad_without_short_name_falls_back_to_no_olympiad(self):
        _html, title, description = self._page(self.unknown_olympiad)
        self.assertEqual(title, 'Редкая задача — олимпиадная задача по экономике | Weconomics.ai')
        self.assertNotIn('Кондратьева', description)

    def test_cut_title_uses_topic_heading_not_the_stub(self):
        _html, title, _description_ = self._page(self.cut)
        self.assertTrue(title.startswith('Задача: Монополия и ценовая дискриминация — '), title)
        self.assertNotIn('максимальную выр', title)

    def test_no_title_and_no_topic_degrades_cleanly(self):
        _html, title, description = self._page(self.bare)
        self.assertEqual(title, 'Задача — олимпиадная задача по экономике | Weconomics.ai')
        self.assertTrue(description.startswith('Олимпиадная задача по экономике с подробным решением'))
        for text in (title, description):
            self.assertNotIn('None', text)
            self.assertNotIn('{', text)
            self.assertNotIn('«»', text)

    def test_formula_markup_does_not_reach_the_title(self):
        _html, title, _description_ = self._page(self.formula)
        self.assertNotIn('$', title)
        self.assertNotIn('\\', title)

    def test_site_name_and_verification_on_every_page(self):
        for url in ('/', reverse('catalog:problem_list'), reverse('calc2:calculator'),
                    reverse('game:page'), reverse('login'), reverse('register')):
            html = self.client.get(url).content.decode()
            self.assertIn('<meta property="og:site_name" content="Weconomics.ai | Олимпиадная экономика">',
                          html, url)
            self.assertIn('<meta name="google-site-verification" '
                          'content="NqSKqN6aS731NKo_q1A1GKZj_45h_x_k4O-grGlrMFY">', html, url)
            self.assertIn('<meta name="yandex-verification" content="524e770a1722738e">', html, url)

    def test_home(self):
        html = self.client.get('/').content.decode()
        self.assertEqual(_title(html), 'Weconomics.ai — подготовка к олимпиадам по экономике')
        self.assertEqual(_description(html), seo.HOME_DESCRIPTION)
        self.assertIn('14 000+ задач с решениями', _description(html))
        self.assertEqual(_meta(html, 'og:title'), 'Weconomics.ai — подготовка к олимпиадам по экономике')

    def test_calculator(self):
        html = self.client.get(reverse('calc2:calculator')).content.decode()
        self.assertEqual(_title(html), 'Графический калькулятор по экономике — онлайн | Weconomics.ai')
        self.assertEqual(_description(html), seo.CALC_DESCRIPTION)

    def test_game(self):
        html = self.client.get(reverse('game:page')).content.decode()
        self.assertEqual(_title(html), 'Wecon Rush — игра для подготовки к олимпиадам по экономике | Weconomics.ai')
        self.assertEqual(_description(html), seo.GAME_DESCRIPTION)
        self.assertEqual(_meta(html, 'og:title'), _title(html))
        # Имя сайта одно: прежнего «Weconomics» без домена быть не должно.
        self.assertEqual(html.count('property="og:site_name"'), 1)

    def test_topic_page(self):
        html = self.client.get(reverse('catalog:problem_list'), {'topic': self.topic.pk}).content.decode()
        self.assertEqual(_title(html),
                         'Задачи по теме «Монополия и ценовая дискриминация» — олимпиадная экономика | Weconomics.ai')
        self.assertEqual(
            _description(html),
            'Подборка задач по теме «Монополия и ценовая дискриминация» с решениями и '
            'ИИ-ассистентом — для подготовки к олимпиадам по экономике. 5 задач на Weconomics.ai')

    def test_other_filter_combinations_keep_the_default_title(self):
        html = self.client.get(reverse('catalog:problem_list'),
                               {'topic': self.topic.pk, 'difficulty': '3'}).content.decode()
        self.assertNotIn('Задачи по теме', _title(html))


class PlainTextTests(TestCase):
    def test_formula_markup_is_reduced_to_text(self):
        self.assertEqual(seo._plain(r'Спрос $\frac{a}{b}$ и $Q = 10$', 80), 'Спрос ab и Q = 10')
        self.assertEqual(seo._plain(r'Цена \$3 за штуку', 80), 'Цена $3 за штуку')
