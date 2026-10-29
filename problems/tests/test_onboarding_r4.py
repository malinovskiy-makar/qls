# -*- coding: utf-8 -*-
"""Онбординг, раунд 4 (29.10.2026): экран сборки плана и фирменная загрузка W.

- три пустых квадрата («заготовки карточек») после строк убраны: три строки →
  галочка → сразу план;
- вместо «искры» в белой плитке — дышащий знак W, партиал `_loader.html`;
- шаги онбординга — с фирменным узором (атрибута `data-bg-pattern="off"` нет).
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from problems.models_platform import UserProfile
from problems.tests.factories import make_user

ROOT = Path(settings.BASE_DIR)


class BuildScreenTests(TestCase):
    def setUp(self):
        self.user = make_user('build_r4')
        UserProfile.objects.filter(user=self.user).update(
            role='student', grade='10', level='basic', onboarded_at=timezone.now())
        self.client.force_login(self.user)

    def html(self):
        return self.client.get('/welcome/build/').content.decode('utf-8')

    def test_no_ghost_cards_and_no_spark(self):
        html = self.html()
        self.assertNotIn('ob-build-ghost', html)
        self.assertNotIn('ob-build-mark', html)
        self.assertEqual(html.count('<li style="--i:'), 3)

    def test_w_loader_is_on_the_build_screen(self):
        html = self.html()
        self.assertIn('class="w-loader"', html)
        self.assertIn('class="w-loader-mark"', html)
        mark = (ROOT / 'static/img/logo-mark.svg').read_text(encoding='utf-8')
        w_path = mark.split('<path fill="#00797a" d="', 1)[1].split('"', 1)[0]
        self.assertIn(w_path, html)

    def test_ghosts_and_leaving_stage_are_gone_from_styles_and_script(self):
        css = (ROOT / 'static/onboarding/onboarding.css').read_text(encoding='utf-8')
        js = (ROOT / 'static/onboarding/onboarding.js').read_text(encoding='utf-8')
        self.assertNotIn('ob-build-ghost', css)
        self.assertNotIn("classList.add('is-leaving')", js)


class LoaderPartialTests(TestCase):
    def partial(self):
        return (ROOT / 'templates/_loader.html').read_text(encoding='utf-8')

    def test_breathes_with_the_numbers_from_the_brief(self):
        text = self.partial()
        self.assertIn('animation: w-breathe 1.6s ease-in-out infinite alternate', text)
        self.assertIn('from { transform: scale(.96) rotate(-6deg); }', text)
        self.assertIn('to   { transform: scale(1.04) rotate(6deg); }', text)
        self.assertIn('@keyframes w-flow', text)

    def test_still_when_motion_is_reduced(self):
        text = self.partial()
        reduced = text.split('@media (prefers-reduced-motion: reduce)', 1)[1].split('</style>', 1)[0]
        self.assertIn('animation: none !important', reduced)

    def test_only_transforms_move_no_svg_filter(self):
        text = self.partial().split('{% endcomment %}', 1)[1]
        self.assertNotIn('feTurbulence', text)
        self.assertNotIn('feDisplacementMap', text)


class PatternTests(TestCase):
    def test_steps_have_the_pattern(self):
        user = make_user('pattern_r4')
        self.client.force_login(user)
        html = self.client.get('/welcome/role/').content.decode('utf-8')
        # Узор снимает только атрибут у тела страницы; в CSS токенов эта строка есть всегда.
        self.assertIn('<body class="ob">', html)
        self.assertNotIn('<body class="ob" data-bg-pattern="off">', html)
