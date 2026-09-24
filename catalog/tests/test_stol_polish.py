"""Полировка «Стола» 24.09.2026 (журнал `claude/JOURNAL_STOL_POLISH_20260924.md`).

Решения владельца 24.09 (Notion «Решения»): совет в помощи один раз, потом ⓘ;
строка лимита ИИ только при малом остатке; особенности задачи на карточке;
фокус с панелями поверх; строки выдачи с метками у названия. Здесь — то, что
видно по разметке сервера; поведение в браузере — `stol_polish_runner.mjs`.
"""
import json
import re

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from problems.ai import core
from problems.enrich import features as enrich_features
from problems.models import AiUsageLog, Feature, Hint, ProblemFeature, Tag
from problems.tests.factories import make_problem, make_topic, make_user

TIP = ('История чата в этой задаче сохраняется. Выделите фрагмент условия или ответа ИИ, '
       'чтобы обсудить именно его.')


def _help(html):
    start = html.index('<aside class="help-panel"')
    return html[start:html.index('</aside>', start)]


def _page(client, problem):
    return client.get(reverse('catalog:problem_detail', args=[problem.pk])).content.decode()


@override_settings(CATALOG_CHAT_PROVIDER='fake', AI_PROVIDER='fake')
class HelpTextsTests(TestCase):
    """Фаза 1: тексты панели помощи и совет один раз."""

    def setUp(self):
        cache.clear()
        topic = make_topic('Монополия', is_canonical=True)
        self.problem = make_problem('Монополист продаёт электроэнергию.', topic=topic,
                                    title='Тариф монополиста',
                                    solution='Решение задачи длиннее тридцати знаков: $MR = MC$.')
        Hint.objects.create(problem=self.problem, text='Первая подсказка.', order=0)
        self.client.force_login(make_user('polish_student'))

    def test_tip_card_and_info_button_once_each_both_hidden(self):
        panel = _help(_page(self.client, self.problem))
        self.assertEqual(panel.count('id="help-tipcard"'), 1)
        self.assertEqual(panel.count('id="help-info"'), 1)
        self.assertIn('<div class="help-tipcard" id="help-tipcard" hidden>', panel)
        self.assertRegex(panel, r'<button type="button" class="help-info" id="help-info"[^>]* hidden>')
        # Текст ровно один и тот же — в карточке и во всплывающей подсказке ⓘ.
        card = re.search(r'id="help-tipcard" hidden>.*?<p>(.*?)</p>', panel, re.S).group(1)
        pop = re.search(r'id="help-info-pop" role="tooltip" hidden>(.*?)</span>', panel, re.S).group(1)
        self.assertEqual(card, TIP)
        self.assertEqual(pop, TIP)
        self.assertIn('id="help-tip-ok">Понятно</button>', panel)
        self.assertIn('aria-expanded="false" aria-describedby="help-info-pop"', panel)
        self.assertNotIn('ladder-lead', panel)

    def test_guest_has_neither_card_nor_info(self):
        self.client.logout()
        panel = _help(_page(self.client, self.problem))
        self.assertNotIn('help-tipcard', panel)
        self.assertNotIn('help-info', panel)
        self.assertNotIn(TIP, panel)

    def test_old_texts_gone_new_texts_present(self):
        html = _page(self.client, self.problem)
        panel = _help(html)
        for gone in ('остаётся ИИ', 'Выделите фрагмент условия, чтобы обсудить его с ИИ',
                     'наведёт на первый шаг', 'теория, план', 'Полное решение', 'в самом конце',
                     'Вопрос по задаче или фото', 'останется здесь и после перезагрузки'):
            self.assertNotIn(gone, panel)
        for present in ('Поможет сделать первый шаг', 'Обсуждение и проверка вашего решения',
                        'Эталонное решение', 'Свериться с «ключом»',
                        'placeholder="Вопрос по задаче или решению"'):
            self.assertIn(present, panel)
        self.assertIn('Открыть эталонное решение?', html)
        self.assertNotIn('Открыть полное решение?', html)
        # `aria-label` поля тот же.
        self.assertIn('aria-label="Вопрос ИИ или решение на проверку"', panel)

    def test_bare_problem_has_no_empty_note_and_no_empty_ladder(self):
        bare = make_problem('Задача без подсказок и решения.')
        panel = _help(_page(self.client, bare))
        self.assertNotIn('ladder-none', panel)
        self.assertIn('data-step="ai"', panel)
        # Без чата ступеней не остаётся — лестницы нет вовсе (правило нуля).
        with self.settings(CATALOG_CHAT_PROVIDER='anthropic', ANTHROPIC_API_KEY=''):
            panel = _help(_page(self.client, bare))
        self.assertNotIn('help-ladder', panel)
        self.assertNotIn('ladder-none', panel)


