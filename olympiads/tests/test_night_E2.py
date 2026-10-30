"""Ночь 30.10, Э2: страница олимпиады по макетам Main, Empty, MainPhone."""
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from olympiads import navigator as nav

from . import night_fixtures as fx


def panels_after_rows(html):
    """[(ключ клетки строки, ключи панелей сразу под ней)] — порядок таблицы."""
    desk = html.split('class="om-desk"', 1)[1].split('class="om-phone"', 1)[0]
    out = []
    for row in re.split(r'<tr>\s*<td class="om-ys">', desk)[1:]:
        cells = re.findall(r'data-open="(c\d+)"', row.split('</tr>', 1)[0])
        panels = re.findall(r'data-panel="(c\d+)"', row)
        out.append((cells, panels))
    return out


@override_settings(OLYMPIADS_PUBLIC=True)
class DetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp, cls.final, cls.kits = fx.mini_vsosh()
        cls.empty = fx.olympiad('empty', manual_rank=5)
        cls.hidden = fx.olympiad('hid', is_published=False)
        cls.stub = fx.olympiad('stub', is_placeholder=True)

    def get(self, slug='vs', **params):
        return self.client.get(reverse('olympiads:detail', args=[slug]), params)

    def test_visible_200_hidden_and_stub_404(self):
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.get('empty').status_code, 200)
        self.assertEqual(self.get('hid').status_code, 404)
        self.assertEqual(self.get('stub').status_code, 404)

    def test_cells_on_page_equal_navigator_cells(self):
        html = self.get(all='1').content.decode()
        desk = html.split('class="om-desk"', 1)[1].split('class="om-phone"', 1)[0]
        page = nav.olympiad_page(self.olymp)
        keys = sorted(c['key'] for g in page['grids'] for c in g['cells'])
        self.assertEqual(sorted(set(re.findall(r'data-open="(c\d+)"', desk))), keys)
        self.assertEqual(sorted(re.findall(r'data-panel="(c\d+)"', desk)), keys)

    def test_ten_seasons_and_more_button(self):
        html = self.get().content.decode()
        self.assertIn('Ещё 21 сезон · с 1995/96', html)
        self.assertIn('data-more hidden', html)

    def test_open_without_js_renders_panel_under_its_row(self):
        page = nav.olympiad_page(self.olymp)
        grid = [g for g in page['grids'] if g['code'] == 'final'][0]
        row = [r for r in grid['rows'] if r['label'] == '2024/25'][0]
        key = row['cells'][2]['key']
        html = self.get(open=key).content.decode()
        self.assertRegex(html, r'data-panel="%s"(?![^>]*hidden)' % key)
        for cells, panels in panels_after_rows(html):
            if key in cells:
                self.assertIn(key, panels)
                self.assertEqual(sorted(cells), sorted(panels))
                break
        else:
            self.fail('строка с клеткой не найдена')

    def test_open_cell_in_old_season_shows_all_rows(self):
        page = nav.olympiad_page(self.olymp)
        grid = [g for g in page['grids'] if g['code'] == 'final'][0]
        old = grid['rows'][-1]['cells'][0]['key']
        html = self.get(open=old).content.decode()
        self.assertNotIn('data-more hidden', html)

    def test_phone_tab_shows_shared_variant_in_10_and_11(self):
        page = nav.olympiad_page(self.olymp)
        grid = [g for g in page['grids'] if g['code'] == 'final'][0]
        shared = [r for r in grid['rows'] if r['label'] == '2018/19'][0]['cells'][1]
        self.assertEqual(shared['grades'], [10, 11])
        for grade in (10, 11):
            html = self.get(grade=grade).content.decode()
            phone = html.split('class="om-phone"', 1)[1]
            self.assertIn('data-open="%s"' % shared['key'], phone, grade)
        phone9 = self.get(grade=9).content.decode().split('class="om-phone"', 1)[1]
        self.assertNotIn('data-open="%s"' % shared['key'], phone9)

    def test_empty_olympiad_has_empty_state_and_no_table(self):
        html = self.get('empty').content.decode()
        self.assertIn('Заданий прошлых лет пока нет', html)
        self.assertNotIn('class="om-grid', html)

    def test_panel_buttons_lead_to_tour_entry(self):
        variant = self.kits['2025/26'][5]
        html = self.get().content.decode()
        intro = reverse('olympiads:training_intro', args=['vs', variant.pk])
        self.assertIn(intro + '?mode=timed', html)
        self.assertIn(intro + '?mode=free', html)

    def test_existing_routes_still_work(self):
        self.assertEqual(self.client.get(reverse('olympiads:calendar')).status_code, 200)
        self.assertEqual(self.client.get(reverse('olympiads:compare'),
                                         {'slugs': 'vs'}).status_code, 200)

    def test_no_numbers_in_template_without_data(self):
        # Блоков без данных нет: у фикстуры нет льгот и проходных баллов.
        html = self.get().content.decode()
        self.assertNotIn('Что это даёт</h2>', html)
        self.assertNotIn('Проходной балл на заключительный этап', html)
