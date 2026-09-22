"""Посадочная `/vp/`, вход в раздел и SEO (сессия 4, ADR 0127).

Нумерация `test_NN_…` — сценарии из задания сессии 4; остальные тесты — рядом. Числа на
странице проверяются ИЗМЕНЕНИЕМ данных: правим задания — число на экране следует за
ними, а не за шаблоном.
"""
import re
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.tests.test_no_slop import visible_text
from vp import landing, views
from vp.models import VPVariant
from vp.tests.helpers import make_published
from vp.tests.test_review import chain_word, make_review_variant, submit

User = get_user_model()

TITLE = re.compile(r'<title>(.*?)</title>', re.S)
NOINDEX = re.compile(r'<meta name="robots" content="[^"]*noindex')
ROW = re.compile(
    r'<tr data-block="(\w+)">\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*'
    r'<td class="is-num">(.*?)</td>\s*<td class="is-num">(.*?)</td>', re.S)
FOOT = re.compile(r'<tfoot>\s*<tr>\s*<td></td>\s*<td>Всего</td>\s*'
                  r'<td class="is-num">(.*?)</td>\s*<td class="is-num">(.*?)</td>', re.S)


def page(client, url='vp:index', *args):
    response = client.get(reverse(url, args=args))
    assert response.status_code == 200, response.status_code
    return response.content.decode()


def table_rows(html):
    """Строки таблицы блоков: [(блок, номера, название, заданий, баллов)]."""
    return ROW.findall(html)


def section(html, start, end):
    """Кусок разметки между двумя якорями (id секции) — чтобы искать только в нём."""
    return html.split(f'id="{start}"', 1)[1].split(f'id="{end}"', 1)[0]


def set_chain(variant, letters, tail):
    """Связная змейка из другого алфавита: ответ №N — `letters[N]` + `letters[N+1]` + хвост."""
    size = len(letters)
    for item in variant.items.filter(block='snake'):
        item.answer = letters[item.number % size] + letters[(item.number + 1) % size] + tail
        item.save()


class LandingBase(TestCase):
    def setUp(self):
        self.variant = make_published('vp-land')
        self.guest = Client()


