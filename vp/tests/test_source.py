"""Подпись источника у варианта ВП: поля модели, импорт из YAML, отрисовка ссылки.

`source_label`/`source_url` — правообладатель (Олмат и т.п.), не путать с
`author`/`source_note` (происхождение варианта, свободный текст без ссылки).
Оба новых поля заполняются вместе или пустуют вместе — проверяется и на
уровне модели (`VPVariant.clean`), и на уровне импорта (`vp.loader`).
"""
import copy
import pathlib
import re
import tempfile
from html.parser import HTMLParser
from io import StringIO

import yaml
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.urls import reverse

from vp.models import VPAttempt, VPVariant
from vp.tests.helpers import make_published

SELFTEST = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'vp' / '_selftest.yaml'
OLMAT_LABEL = 'Олмат'
OLMAT_URL = 'https://t.me/vsosh_aa_bot'


def load_data():
    return yaml.safe_load(SELFTEST.read_text(encoding='utf-8'))


# ------------------------------------------------------------- разметка

class _AnchorNestingChecker(HTMLParser):
    """Был ли уже открыт другой <a>, когда встретился <a href=target_href>."""

    def __init__(self, target_href):
        super().__init__()
        self.target_href = target_href
        self._open_a = 0
        self.found = False
        self.nested = False

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        if dict(attrs).get('href') == self.target_href:
            self.found = True
            if self._open_a > 0:
                self.nested = True
        self._open_a += 1

    def handle_endtag(self, tag):
        if tag == 'a' and self._open_a > 0:
            self._open_a -= 1


def source_link_is_nested(html, href=OLMAT_URL):
    """True, если ссылка с этим href открылась внутри ЕЩЁ ОДНОГО <a>."""
    checker = _AnchorNestingChecker(href)
    checker.feed(html)
    assert checker.found, f'ссылка с href={href!r} не найдена в HTML'
    return checker.nested


def source_link_rel(html, href=OLMAT_URL):
    """Значение атрибута rel у ссылки с этим href (по отданному HTML)."""
    match = re.search(rf'<a\b[^>]*\bhref="{re.escape(href)}"[^>]*>', html)
    assert match, f'ссылка с href={href!r} не найдена в HTML'
    rel = re.search(r'\brel="([^"]*)"', match.group(0))
    return rel.group(1) if rel else ''


def variant_card(html, title):
    """Карточка варианта с этим заголовком на экране выбора `/vp/variants/`.

    ⚠️ С 22.09.2026 карточки живут не на посадочной, а на отдельном экране:
    `index_html` ниже ходит именно туда.
    """
    for block in re.findall(r'<article class="vp-vcard.*?</article>', html, re.S):
        if title in block:
            return block
    raise AssertionError(f'карточка варианта с заголовком {title!r} не найдена')


# --------------------------------------------------------------- импорт

