# -*- coding: utf-8 -*-
"""Онбординг, раунд 3 (29.10.2026): роль без чипов, пять логотипов целей без плашек.

Решение владельца «у всех пяти целей логотип, без плашек» записано в Notion 29.10;
холст поправлен, снимки макета — нет, поэтому правда здесь, а не в `shots/`.
"""
import re
from pathlib import Path

from django.conf import settings

from problems.models_platform import UserProfile
from problems.tests.test_onboarding import OnboardingBase, main_html

CSS = Path(settings.BASE_DIR) / 'static' / 'onboarding' / 'onboarding.css'
LOGOS = Path(settings.BASE_DIR) / 'static' / 'onboarding' / 'logos'


def plates(html):
    """Содержимое каждой `.ob-plate` шага целей, по порядку плиток."""
    return re.findall(r'<span class="ob-plate[^"]*" aria-hidden="true">(.*?)</span>\n', html, re.S)


def css_rule(selector):
    css = CSS.read_text(encoding='utf-8')
    match = re.search(r'^' + re.escape(selector) + r' \{([^}]*)\}', css, re.M)
    return match.group(1) if match else ''


class RoleTilesTests(OnboardingBase):
    def test_role_tile_is_icon_name_and_mark_only(self):
        html = main_html(self.client.get('/welcome/role/'))
        for chip in ('Wecon Rush', 'домашки', 'PDF и TeX', 'туры', 'ob-role-chips', 'k-chip'):
            self.assertNotIn(chip, html)
        self.assertEqual(html.count('class="ob-role-ico"'), 2)
        self.assertEqual(html.count('class="ob-mark"'), 2)

    def test_role_tile_is_about_168px_high(self):
        self.assertIn('min-height: 168px', css_rule('.ob-role .k-tile'))


class GoalLogosTests(OnboardingBase):
    def goals_html(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(role='student', grade='10',
                                                              level='basic')
        return main_html(self.client.get('/welcome/goals/'))

    def test_five_logos_one_per_goal(self):
        found = plates(self.goals_html())
        self.assertEqual(len(found), 5)
        for plate in found:
            self.assertRegex(plate, r'<img |<svg ')
        vsosh, listed, international, knowledge, undecided = found
        self.assertIn('vsosh_econ_top.png', vsosh)
        self.assertIn('vp_logo.png', listed)
        self.assertIn('ranepa_mark.png', listed)       # кружки на «Перечневых» остались
        self.assertIn('nes_mark.png', listed)
        self.assertIn('ieo_mark.png', international)
        self.assertIn('weconomics_w.svg', knowledge)
        for logo in ('vsosh_econ_top.png', 'vp_logo.png', 'ieo_mark.png', 'ranepa_mark.png'):
            self.assertIn(logo, undecided)               # веер из четырёх
        self.assertEqual(undecided.count('<img '), 4)
        for name in ('vsosh_econ_top.png', 'vp_logo.png', 'ieo_mark.png', 'ranepa_mark.png',
                     'nes_mark.png', 'weconomics_w.svg'):
            self.assertTrue((LOGOS / name).exists(), name)

    def test_no_white_plate_and_no_supply_demand_picture(self):
        html = self.goals_html()
        self.assertNotIn('ob-plate--draw', html)
        self.assertNotIn('M9 7c8 3 17 11 27 22', html)    # кривая «спрос-предложение»
        self.assertNotIn('stroke-dasharray="3 4"', html)  # пунктирный «?»
        plate = css_rule('.ob-plate')
        self.assertNotIn('background', plate)
        self.assertNotIn('border', plate)
        self.assertIn('width: 104px', plate)
        self.assertIn('height: 64px', plate)
        css = CSS.read_text(encoding='utf-8')
        self.assertNotIn('#ffffff', ''.join(re.findall(r'\.ob-plate[^{]*\{[^}]*\}', css)))
        self.assertIn('background: var(--surface)', css_rule('.ob-plate-badges span'))

    def test_dark_theme_pad_only_under_olympiad_logos(self):
        pad = css_rule('[data-theme="dark"] .ob-plate--olymp')
        self.assertIn('background: var(--brand-cream)', pad)
        self.assertIn('border-radius: 10px', pad)
        self.assertIn('padding: 6px', pad)
        html = self.goals_html()
        self.assertEqual(html.count('ob-plate--olymp'), 3)
        self.assertEqual(html.count('ob-plate ob-plate--mark'), 1)
        self.assertEqual(html.count('ob-plate ob-plate--fan'), 1)

    def test_fan_is_pale_and_grey(self):
        fan = css_rule('.ob-plate--fan img')
        self.assertIn('filter: grayscale(1)', fan)
        self.assertIn('opacity: .5', fan)
        self.assertIn('opacity: .75', css_rule('.ob-t:hover .ob-plate--fan img'))