class LandingTests(LandingBase):
    def test_01_guest_opens_the_landing_without_login(self):
        response = self.guest.get(reverse('vp:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'vp/index.html')
        self.assertEqual(reverse('vp:index'), '/vp/')

    def test_02_block_table_and_totals_follow_the_items_not_the_template(self):
        rows = table_rows(page(self.guest))
        self.assertEqual(
            [(b, r, c, t) for b, r, _, c, t in rows],
            [('snake', '1–30', '30', '60'), ('gapfill', '31–35', '5', '10'),
             ('multi', '36–40', '5', '15'), ('analytic', '41–42', '2', '6'),
             ('single', '43–44', '2', '9')])
        self.assertEqual(FOOT.search(page(self.guest)).groups(), ('44', '100'))

        # Портим данные: балл змейки, число заданий, время. Страница обязана последовать.
        first = self.variant.items.get(number=1)
        first.points = 3
        first.save()
        self.variant.items.get(number=44).delete()
        VPVariant.objects.filter(pk=self.variant.pk).update(duration_seconds=1500)
        html = page(self.guest)
        rows = {b: (r, c, t) for b, r, _, c, t in table_rows(html)}
        self.assertEqual(rows['snake'], ('1–30', '30', '61'))
        self.assertEqual(rows['single'], ('43', '1', '4'))
        self.assertEqual(FOOT.search(html).groups(), ('43', '96'))
        self.assertIn('43 задания за 25 минут, 96 баллов', html)
        self.assertNotIn('44 задания', html)
        self.assertNotIn('100 баллов', html)

    def test_facts_sentence_is_computed_from_the_data(self):
        html = page(self.guest)
        self.assertIn('Формат новый: 44 задания за 30 минут, 100 баллов, всё проверяется автоматически.', html)
        self.assertIn('1 тур появился в отборочном этапе впервые', html)

    def test_03_draft_is_hidden_from_a_guest_and_visible_to_staff(self):
        draft = make_published('vp-draft')
        draft.title = 'Черновик ВП для проверки'
        draft.is_published = False
        draft.save()
        self.assertNotContains(self.guest.get(reverse('vp:index')), 'Черновик ВП для проверки')
        staff = Client()
        staff.force_login(User.objects.create_user('vp_lstaff', password='p12345', is_staff=True))
        html = page(staff)
        self.assertIn('Черновик ВП для проверки', html)
        self.assertIn('Не опубликован', html)

    def test_numbers_on_the_page_do_not_depend_on_who_looks(self):
        """Черновик другой структуры не меняет числа страницы у персонала: они — из опубликованных."""
        draft = make_published('vp-draft2')
        draft.is_published = False
        draft.save()
        draft.items.filter(number__gt=30).delete()
        staff = Client()
        staff.force_login(User.objects.create_user('vp_lstaff2', password='p12345', is_staff=True))
        self.assertEqual(table_rows(page(staff)), table_rows(page(self.guest)))
        self.assertIn('44 задания за 30 минут', page(staff))

    def test_every_published_variant_has_a_go_button_to_its_intro(self):
        other = make_published('vp-11')
        other.grade_band = '11'
        other.title = 'Вариант для 11 класса'
        other.save()
        html = page(self.guest)
        for variant in (self.variant, other):
            self.assertIn(f'href="{reverse("vp:intro", args=[variant.slug])}"', html)
        self.assertEqual(html.count('>Пройти</a>'), 2)
        listing = section(html, 'vp-variants-h', 'vp-help-h')
        self.assertLess(listing.index('9–10 классы'), listing.index('11 класс'))
        self.assertIn('Демонстрационный · 2026', listing)        # чей вариант виден

    def test_empty_landing_is_honest_and_has_no_invented_numbers(self):
        VPVariant.objects.update(is_published=False)
        html = page(self.guest)
        self.assertIn('Опубликованных вариантов пока нет', html)
        self.assertIn('Если сайт не открывается', html)          # полезное остаётся
        for absent in ('vp-format-h', 'vp-scoring-h', 'vp-snake-h', 'Выбрать вариант'):
            self.assertNotIn(absent, html)
        self.assertNotRegex(html, r'\d+ задани')
        self.assertIn('Формат новый, всё проверяется автоматически.', html)

    def test_help_block_for_people_who_cannot_open_the_site(self):
        html = page(self.guest)
        self.assertIn('Если сайт не открывается', html)
        self.assertIn('VPN', html)
        self.assertIn('weconomics.ai', html)

    def test_no_promises_of_modes_that_do_not_exist_and_no_long_dash(self):
        """Тренировки блоками и бесконечной змейки пока нет — ни слова, ни кнопки на странице."""
        text = visible_text(page(self.guest))
        for promise in ('блоками', 'бесконечн', 'скоро', 'появится', 'в разработке', 'тренировк'):
            self.assertNotIn(promise, text.lower(), promise)
        self.assertNotIn('—', text)                              # правило сайта: длинного тире нет

    def test_order_of_sections_follows_the_brief(self):
        html = page(self.guest)
        anchors = ['vp-new-h', 'vp-format-h', 'vp-scoring-h', 'vp-snake-h', 'vp-variants-h', 'vp-help-h']
        positions = [html.index(f'id="{a}"') for a in anchors]
        self.assertEqual(positions, sorted(positions))


class TourDatesTests(LandingBase):
    def test_dates_come_from_config_not_from_the_template(self):
        self.assertIn('проходит 26 и 30 сентября 2026', page(self.guest))
        with mock.patch.object(views, 'TOUR_DATES', (date(2027, 10, 3), date(2027, 10, 10))):
            html = page(self.guest)
        self.assertIn('проходит 3 и 10 октября 2027', html)
        self.assertNotIn('сентября', html)

    def test_no_dates_no_phrase(self):
        with mock.patch.object(views, 'TOUR_DATES', ()):
            html = page(self.guest)
        self.assertNotIn(' и проходит ', html)
        self.assertIn('1 тур появился в отборочном этапе впервые.', html)

    def test_dates_text(self):
        self.assertEqual(landing.dates_text([date(2026, 9, 30), date(2026, 9, 26)]), '26 и 30 сентября 2026')
        self.assertEqual(landing.dates_text([date(2026, 9, 26)]), '26 сентября 2026')
        self.assertEqual(landing.dates_text([date(2026, 9, 26), date(2026, 9, 28), date(2026, 9, 30)]),
                         '26, 28 и 30 сентября 2026')
        self.assertEqual(landing.dates_text([date(2026, 9, 30), date(2026, 10, 2)]),
                         '30 сентября 2026 и 2 октября 2026')
        self.assertEqual(landing.dates_text([]), '')


class ClassesTests(LandingBase):
    def eleven(self, points_of_first=None):
        variant = make_published('vp-eleven')
        variant.grade_band = '11'
        variant.save()
        for number in (43, 44):
            item = variant.items.get(number=number)
            item.points = '4.5'                 # у 11 класса №43 и №44 по 4,5 — блок тот же, 9 баллов
            item.save()
        if points_of_first:
            item = variant.items.get(number=1)
            item.points = points_of_first
            item.save()
        return variant

    def test_same_displayed_format_is_one_table_without_class_labels(self):
        self.eleven()
        html = page(self.guest)
        self.assertEqual(html.count('class="vp-table vp-table--blocks"'), 1)
        self.assertEqual(section(html, 'vp-format-h', 'vp-scoring-h').count('<h3'), 0)

    def test_classes_that_differ_in_points_get_a_table_each(self):
        self.eleven(points_of_first=3)                # змейка 11 класса — 61 балл
        html = page(self.guest)
        block = section(html, 'vp-format-h', 'vp-scoring-h')
        self.assertEqual(block.count('class="vp-table vp-table--blocks"'), 2)
        self.assertIn('<h3 class="vp-h3">9–10 классы</h3>', block)
        self.assertIn('<h3 class="vp-h3">11 класс</h3>', block)
        self.assertEqual([r[4] for r in table_rows(block) if r[0] == 'snake'], ['60', '61'])
        rules = section(html, 'vp-scoring-h', 'vp-snake-h')
        self.assertEqual(rules.count('или полный балл, или ноль'), 2)
        # Когда формата два, общего «44 задания за 30 минут» на странице нет.
        self.assertIn('Формат новый, всё проверяется автоматически.', html)
        self.assertNotIn('44 задания за', html)


class DurationTests(LandingBase):
    def test_variants_that_differ_only_in_duration_share_a_table_but_not_the_minutes_claim(self):
        """Длительность в таблице не видна: две одинаковые таблицы были бы шумом. А «за 30 минут» на
        странице нет, раз минуты у вариантов разные."""
        other = make_published('vp-short')
        VPVariant.objects.filter(pk=other.pk).update(duration_seconds=1500)
        html = page(self.guest)
        self.assertEqual(html.count('class="vp-table vp-table--blocks"'), 1)
        self.assertIn('Формат новый, всё проверяется автоматически.', html)
        self.assertNotRegex(html, r'\d+ минут')
        VPVariant.objects.filter(pk=other.pk).update(duration_seconds=1800)
        self.assertIn('44 задания за 30 минут', page(self.guest))


class ScoringRulesTests(LandingBase):
    def test_three_rules_ranges_and_penalty_example_follow_the_data(self):
        html = page(self.guest)
        self.assertIn('Задания 1–35 и 43–44: или полный балл, или ноль.', html)
        self.assertIn('В заданиях 36–42 балл делится', html)
        self.assertIn('верный даёт +1,5, лишний отнимает 1.', html)          # для трёхбалльных
        self.assertIn('Отметить все варианты подряд не получится', html)
        for item in self.variant.items.filter(block__in=('multi', 'analytic')):
            item.points = 6
            item.save()
        html = page(self.guest)
        self.assertIn('верный даёт +3, лишний отнимает 2.', html)


class SnakeExampleTests(TestCase):
    def setUp(self):
        self.guest = Client()

    def chips(self, html):
        chain = html.split('class="vp-chain-demo"', 1)[1].split('</div>', 1)[0]
        return [re.sub(r'<[^>]+>', '', span) for span in re.findall(r'<span>(.*?)</span>', chain)]

    def test_example_is_a_real_chain_of_four_from_a_published_variant(self):
        make_review_variant('vp-snk')
        html = page(self.guest)
        self.assertEqual(self.chips(html), [chain_word(n) for n in (1, 2, 3, 4)])
        # Вторая буква выделена у всех, кроме последнего слова: с неё начнётся следующее.
        marks = re.findall(r'<b>(.)</b>', html.split('class="vp-chain-demo"', 1)[1].split('</div>', 1)[0])
        self.assertEqual(marks, [chain_word(n)[1] for n in (1, 2, 3)])
        self.assertIn('Так выглядит цепочка из 4 заданий варианта «Тестовый вариант»', html)

    def test_demonstration_variant_is_preferred_over_an_authored_one(self):
        """Пример открывает настоящие ответы: берём демоверсию, авторский вариант бережём."""
        author = make_review_variant('vp-author')
        author.source_kind = 'author'
        author.order = 0
        author.save()
        set_chain(author, 'жзиклмнопр', 'ыы')
        demo = make_review_variant('vp-demo')
        demo.order = 5
        demo.save()
        self.assertEqual(self.chips(page(self.guest)), [chain_word(n) for n in (1, 2, 3, 4)])
        VPVariant.objects.filter(pk=demo.pk).update(is_published=False)
        self.assertNotIn('абфъщ', ''.join(self.chips(page(self.guest))))       # теперь авторский

    def test_no_chain_in_the_data_no_example_but_the_rule_stays(self):
        variant = make_review_variant('vp-broken')
        variant.items.filter(block='snake').update(answer='ба')                # связки нигде нет
        html = page(self.guest)
        self.assertNotIn('class="vp-chain-demo"', html)
        self.assertIn('Что такое змейка', html)

    def test_draft_variants_never_feed_the_example(self):
        variant = make_review_variant('vp-draft-chain')
        variant.is_published = False
        variant.save()
        make_published('vp-plain')                                              # опубликован, но связки нет
        staff = Client()
        staff.force_login(User.objects.create_user('vp_snake_staff', password='p12345', is_staff=True))
        self.assertNotIn('class="vp-chain-demo"', page(staff))

    def test_marked_letter_is_the_second_letter_of_the_first_word(self):
        self.assertEqual(landing._marked('валютный курс', False),
                         {'before': 'в', 'mark': 'а', 'after': 'лютный курс'})
        self.assertEqual(landing._marked('ёж', False), {'before': 'ё', 'mark': 'ж', 'after': ''})
        self.assertEqual(landing._marked('ликвидность', True),
                         {'before': 'ликвидность', 'mark': '', 'after': ''})


class MenuTests(TestCase):
    def nav(self, client=None):
        response = (client or Client()).get(reverse('vp:index'))
        return response.context['nav_items']

    def test_04_menu_item_stands_after_olympiads_and_leads_to_vp(self):
        for user in (None,
                     User.objects.create_user('vp_menu_st', password='p12345', role='student'),
                     User.objects.create_user('vp_menu_te', password='p12345', role='teacher')):
            client = Client()
            if user:
                client.force_login(user)
            items = self.nav(client)
            labels = [i['label'] for i in items]
            self.assertEqual(labels[labels.index('Олимпиады') + 1], 'Тренажёр ВП', labels)
            item = items[labels.index('Тренажёр ВП')]
            self.assertEqual(item['url'], '/vp/')
            self.assertTrue(item['active'])                                    # мы на /vp/

    def test_menu_item_is_active_on_every_vp_screen_and_only_there(self):
        variant = make_published('vp-menu')
        client = Client()
        client.post(reverse('vp:start', args=['vp-menu']))
        for name, args in (('vp:intro', ['vp-menu']),):
            active = [i['label'] for i in client.get(reverse(name, args=args)).context['nav_items'] if i['active']]
            self.assertEqual(active, ['Тренажёр ВП'])
        catalog = client.get('/catalog/').context['nav_items']
        self.assertFalse([i for i in catalog if i['label'] == 'Тренажёр ВП' and i['active']])
        self.assertTrue(variant.is_published)


class SeoTests(LandingBase):
    def test_landing_title_answers_the_live_query(self):
        title = TITLE.search(page(self.guest)).group(1)
        for words in ('Высшая проба', '1 тур', 'экономик'):
            self.assertIn(words, title)
        self.assertNotIn('—', title)

    def test_the_word_demo_is_in_the_title_only_when_a_demo_variant_is_published(self):
        self.assertIn('демоверсия', TITLE.search(page(self.guest)).group(1))          # helpers: source_kind=demo
        VPVariant.objects.update(source_kind='author')
        title = TITLE.search(page(self.guest)).group(1)
        self.assertNotIn('демоверсия', title)
        self.assertIn('Высшая проба', title)

    def test_description_and_open_graph(self):
        html = page(self.guest)
        description = re.search(r'<meta name="description" content="(.*?)">', html, re.S).group(1)
        self.assertIn('Высшая проба', description)
        self.assertIn('1 тура', description)
        self.assertLessEqual(len(description), 200)
        self.assertIn(f'<meta property="og:description" content="{description}">', html)
        self.assertIn('<meta property="og:title" content="Высшая проба, 1 тур', html)

    def test_variant_page_has_its_own_title_and_description(self):
        html = page(self.guest, 'vp:intro', 'vp-land')
        title = TITLE.search(html).group(1)
        self.assertTrue(title.startswith('Тестовый вариант'), title)
        self.assertIn('вариант 1 тура «Высшая проба»', title)
        description = re.search(r'<meta name="description" content="(.*?)">', html, re.S).group(1)
        self.assertIn('9–10 классы', description)
        self.assertIn('2026', description)
        self.assertNotIn('—', description)                      # правило сайта: длинного тире нет
        self.assertNotIn('noindex', html)

    def test_05_sitemap_lists_the_landing_and_the_variants_but_no_personal_pages(self):
        draft = make_published('vp-hidden')
        draft.is_published = False
        draft.save()
        attempt = submit(self.variant, {}, session_key='sitemap-guest')
        client = Client()
        client.post(reverse('vp:start', args=['vp-land']))          # ещё и живая несданная попытка
        response = client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        urls = re.findall(r'<loc>(.*?)</loc>', response.content.decode())
        self.assertIn('https://testserver/vp/', urls)
        self.assertIn('https://testserver/vp/vp-land/', urls)
        self.assertNotIn('https://testserver/vp/vp-hidden/', urls)
        for url in urls:
            self.assertNotIn('/vp/a/', url)
            self.assertNotIn('/vp/r/', url)
        self.assertNotIn(attempt.public_code, response.content.decode())

    def test_06_result_and_attempt_pages_are_noindex_the_landing_is_not(self):
        attempt = submit(self.variant, {}, session_key='noindex-guest')
        owner = Client()
        owner.post(reverse('vp:start', args=['vp-land']))
        started = owner.session['vp_attempts'][0]
        for client in (Client(), owner):                                        # чужой и владелец
            html = client.get(reverse('vp:result', args=[attempt.public_code])).content.decode()
            self.assertRegex(html, NOINDEX)
        self.assertRegex(owner.get(reverse('vp:take', args=[started])).content.decode(), NOINDEX)
        for name, args in (('vp:index', []), ('vp:intro', ['vp-land'])):
            self.assertNotRegex(self.guest.get(reverse(name, args=args)).content.decode(), NOINDEX)

    def test_robots_closes_attempts_but_leaves_results_readable_for_their_noindex(self):
        text = self.guest.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /vp/a/', text)
        # Закрытый адрес индекс не запрещает, а лишь не даёт прочитать `noindex`: результат
        # открывается по ссылке, и бот обязан дойти до страницы.
        self.assertNotIn('/vp/r/', text)
        self.assertNotIn('Disallow: /vp/\n', text)


class PublicResultDoesNotNameTheOwnerTests(TestCase):
    """Пункт 7: тест сессии 2 в исходном смысле (полный вариант — в `test_take`)."""

    def test_07_signed_in_author_is_called_a_participant_by_everyone_else(self):
        variant = make_published('vp-priv')
        user = User.objects.create_user('vp_private_login', password='p12345',
                                        first_name='Мария', last_name='Тайная')
        attempt = submit(variant, {}, user=user, session_key='')
        for client in (Client(),):
            html = client.get(reverse('vp:result', args=[attempt.public_code])).content.decode()
            for private in ('vp_private_login', 'Мария', 'Тайная'):
                self.assertNotIn(private, html)
            self.assertIn('Участник', html)
