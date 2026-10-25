"""Раздел переключён на 2 тур, 1 тур скрыт (решение владельца 24.10.2026).

Видимость — `vp/visibility.py`, настройки — `vp/config.py`: `CURRENT_TOUR = 2`,
`VISIBLE_TOURS = (2,)`. Данные 1 тура не тронуты: старые результаты открываются,
начатая попытка доступна владельцу, в «Моих попытках» она с пометкой «1 тур».
"""
import json
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import board, config
from vp.blocks import NUMBER_RULE
from vp.models import VPAttempt, VPVariant
from vp.tests.helpers import load_demo, make_published, perfect_raw

User = get_user_model()
TOUR1_SLUG = 'vp-1tur-test'


def body(html):
    """Страница без общих стилей сайта: в них слова и числа из комментариев."""
    return html.split('</style>')[-1]


class SectionBase(TestCase):
    def setUp(self):
        self.demos = {band: load_demo(band) for band in ('9', '10', '11')}
        self.tour1 = make_published(TOUR1_SLUG)          # 1 тур, опубликован, но скрыт
        self.tour1.title = 'Вариант первого тура для проверки'
        self.tour1.save()
        self.guest = Client()
        self.user = User.objects.create_user('vp_s', password='p12345')
        self.client.force_login(self.user)
        self.staff = Client()
        self.staff.force_login(User.objects.create_user('vp_staff', password='p12345', is_staff=True))

    def finish(self, client, variant, perfect=True, timer=True):
        client.post(reverse('vp:start', args=[variant.slug]), {'with_timer': '1' if timer else '0'})
        attempt = VPAttempt.objects.filter(variant=variant).order_by('-id').first()
        if perfect:
            client.post(reverse('vp:save', args=[attempt.public_code]),
                        json.dumps({'answers': [{'item': i.number, 'raw': perfect_raw(i)}
                                                for i in variant.items.all()]}),
                        content_type='application/json')
        client.post(reverse('vp:finish', args=[attempt.public_code]))
        attempt.refresh_from_db()
        return attempt


class ConfigTests(TestCase):
    def test_settings_of_the_season(self):
        self.assertEqual((config.CURRENT_TOUR, config.VISIBLE_TOURS), (2, (2,)))
        self.assertEqual(config.TOUR_DATES[2], ('range', (date(2026, 11, 13), date(2026, 11, 22))))
        self.assertEqual(config.bands(2), (('9', '9 класс'), ('10', '10 класс'), ('11', '11 класс')))
        self.assertEqual(config.NEW_BADGE_UNTIL, date(2026, 11, 13))


class LandingTour2Tests(SectionBase):
    def test_landing_is_about_tour_2(self):
        html = self.guest.get(reverse('vp:index')).content.decode()
        self.assertIn('<title>Высшая проба, 2 тур', html)
        self.assertIn('Отборочный этап · 2 тур', html)
        self.assertIn('тренажёр второго тура', html)
        self.assertIn('с 13 по 22 ноября 2026', html)
        hero = html.split('aria-label="Формат варианта"', 1)[1].split('class="vp-land-cta"', 1)[0]
        self.assertIn('<b>17–18</b><span>заданий</span>', hero)
        self.assertIn('<b>70</b><span>минут</span>', hero)
        self.assertIn('<b>100</b><span>баллов</span>', hero)
        self.assertIn('<b>13–22 нояб.</b><span>дни тура</span>', hero)
        self.assertNotIn(self.tour1.title, html)
        self.assertNotIn('1 тур', body(html))

    def test_two_format_tables_and_rules_without_snake(self):
        html = self.guest.get(reverse('vp:index')).content.decode()
        rules = html.split('id="vp-rules-cont"', 1)[1]
        self.assertIn('<h4 class="vp-rsec-h4">9 класс</h4>', rules)
        self.assertIn('<h4 class="vp-rsec-h4">10 класс и 11 класс</h4>', rules)
        self.assertNotIn('змейк', rules.lower())
        self.assertNotIn('data-sec="vp-r-snake"', html)
        self.assertIn(NUMBER_RULE, rules)
        self.assertIn('Ответ в неверном формате – 0 баллов, как на туре', rules)
        self.assertIn('на туре идёт запись экрана и камеры, её проверяют после тура', rules)
        self.assertIn('https://olymp.hse.ru/mmo/materials-eco', rules)
        self.assertIn('каждый лишний отнимает', rules)            # штраф в тестах
        self.assertIn('Штрафа за неверные нет', rules)              # пропуски и соотнесение

    def test_board_tabs_per_class(self):
        html = self.guest.get(reverse('vp:index')).content.decode()
        for band in ('9', '10', '11'):
            self.assertIn(f'data-board-tab="{band}"', html)
        self.assertIn('data-board-tab="9" aria-selected="true"', html)   # гостю — 9 класс

    def test_board_tab_of_my_last_attempt_and_separate_tables(self):
        other = Client()
        other.force_login(User.objects.create_user('vp_s9', password='p12345'))
        self.finish(other, self.demos['9'])
        self.finish(self.client, self.demos['10'])
        self.assertEqual([r['name'] for r in board.rows(2, '10')], ['vp_s'])
        self.assertEqual([r['name'] for r in board.rows(2, '9')], ['vp_s9'])
        html = self.client.get(reverse('vp:index')).content.decode()
        self.assertIn('data-board-tab="10" aria-selected="true"', html)
        panel10 = html.split('data-board-panel="10"', 1)[1].split('data-board-panel=', 1)[0]
        self.assertIn('vp_s<', panel10)
        self.assertNotIn('vp_s9', panel10)
        self.assertRegex(html, r'data-board-panel="9"[^>]* hidden')
        # Без JS вкладка — ссылка `?board=`.
        html9 = self.client.get(reverse('vp:index') + '?board=9').content.decode()
        self.assertIn('data-board-tab="9" aria-selected="true"', html9)

    def test_tour1_attempts_are_not_in_the_tour2_tables(self):
        attempt = VPAttempt.objects.create(
            variant=self.tour1, user=self.user, public_code='old-t1', is_ranked=True,
            submitted_at=self.tour1.created_at, score=90)
        self.assertEqual(board.rows(2, '11'), [])
        self.assertIsNone(board.my_best(self.user)[0])
        self.assertEqual(board.place_of(attempt), 1)                 # таблица 1 тура жива в данных


