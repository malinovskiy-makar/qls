# -*- coding: utf-8 -*-
"""Фаза 1: семь адресов открыты без входа, тексты на месте, футер везде."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from legal import documents

MAIL = '@'.join(('office', 'example.org'))   # адрес собран, а не записан: в репозитории писем нет
FILLED = {**settings.LEGAL, 'contact_email': MAIL, 'docs_date': '15 октября 2026 г.'}
EMPTY = {**settings.LEGAL, 'contact_email': '', 'docs_date': ''}

URLS = ['/legal/', '/legal/privacy/', '/legal/consent/', '/legal/consent-ai/',
        '/legal/cookies/', '/legal/terms/', '/legal/recommendations/']


class PublicPagesTests(TestCase):
    def test_seven_addresses_answer_200_without_login(self):
        for url in URLS:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_unknown_document_is_404(self):
        self.assertEqual(self.client.get('/legal/nothing/').status_code, 404)

    @override_settings(LEGAL=EMPTY)
    def test_empty_values_show_a_visible_stub_and_not_emptiness(self):
        html = self.client.get('/legal/privacy/').content.decode('utf-8')
        self.assertIn('<span class="lg-missing">[не заполнено]</span>', html)
        self.assertNotIn('[ПОЧТА]', html)
        self.assertNotIn('[ДАТА]', html)
        index = self.client.get('/legal/').content.decode('utf-8')
        self.assertIn('class="lg-missing"', index)

    @override_settings(LEGAL=FILLED)
    def test_values_are_substituted_from_settings(self):
        html = self.client.get('/legal/privacy/').content.decode('utf-8')
        self.assertIn('Редакция 1 от 15 октября 2026 г.', html)
        self.assertIn('<a href="mailto:%s">%s</a>' % (MAIL, MAIL), html)
        self.assertNotIn('class="lg-missing"', html)

    @override_settings(LEGAL={**FILLED, 'contact_email': 'x"><script>alert(1)</script>@a.ru'})
    def test_a_hostile_value_cannot_inject_markup(self):
        html = self.client.get('/legal/terms/').content.decode('utf-8')
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_the_text_files_stay_untouched_by_substitution(self):
        for doc in documents.all_documents():
            text = doc.path.read_text(encoding='utf-8')
            self.assertIn('[ДАТА]', text, doc.filename)

    def test_tables_render_as_tables(self):
        privacy = self.client.get('/legal/privacy/').content.decode('utf-8')
        self.assertEqual(privacy.count('<table>'), 3)
        self.assertIn('<th>Цель</th>', privacy)
        self.assertNotIn('|---|', privacy)
        self.assertEqual(self.client.get('/legal/cookies/').content.decode('utf-8').count('<table>'), 2)

    def test_raw_html_in_a_text_would_be_escaped(self):
        rendered = documents._renderer().render('a <script>x</script> b')
        self.assertNotIn('<script>', rendered)

    def test_links_inside_the_texts_resolve(self):
        """Ссылки /legal/... внутри самих документов ведут на живые страницы."""
        seen = set()
        for doc in documents.all_documents():
            html = self.client.get('/legal/%s/' % doc.slug).content.decode('utf-8')
            body = html.split('<article', 1)[1]
            seen |= set(re.findall(r'href="(/legal/[^"]*)"', body))
        self.assertTrue(seen)
        for url in seen:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_index_has_the_requisites_and_all_documents(self):
        html = self.client.get('/legal/').content.decode('utf-8')
        for needle in ('Ленглер Андрей Викторович', '662333547172',
                       'плательщик налога на профессиональный доход',
                       'https://t.me/weconomics_ru', '12+'):
            self.assertIn(needle, html)
        for doc in documents.all_documents():
            self.assertIn('href="/legal/%s/"' % doc.slug, html)

    def test_pages_use_only_design_tokens_and_no_emoji(self):
        base = Path(settings.BASE_DIR)
        for rel in ('legal/templates/legal/_style.html', 'templates/_legal_footer.html'):
            text = (base / rel).read_text(encoding='utf-8')
            body = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', text, flags=re.S)
            self.assertIsNone(re.search(r'#[0-9a-fA-F]{3,8}\b', body), rel)
            self.assertIsNone(re.search(r'[\U0001F300-\U0001FAFF☀-➿]', body), rel)


class RootTemplateFooterTests(SimpleTestCase):
    """Инвариант: каждый шаблон-документ несёт ссылку на /legal/.

    Список корневых шаблонов собирается обходом (как у
    `problems.tests.test_signup_source.EveryRootTemplateTests`), а не пишется
    руками: новый корневой шаблон без футера краснит этот тест.
    """

    #: Исключений нет: с части Б (09.10.2026) строка документов стоит и в игре, и на
    #: калькуляторе, в нижней строке рядом с меткой версии. Раньше там была только
    #: ссылка «Документы» в шапке (иконка без подписи).
    NAV_LINK_ONLY = set()
    #: 12 корневых шаблонов из отчёта инвентаризации (раздел 3.1), по умолчанию
    #: подключающих счётчик, плюс экран согласия, добавленный этой работой.
    INVENTORY_ROOTS = 12

    def _roots(self):
        base = Path(settings.BASE_DIR)
        paths = list(base.glob('templates/**/*.html')) + list(base.glob('*/templates/**/*.html'))
        roots = []
        for p in paths:
            rel = p.relative_to(base)
            if rel.parts[0].startswith(('venv', 'node_modules')):
                continue
            if re.search(r'<!doctype html', p.read_text(encoding='utf-8'), re.I):
                roots.append(rel.as_posix())
        return sorted(roots)

    def test_every_root_template_links_to_legal(self):
        base = Path(settings.BASE_DIR)
        roots = self._roots()
        with_footer, with_nav_link, missing = [], [], []
        for rel in roots:
            text = (base / rel).read_text(encoding='utf-8')
            if "{% include '_legal_footer.html' %}" in text:
                with_footer.append(rel)
            elif rel in self.NAV_LINK_ONLY and "nav_docs_link=True" in text:
                with_nav_link.append(rel)
            else:
                missing.append(rel)
        self.assertEqual(missing, [], 'корневой шаблон без ссылки на /legal/')
        # Инвариант: корней из отчёта - 12 (+ экран согласия); у каждого есть ссылка.
        new_roots = {'legal/templates/legal/accept.html'}
        self.assertEqual(len(with_footer) + len(with_nav_link), self.INVENTORY_ROOTS + len(new_roots))
        self.assertEqual(set(with_nav_link), self.NAV_LINK_ONLY)
        self.assertTrue(new_roots <= set(with_footer))


class FooterRenderTests(TestCase):
    LINE = ('© 2026 Weconomics', 'Документы', 'Политика', 'Соглашение', 'Рекомендации',
            'Настройки cookie', '12+')

    def test_footer_is_on_public_pages(self):
        for url in ('/', '/catalog/', '/login/', '/register/', '/legal/privacy/', '/game/', '/calc2/'):
            response = self.client.get(url, follow=True)
            html = response.content.decode('utf-8')
            block = html.split('<p class="legal-foot">', 1)
            self.assertEqual(len(block), 2, url)
            text = re.sub(r'<[^>]+>', ' ', block[1].split('</p>', 1)[0])
            for part in self.LINE:
                self.assertIn(part, text, url)
            for href in ('/legal/', '/legal/privacy/', '/legal/terms/', '/legal/recommendations/'):
                self.assertIn('href="%s"' % href, block[1].split('</p>', 1)[0], url)

    def test_game_and_calculator_have_the_footer_line_with_visible_text(self):
        """Часть Б: строка документов стоит и в игре, и на калькуляторе (с подписью, не значком)."""
        for url in ('/game/', '/calc2/'):
            html = self.client.get(url).content.decode('utf-8')
            block = html.split('<p class="legal-foot">', 1)
            self.assertEqual(len(block), 2, url)
            self.assertIn('>Документы</a>', block[1].split('</p>', 1)[0], url)
            # Метка версии и строка документов рядом: в одном месте страницы.
            self.assertLess(html.index('class="site-version"'), html.index('<p class="legal-foot">'))

    def test_calculator_model_picker_shows_the_footer_line(self):
        """Экран выбора моделей (окно поверх приложения) не закрывает строку документов."""
        html = self.client.get('/calc2/').content.decode('utf-8')
        self.assertIn('id="scene-picker"', html)
        footer = html.split('<div class="calc-foot">', 1)[1].split('</p>', 1)[0]
        self.assertIn('Beta 1.1', footer)
        self.assertIn('<a href="/legal/">Документы</a>', footer)
        # Окно выбора кончается над полосой (и над окном cookie, пока оно открыто).
        self.assertIn('#scene-picker { bottom: calc(30px + var(--ck-h, 0px)); }', html)

    def test_calculator_has_the_docs_link_in_the_header(self):
        from problems.tests.factories import make_user
        self.client.force_login(make_user('calc_legal'))
        html = self.client.get('/calc2/').content.decode('utf-8')
        self.assertIn('nav-docs-btn', html)
        self.assertIn('nav-docs-panel', html)
        self.assertIn('href="%s">Документы</a>' % reverse('legal:index'), html)

    def test_task_screen_has_the_docs_link_in_the_header_and_hides_the_footer(self):
        """Экран задачи занят ровно в высоту окна: футер там скрыт, ссылка стоит в шапке."""
        from problems.tests.factories import make_problem
        problem = make_problem('Условие.', title='Задача')
        html = self.client.get(reverse('catalog:problem_detail', args=[problem.pk])).content.decode('utf-8')
        self.assertIn('<a class="nav-icon-btn nav-docs-btn" href="%s"' % reverse('legal:index'), html)
        css = (Path(settings.BASE_DIR) / 'catalog/static/catalog/css/stol.css').read_text(encoding='utf-8')
        self.assertIn('body:has(.stol-app[data-view="stol"]) .legal-foot { display: none; }', css)
