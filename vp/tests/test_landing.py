"""Посадочная `/vp/`, вход в раздел и SEO (сессия 4, ADR 0127; сессия 5 — редизайн).

Нумерация `test_NN_…` — сценарии из задания сессии 4; остальные тесты — рядом. Числа на
странице проверяются ИЗМЕНЕНИЕМ данных: правим задания — число на экране следует за
ними, а не за шаблоном.

⚠️ С 22.09.2026 посадочная — три зоны на один экран, а формат и правила живут в
ОКНЕ «Правила и формат» (`vp/_rules.html`). Разметка окна лежит в HTML страницы,
поэтому таблица блоков ищется там же, где раньше, — просто внутри окна. Список
вариантов уехал на `/vp/variants/`, и его проверяет `test_variants`.
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


def rules(html):
    """Содержимое окна «Правила и формат» — там живут формат, баллы и ссылки."""
    return html.split('id="vp-rules-cont"', 1)[1]


#: ⚠️ Куски ищутся по РАЗМЕТКЕ, а не по имени класса: стили страницы лежат в том
#: же HTML, и `vp-land-facts` нашлось бы в `<style>` даже на пустой странице.
HERO_OPEN = 'class="vp-land-card vp-land-hero"'
BOARD_OPEN = 'class="vp-land-card vp-land-board"'
FACTS = 'aria-label="Формат варианта"'


def hero(html):
    """Зона A: тур, плитки фактов, змейка, кнопки."""
    return html.split(HERO_OPEN, 1)[1].split(BOARD_OPEN, 1)[0]


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
        rows = table_rows(rules(page(self.guest)))
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
        rows = {b: (r, c, t) for b, r, _, c, t in table_rows(rules(html))}
        self.assertEqual(rows['snake'], ('1–30', '30', '61'))
        self.assertEqual(rows['single'], ('43', '1', '4'))
        self.assertEqual(FOOT.search(rules(html)).groups(), ('43', '96'))
        self.assertIn('43 задания, 25 минут, 96 баллов', html)
        self.assertNotIn('44 задания', html)
        self.assertNotIn('100 баллов', html)

    def test_facts_tiles_are_computed_from_the_data(self):
        """Плитки зоны «тур»: число, минуты, баллы и дни — из данных, не из шаблона."""
        block = hero(page(self.guest))
        self.assertIn('<b>44</b><span>задания</span>', block)
        self.assertIn('<b>30</b><span>минут</span>', block)
        self.assertIn('<b>100</b><span>баллов</span>', block)
        self.assertIn('<b>26 и 30 сент.</b><span>дни тура</span>', block)

    def test_three_zones_are_on_the_page(self):
        """Тур, таблица лучших попыток и полоса «моё» — три зоны экрана."""
        html = page(self.guest)
        for marker in (HERO_OPEN, BOARD_OPEN, 'class="vp-land-band"'):
            self.assertIn(marker, html)
        self.assertIn('Лучшие попытки', html)

    def test_choose_variant_leads_to_the_variants_screen(self):
        """Список вариантов уехал: посадочная только ведёт на него."""
        html = page(self.guest)
        self.assertIn(f'href="{reverse("vp:variants")}"', html)
        self.assertIn('Выбрать вариант', html)
        # Карточек вариантов на посадочной больше нет.
        self.assertNotIn(f'href="{reverse("vp:intro", args=["vp-land"])}"', html)

    def test_rules_dialog_holds_the_format_and_all_six_sections(self):
        html = page(self.guest)
        self.assertIn('<dialog class="vp-rules" id="vp-rules"', html)
        self.assertIn('class="vp-table vp-table--blocks"', rules(html))
        for anchor in ('vp-r-format', 'vp-r-score', 'vp-r-snake',
                       'vp-r-board', 'vp-r-tour', 'vp-r-vpn'):
            self.assertIn(f'id="{anchor}"', html, anchor)

    def test_hse_materials_link_is_on_the_page_and_in_the_rules(self):
        html = page(self.guest)
        self.assertEqual(html.count('https://olymp.hse.ru/mmo/materials-eco'), 2)

    def test_source_links_in_the_rules_follow_the_data(self):
        """Ссылок источников ровно столько, сколько РАЗНЫХ источников у опубликованных."""
        self.assertEqual(self._source_links(), 0)                # у фикстуры источника нет

        VPVariant.objects.filter(pk=self.variant.pk).update(
            source_label='Олмат', source_url='https://t.me/vsosh_aa_bot')
        self.assertEqual(self._source_links(), 1)

        second = make_published('vp-second')
        VPVariant.objects.filter(pk=second.pk).update(
            source_label='Олмат', source_url='https://t.me/vsosh_aa_bot')
        self.assertEqual(self._source_links(), 1)                # тот же источник — одна ссылка

        third = make_published('vp-third')
        VPVariant.objects.filter(pk=third.pk).update(
            source_label='Другой сборник', source_url='https://example.org/econ')
        self.assertEqual(self._source_links(), 2)

    def _source_links(self):
        block = rules(page(self.guest)).split('id="vp-r-tour"', 1)[1].split('</section>', 1)[0]
        # Ссылка ВШЭ стоит всегда и источником не является.
        return block.count('↗') - 1

    def test_empty_landing_is_honest_and_has_no_invented_numbers(self):
        VPVariant.objects.update(is_published=False)
        html = page(self.guest)
        self.assertIn('Если сайт не открывается', html)          # полезное остаётся
        self.assertNotIn(FACTS, html)
        self.assertNotIn('class="vp-table vp-table--blocks"', html)
        self.assertNotRegex(hero(html), r'\d+ задани')

    def test_help_block_for_people_who_cannot_open_the_site(self):
        html = page(self.guest)
        self.assertIn('Если сайт не открывается', html)
        self.assertIn('VPN', html)
        self.assertIn('weconomics.ai', html)

    def test_no_promises_of_modes_that_do_not_exist_and_no_long_dash(self):
        """Тренировки блоками и бесконечной змейки пока нет — ни слова, ни кнопки на странице.

        «Тренировка» как режим НЕ ищется: с 22.09 это законное слово таблицы
        (повторная попытка — тренировка). Ищутся именно обещанные режимы.
        """
        text = visible_text(page(self.guest))
        for promise in ('блоками', 'бесконечн', 'скоро', 'появится', 'в разработке'):
            self.assertNotIn(promise, text.lower(), promise)
        self.assertNotIn('—', text)                              # правило сайта: длинного тире нет
        self.assertNotIn('забег', text.lower())                  # слово раздела — «попытка»

    def test_no_page_promises_registration_is_not_needed(self):
        self.assertNotIn('Регистрация не нужна', page(self.guest))

    def test_guest_band_invites_to_register_with_a_way_back(self):
        html = page(self.guest)
        self.assertIn('/register/?next=%2Fvp%2F', html)
        self.assertIn('/login/?next=%2Fvp%2F', html)
        self.assertIn('Чтобы пройти вариант, нужна короткая бесплатная регистрация', html)


class TourDatesTests(LandingBase):
    def test_dates_come_from_config_not_from_the_template(self):
        self.assertIn('26 и 30 сентября 2026', page(self.guest))
        with mock.patch.object(views, 'TOUR_DATES', (date(2027, 10, 3), date(2027, 10, 10))):
            html = page(self.guest)
        self.assertIn('3 и 10 октября 2027', html)
        self.assertIn('3 и 10 окт.', html)
        self.assertNotIn('сентября', html)

    def test_no_dates_no_phrase_and_no_tile(self):
        with mock.patch.object(views, 'TOUR_DATES', ()):
            html = page(self.guest)
        self.assertNotIn('дни тура', html)
        self.assertIn('1 тур появился в отборочном этапе впервые.', rules(html))
        # Остальные три плитки на месте: дат нет, формат есть.
        self.assertIn('<b>44</b>', hero(html))

    def test_dates_short(self):
        self.assertEqual(landing.dates_short([date(2026, 9, 30), date(2026, 9, 26)]), '26 и 30 сент.')
        self.assertEqual(landing.dates_short([date(2026, 9, 26)]), '26 сент.')
        self.assertEqual(landing.dates_short([date(2026, 5, 3)]), '3 мая')
        self.assertEqual(landing.dates_short([date(2026, 9, 30), date(2026, 10, 2)]),
                         '30 сент. и 2 окт.')
        self.assertEqual(landing.dates_short([]), '')

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
        html = rules(page(self.guest))
        self.assertEqual(html.count('class="vp-table vp-table--blocks"'), 1)
        self.assertEqual(html.count('class="vp-rsec-h4"'), 0)

    def test_classes_that_differ_in_points_get_a_table_each(self):
        self.eleven(points_of_first=3)                # змейка 11 класса — 61 балл
        html = page(self.guest)
        block = section(rules(html), 'vp-r-format', 'vp-r-score')
        self.assertEqual(block.count('class="vp-table vp-table--blocks"'), 2)
        self.assertIn('<h4 class="vp-rsec-h4">9–10 классы</h4>', block)
        self.assertIn('<h4 class="vp-rsec-h4">11 класс</h4>', block)
        self.assertEqual([r[4] for r in table_rows(block) if r[0] == 'snake'], ['60', '61'])
        scoring = section(rules(html), 'vp-r-score', 'vp-r-snake')
        self.assertEqual(scoring.count('или полный балл, или ноль'), 2)
        # Когда формата два, плиток фактов и общего «44 задания» на странице нет.
        self.assertNotIn(FACTS, html)
        self.assertIn('Формат различается по классам', rules(html))


class DurationTests(LandingBase):
    def test_variants_that_differ_only_in_duration_share_a_table_but_not_the_minutes_claim(self):
        """Длительность в таблице не видна: две одинаковые таблицы были бы шумом. А «за 30 минут» на
        странице нет, раз минуты у вариантов разные."""
        other = make_published('vp-short')
        VPVariant.objects.filter(pk=other.pk).update(duration_seconds=1500)
        html = page(self.guest)
        self.assertEqual(rules(html).count('class="vp-table vp-table--blocks"'), 1)
        self.assertNotIn(FACTS, html)
        self.assertNotRegex(hero(html), r'\d+ минут')
        VPVariant.objects.filter(pk=other.pk).update(duration_seconds=1800)
        self.assertIn('44 задания, 30 минут, 100 баллов', page(self.guest))


class ScoringRulesTests(LandingBase):
    def test_three_rules_ranges_and_penalty_example_follow_the_data(self):
        html = rules(page(self.guest))
        self.assertIn('Задания 1–35 и 43–44: или полный балл, или ноль.', html)
        self.assertIn('В заданиях 36–42 балл делится', html)
        self.assertIn('верный даёт +1,5, лишний отнимает 1.', html)          # для трёхбалльных
        self.assertIn('Отметить все варианты подряд не получится', html)
        for item in self.variant.items.filter(block__in=('multi', 'analytic')):
            item.points = 6
            item.save()
        html = rules(page(self.guest))
        self.assertIn('верный даёт +3, лишний отнимает 2.', html)


class SnakeExampleTests(TestCase):
    def setUp(self):
        self.guest = Client()

    def chips(self, html):
        chain = html.split('class="vp-chain"', 1)[1].split('</div>', 1)[0]
        return [re.sub(r'<[^>]+>', '', span) for span in re.findall(r'<span>(.*?)</span>', chain)]

    def test_example_is_a_real_chain_of_four_from_a_published_variant(self):
        make_review_variant('vp-snk')
        html = page(self.guest)
        self.assertEqual(self.chips(html), [chain_word(n) for n in (1, 2, 3, 4)])
        # Вторая буква выделена у всех, кроме последнего слова: с неё начнётся следующее.
        marks = re.findall(r'<b>(.)</b>', html.split('class="vp-chain"', 1)[1].split('</div>', 1)[0])
        self.assertEqual(marks, [chain_word(n)[1] for n in (1, 2, 3)])
        # Подпись честно называет вариант примера — и на странице, и в окне правил.
        self.assertIn('пример из варианта «Тестовый вариант»', html)
        self.assertIn('Цепочка из варианта «Тестовый вариант».', html)

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
        self.assertNotIn('class="vp-chain"', html)
        self.assertIn('Что такое змейка', html)

    def test_draft_variants_never_feed_the_example(self):
        variant = make_review_variant('vp-draft-chain')
        variant.is_published = False
        variant.save()
        make_published('vp-plain')                                              # опубликован, но связки нет
        staff = Client()
        staff.force_login(User.objects.create_user('vp_snake_staff', password='p12345', is_staff=True))
        self.assertNotIn('class="vp-chain"', page(staff))

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
        client.force_login(User.objects.create_user('vp_sitemap', password='p12345'))
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
        owner.force_login(User.objects.create_user('vp_noindex', password='p12345'))
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