class VisibilityTests(SectionBase):
    def test_variants_screen_shows_three_demos_and_no_tour1(self):
        response = self.guest.get(reverse('vp:variants'))
        html = response.content.decode()
        self.assertEqual([b['code'] for b in response.context['bands']], ['9', '10', '11'])
        self.assertEqual(sum(b['count'] for b in response.context['bands']), 3)
        self.assertNotIn(TOUR1_SLUG, html)
        for band in ('10', '11'):
            page = self.guest.get(reverse('vp:variants') + f'?band={band}').content.decode()
            self.assertIn(f'vp-2tur-2026-demo-{band}', page)
            self.assertNotIn(TOUR1_SLUG, page)
        # Персонал тоже видит только туры раздела (черновики — да, скрытый тур — нет).
        self.assertNotIn(TOUR1_SLUG, self.staff.get(reverse('vp:variants') + '?band=11')
                         .content.decode())

    def test_intro_and_start_of_hidden_tour(self):
        url = reverse('vp:intro', args=[TOUR1_SLUG])
        self.assertEqual(self.guest.get(url).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.staff.get(url).status_code, 200)
        response = self.client.post(reverse('vp:start', args=[TOUR1_SLUG]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(VPAttempt.objects.filter(variant=self.tour1).exists())
        self.assertEqual(self.client.get(reverse('vp:intro', args=['vp-2tur-2026-demo-9']))
                         .status_code, 200)

    def test_old_tour1_result_and_unfinished_attempt_still_open(self):
        done = VPAttempt.objects.create(variant=self.tour1, user=self.user, public_code='t1-done',
                                        submitted_at=self.tour1.created_at, score=40, max_score=100)
        live = VPAttempt.objects.create(variant=self.tour1, user=self.user, public_code='t1-live')
        result = reverse('vp:result', args=[done.public_code])
        self.assertEqual(self.client.get(result).status_code, 200)
        self.assertEqual(self.guest.get(result).status_code, 200)
        self.assertEqual(self.client.get(reverse('vp:take', args=[live.public_code])).status_code, 200)
        my = self.client.get(reverse('vp:my')).content.decode()
        self.assertIn('<span class="vp-tour-tag">1 тур</span>', my)
        # Чужому кнопки «Пройти этот же вариант» к скрытому туру нет.
        self.assertNotIn(reverse('vp:intro', args=[TOUR1_SLUG]), self.guest.get(result).content.decode())

    def test_sitemap_lists_only_visible_variants(self):
        xml = self.guest.get('/sitemap.xml').content.decode()
        self.assertNotIn('vp-1tur-', xml)
        for band in ('9', '10', '11'):
            self.assertIn(f'/vp/vp-2tur-2026-demo-{band}/', xml)

    def test_seo_is_about_tour_2(self):
        html = self.guest.get(reverse('vp:variants')).content.decode()
        self.assertIn('Варианты 2 тура «Высшей пробы»', html)
        intro = self.guest.get(reverse('vp:intro', args=['vp-2tur-2026-demo-10'])).content.decode()
        self.assertIn('вариант 2 тура «Высшая проба»', intro)

    def test_making_tour1_visible_again_is_one_setting(self):
        """Архив 1 тура вернётся одной настройкой: варианты снова видны и открываются."""
        with mock.patch.object(config, 'VISIBLE_TOURS', (1, 2)):
            self.assertEqual(self.guest.get(reverse('vp:intro', args=[TOUR1_SLUG])).status_code, 200)
            xml = self.guest.get('/sitemap.xml').content.decode()
            self.assertIn(f'/vp/{TOUR1_SLUG}/', xml)


class IntroTour2Tests(SectionBase):
    def test_intro_explains_number_format_and_shares(self):
        html = self.guest.get(reverse('vp:intro', args=['vp-2tur-2026-demo-10'])).content.decode()
        self.assertIn('Отборочный этап · 2 тур', html)
        self.assertIn('Ответ-число в неверном формате – 0 баллов, как на туре.', html)
        self.assertIn(NUMBER_RULE, html)
        self.assertIn('штрафа нет', html)
        self.assertNotIn('Что такое змейка', html)
        self.assertEqual(VPVariant.objects.get(slug='vp-2tur-2026-demo-10').duration_seconds, 4200)
