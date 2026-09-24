"""Полировка «Стола» 24.09.2026 (журнал `claude/JOURNAL_STOL_POLISH_20260924.md`).

Решения владельца 24.09 (Notion «Решения»): совет в помощи один раз, потом ⓘ;
строка лимита ИИ только при малом остатке; особенности задачи на карточке;
фокус с панелями поверх; строки выдачи с метками у названия. Здесь — то, что
видно по разметке сервера; поведение в браузере — `stol_polish_runner.mjs`.
"""
import re

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from problems.models import Hint
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