class EntryAndSiteTextsTests(TestCase):
    """Фаза 1: вход каталога, учебник, версия."""

    def setUp(self):
        cache.clear()
        make_problem('Задача про эластичность спроса.', topic=make_topic('Эластичность', is_canonical=True))

    def test_catalog_entry_texts(self):
        html = self.client.get('/catalog/').content.decode()
        self.assertIn('Поиск ищет по смыслу: точные слова не нужны', html)
        self.assertNotIn('Enter – найти', html)
        self.assertNotIn('class="ask-kbd"', html)
        self.assertNotIn('складываются: «или»', html)
        # Выпадашка «Тема» на месте, в шапке одно слово.
        self.assertIn('<div class="se-dd-head"><b>Тема</b></div>', html)
        # У «Сложности» и «Задачи и тесты» пояснения остались (в фикстуре их
        # выпадашек нет — смотрим шаблон).
        with open('catalog/templates/catalog/stol/_stol_entry.html', encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('<span class="se-dd-note">можно несколько</span>', src)
        self.assertIn('<span class="se-dd-note">одно из трёх</span>', src)

    def test_textbook_text(self):
        html = self.client.get('/textbook/').content.decode()
        self.assertIn('от самых первых моделей до продвинутых\n     сюжетов. Мы уже пишем.', html)
        self.assertNotIn('заключительного этапа', html)

    def test_site_version_is_beta_1_1(self):
        self.assertEqual(settings.SITE_VERSION, 'Beta 1.1')
        html = self.client.get('/catalog/').content.decode()
        self.assertIn('<div class="site-version">Beta 1.1</div>', html)


class FeedbackButtonHeightTests(TestCase):
    """Фаза 1: «Проблема или предложение» — 30 px, как переключатель темы."""

    def test_rule_sets_30px_without_vertical_padding(self):
        with open('templates/_fb_btn_style.html', encoding='utf-8') as fh:
            src = fh.read()
        rule = src.split('.fb-btn {', 1)[1].split('}', 1)[0]
        self.assertIn('height: 30px;', rule)
        self.assertIn('box-sizing: border-box;', rule)
        self.assertIn('padding: 0 10px;', rule)
        narrow = src.split('@media (max-width: 1420px)', 1)[1].split('\n}', 1)[0]
        self.assertIn('.fb-btn { padding: 0 7px; }', narrow)


@override_settings(CATALOG_CHAT_PROVIDER='fake', AI_PROVIDER='fake', AI_GENERATOR_DAILY_LIMIT=30)
class LimitLineTests(TestCase):
    """Фаза 2: строка лимита ИИ только при остатке ≤ 5, честная подпись."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Монополист выбирает выпуск.', title='Выпуск монополиста')
        self.user = make_user('polish_limit')
        self.client.force_login(self.user)

    def _spend(self, n):
        AiUsageLog.objects.bulk_create([AiUsageLog(user=self.user, kind='catalog_chat',
                                                   model_name='fake', ok=True) for _ in range(n)])

    def _line(self):
        panel = _help(_page(self.client, self.problem))
        m = re.search(r'<p class="sv-limit" id="sv-limit"( hidden)?>(.*?)</p>', panel)
        return m

    def test_30_left_is_hidden(self):
        m = self._line()
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), ' hidden')
        self.assertEqual(m.group(2), 'Запросов к ИИ на сегодня: осталось <b id="sv-remaining">30</b>')

    def test_5_left_is_shown(self):
        self._spend(25)
        m = self._line()
        self.assertIsNone(m.group(1))
        self.assertEqual(re.sub(r'<.*?>', '', m.group(2)), 'Запросов к ИИ на сегодня: осталось 5')

    def test_6_left_is_still_hidden(self):
        self._spend(24)
        self.assertEqual(self._line().group(1), ' hidden')

    def test_0_left_is_shown(self):
        self._spend(30)
        m = self._line()
        self.assertIsNone(m.group(1))
        self.assertIn('осталось <b id="sv-remaining">0</b>', m.group(2))

    def test_counted_with_chat_only(self):
        """Доступен только чат (модель проверки без ключа) — число всё равно верное."""
        self._spend(27)
        with self.settings(AI_PROVIDER='anthropic', ANTHROPIC_API_KEY=''):
            m = self._line()
        self.assertIsNotNone(m)
        self.assertIsNone(m.group(1))
        self.assertIn('осталось <b id="sv-remaining">3</b>', m.group(2))

    def test_guest_has_no_line(self):
        self.client.logout()
        html = _page(self.client, self.problem)
        self.assertNotIn('sv-limit', _help(html))
        self.assertNotIn('Запросов к ИИ на сегодня', html)

    def test_task_cfg_carries_the_one_threshold(self):
        self.assertEqual(core.LIMIT_WARN_AT, 5)
        html = _page(self.client, self.problem)
        cfg = re.search(r'<script type="application/json" class="stol-cfg">(.*?)</script>', html, re.S)
        self.assertEqual(json.loads(cfg.group(1))['limitWarnAt'], core.LIMIT_WARN_AT)

    def test_chat_answer_carries_remaining(self):
        """Контракт, на который опирается скрипт: ответ чата несёт остаток."""
        self._spend(10)
        with self.settings(AI_FAKE_REPLY=json.dumps({'reply': 'Начните с MR = MC.'}, ensure_ascii=False)):
            resp = self.client.post(reverse('catalog:api_chat'),
                                    json.dumps({'problem_id': self.problem.pk, 'message': 'Как решать?'}),
                                    content_type='application/json')
        data = resp.json()
        self.assertIn('remaining', data)
        self.assertEqual(data['remaining'], 30 - 10 - 1)


def _feature(key):
    """Строка справочника `Feature` — в тестовой базе его заполняют сами тесты."""
    for order, (k, label, by) in enumerate(enrich_features.CATALOG_FEATURES):
        if k == key:
            return Feature.objects.get_or_create(key=key, defaults={
                'label': label, 'counted_by': by, 'order': order})[0]
    raise KeyError(key)


class CardFeaturesTests(TestCase):
    """Фаза 4: особенности задачи в строке свойств, «Теги · N» кнопкой."""

    def setUp(self):
        cache.clear()
        self.topic = make_topic('Монополия', is_canonical=True)
        self.problem = make_problem('Фирма выбирает цену. Firm chooses price.', topic=self.topic,
                                    title='Цена фирмы', features=['graph'])
        for key in ('на_английском', 'бизнесовое', 'с_реальной_олимпиады'):
            ProblemFeature.objects.create(problem=self.problem, feature=_feature(key), source='code')
        for name in ('монополия', 'эластичность'):
            self.problem.tags.add(Tag.objects.create(name=name, slug=name[:40], kind='canonical'))
        self.bare = make_problem('Задача без особенностей.', topic=self.topic, title='Без особенностей')

    def _words(self, problem):
        html = _page(self.client, problem)
        start = html.index('<div class="pp-sub-words">')
        return html, html[start:html.index('</div>', start)]

    def test_card_shows_canonical_features_as_filter_links(self):
        html, words = self._words(self.problem)
        links = dict((label, href) for href, label in re.findall(r'<a class="pp-w" href="([^"]+)">([^<]+)</a>', words))
        # Порядок — `Feature.order`: вид задачи, потом особенности; «с реальной олимпиады» скрыта.
        self.assertEqual(list(links), ['развёрнутая задача', 'бизнесовое', 'на английском'])
        self.assertIn('feature=', links['бизнесовое'])
        self.assertIn('feature=', links['на английском'])
        self.assertNotIn('с реальной олимпиады', words.lower())
        self.assertNotIn('есть график', html.lower())
        # Ссылка ведёт в каталог, где эта задача есть.
        listing = self.client.get(links['бизнесовое'].replace('&amp;', '&')).content.decode()
        self.assertIn('/catalog/problem/%d/' % self.problem.pk, listing)
        self.assertNotIn('/catalog/problem/%d/' % self.bare.pk, listing)

    def test_card_hidden_constant_is_the_one_place(self):
        self.assertEqual(enrich_features.CARD_HIDDEN, ('с_реальной_олимпиады',))

    def test_problem_without_features_has_only_kind(self):
        _html, words = self._words(self.bare)
        labels = re.findall(r'<a class="pp-w" href="[^"]+">([^<]+)</a>', words)
        self.assertEqual(labels, ['развёрнутая задача'])

    def test_features_cost_one_query_not_one_per_feature(self):
        _page(self.client, self.problem)          # прогрев кэшей страницы
        with CaptureQueriesContext(connection) as rich:
            _page(self.client, self.problem)
        own = [q['sql'] for q in rich.captured_queries if 'problemfeature' in q['sql'].lower()]
        self.assertEqual(len(own), 1, own)
        # Та же задача без особенностей — запросов ровно столько же: выборка одна
        # на задачу, а не по одной на особенность.
        ProblemFeature.objects.filter(problem=self.problem).delete()
        with CaptureQueriesContext(connection) as bare:
            _page(self.client, self.problem)
        self.assertEqual(len(rich.captured_queries), len(bare.captured_queries))

    def test_tags_are_a_button_and_a_hidden_list_below(self):
        html = _page(self.client, self.problem)
        self.assertIn('<button type="button" class="pp-tags-btn" aria-expanded="false" '
                      'aria-controls="pp-tags-list">Теги · 2</button>', html)
        self.assertNotIn('<details class="pp-tags"', html)
        start = html.index('<div class="pp-tag-list" id="pp-tags-list" hidden>')
        tag_list = html[start:html.index('</div>', start)]
        self.assertEqual(tag_list.count('class="pp pp--tag"'), 2)
        # Список — после строки свойств, а не внутри неё.
        self.assertLess(html.index('class="pp-tags-btn"'), start)