class ImportTestCase(TestCase):
    """Тот же приём, что в test_import.py: пишем YAML во временный файл и зовём команду."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name='v.yaml'):
        path = pathlib.Path(self.tmp.name) / name
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding='utf-8')
        return str(path)

    def run_import(self, data, *args, expect_error=False):
        path = self.write(data)
        out, err = StringIO(), StringIO()
        if expect_error:
            with self.assertRaises(CommandError) as ctx:
                call_command('import_vp', path, *args, stdout=out, stderr=err)
            return out.getvalue(), err.getvalue() + str(ctx.exception)
        call_command('import_vp', path, *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()


class ImportSourceTests(ImportTestCase):
    def test_1_source_block_fills_both_fields(self):
        data = load_data()
        data['source'] = {'label': OLMAT_LABEL, 'url': OLMAT_URL}
        self.run_import(data)
        variant = VPVariant.objects.get(slug='vp-selftest')
        self.assertEqual(variant.source_label, OLMAT_LABEL)
        self.assertEqual(variant.source_url, OLMAT_URL)

    def test_2a_label_without_url_refuses(self):
        data = load_data()
        data['source'] = {'label': OLMAT_LABEL}
        _, err = self.run_import(data, expect_error=True)
        self.assertIn('source.label', err)
        self.assertIn('оба', err)
        self.assertEqual(VPVariant.objects.count(), 0)

    def test_2b_url_without_label_refuses(self):
        data = load_data()
        data['source'] = {'url': OLMAT_URL}
        _, err = self.run_import(data, expect_error=True)
        self.assertIn('оба', err)
        self.assertEqual(VPVariant.objects.count(), 0)

    def test_3_http_url_refuses(self):
        data = load_data()
        data['source'] = {'label': OLMAT_LABEL, 'url': 'http://t.me/vsosh_aa_bot'}
        _, err = self.run_import(data, expect_error=True)
        self.assertIn('https://', err)
        self.assertEqual(VPVariant.objects.count(), 0)

    def test_missing_source_block_is_not_a_warning(self):
        """Отсутствие блока — нормальное состояние (демоварианты ВШЭ), не предупреждение."""
        data = load_data()
        out, _ = self.run_import(data)
        self.assertNotIn('предупреждение', out)
        variant = VPVariant.objects.get(slug='vp-selftest')
        self.assertEqual(variant.source_label, '')
        self.assertEqual(variant.source_url, '')

    def test_4_repeated_import_with_changed_label_updates_not_duplicates(self):
        data = load_data()
        data['source'] = {'label': OLMAT_LABEL, 'url': OLMAT_URL}
        self.run_import(data)
        data['source']['label'] = 'Олмат (правка)'
        out, _ = self.run_import(data)
        self.assertIn('source_label', out)
        self.assertEqual(VPVariant.objects.count(), 1)
        self.assertEqual(VPVariant.objects.get().source_label, 'Олмат (правка)')


# -------------------------------------------------------- модель напрямую

class ModelInvariantTests(TestCase):
    """Тот же инвариант, но без импорта — прямой `.save()` в обход loader.py."""

    def make(self, **extra):
        return VPVariant(slug='x', title='X', grade_band='9-10', year=2026,
                         source_kind='demo', **extra)

    def test_label_without_url_raises_on_save(self):
        with self.assertRaises(ValidationError):
            self.make(source_label=OLMAT_LABEL).save()

    def test_http_url_raises_on_save(self):
        with self.assertRaises(ValidationError):
            self.make(source_label=OLMAT_LABEL,
                      source_url='http://t.me/vsosh_aa_bot').save()

    def test_both_blank_saves_fine(self):
        variant = self.make()
        variant.save()
        self.assertEqual(VPVariant.objects.get(pk=variant.pk).source_label, '')

    def test_both_filled_saves_fine(self):
        variant = self.make(source_label=OLMAT_LABEL, source_url=OLMAT_URL)
        variant.save()
        self.assertEqual(VPVariant.objects.get(pk=variant.pk).source_url, OLMAT_URL)


# --------------------------------------------------------------- экраны

class RenderingBase(TestCase):
    def setUp(self):
        self.olmat = make_published('vp-olmat')
        self.olmat.title = 'Вариант Олмата'
        self.olmat.source_label = OLMAT_LABEL
        self.olmat.source_url = OLMAT_URL
        self.olmat.save()
        self.official = make_published('vp-official')
        self.official.title = 'Официальный демовариант'
        self.official.save()
        self.guest = Client()

    def index_html(self):
        """Экран, где стоят карточки вариантов: с 22.09.2026 это `/vp/variants/`."""
        response = self.guest.get(reverse('vp:variants'))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def intro_html(self, slug):
        response = self.guest.get(reverse('vp:intro', args=[slug]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class IndexCardSourceTests(RenderingBase):
    def test_5a_olmat_card_links_to_the_source(self):
        card = variant_card(self.index_html(), self.olmat.title)
        self.assertIn('Источник:', card)
        self.assertRegex(
            card, rf'<a[^>]+href="{re.escape(OLMAT_URL)}"[^>]*>{OLMAT_LABEL}</a>')

    def test_5b_official_card_has_no_source_line(self):
        card = variant_card(self.index_html(), self.official.title)
        self.assertNotIn('Источник:', card)
        self.assertNotIn(OLMAT_URL, card)


class IntroSourceTests(RenderingBase):
    def test_6a_olmat_intro_links_to_the_source(self):
        html = self.intro_html(self.olmat.slug)
        self.assertIn('Источник:', html)
        self.assertRegex(
            html, rf'<a[^>]+href="{re.escape(OLMAT_URL)}"[^>]*>{OLMAT_LABEL}</a>')

    def test_6b_official_intro_has_no_source_line(self):
        html = self.intro_html(self.official.slug)
        self.assertNotIn('Источник:', html)
        self.assertNotIn(OLMAT_URL, html)


class TakeSourceTests(RenderingBase):
    def test_7_take_page_has_no_source_line_or_link(self):
        # ⚠️ Не проверяем отсутствие слова «Олмат» целиком: оно легитимно есть
        # в <title> вкладки (взято из variant.title, который тест переименовал
        # для различения карточек). Важно — нет ни строки «Источник:», ни
        # самой ссылки на источник.
        # Стена регистрации (22.09.2026): попытку заводит только вошедший.
        person = Client()
        person.force_login(
            get_user_model().objects.create_user('vp_src', password='p12345'))
        person.post(reverse('vp:start', args=[self.olmat.slug]), {'with_timer': '0'})
        attempt = VPAttempt.objects.order_by('-id').first()
        html = person.get(reverse('vp:take', args=[attempt.public_code])).content.decode()
        self.assertNotIn('Источник:', html)
        self.assertNotIn(OLMAT_URL, html)


class MarkupSafetyTests(RenderingBase):
    def test_8a_index_source_link_is_not_nested_in_another_anchor(self):
        card = variant_card(self.index_html(), self.olmat.title)
        self.assertFalse(source_link_is_nested(card))

    def test_8b_intro_source_link_is_not_nested_in_another_anchor(self):
        html = self.intro_html(self.olmat.slug)
        self.assertFalse(source_link_is_nested(html))

    def test_9a_index_source_link_rel_has_noopener(self):
        card = variant_card(self.index_html(), self.olmat.title)
        self.assertIn('noopener', source_link_rel(card).split())

    def test_9b_intro_source_link_rel_has_noopener(self):
        html = self.intro_html(self.olmat.slug)
        self.assertIn('noopener', source_link_rel(html).split())
