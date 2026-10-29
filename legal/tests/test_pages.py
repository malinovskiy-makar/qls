# -*- coding: utf-8 -*-
"""Фаза 1: семь адресов открыты без входа, тексты на месте, футер везде."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from legal import documents

MAIL = '@'.join(('office', 'example.org'))   # адрес собран, а не записан: в репозитории писем нет
FILLED = {**settings.LEGAL, 'contact_email': MAIL, 'docs_date': '15 октября 2026 г.',
          'tg_relay': 'Example Hosting B.V., Нидерланды'}
EMPTY = {**settings.LEGAL, 'contact_email': '', 'docs_date': '', 'tg_relay': ''}

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
        self.assertIn('Редакция 2 от 15 октября 2026 г.', html)
        self.assertIn('<a href="mailto:%s">%s</a>' % (MAIL, MAIL), html)
        self.assertNotIn('class="lg-missing"', html)

    @override_settings(LEGAL={**FILLED, 'contact_email': 'x"><script>alert(1)</script>@a.ru'})
    def test_a_hostile_value_cannot_inject_markup(self):
        html = self.client.get('/legal/terms/').content.decode('utf-8')
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_the_text_files_stay_untouched_by_substitution(self):
        changed = {'privacy.md', 'consent.md', 'terms.md', 'consent_mail.md'}
        for doc in documents._every_document():
            text = doc.path.read_text(encoding='utf-8')
            if doc.filename in changed:
                self.assertIn('[ДАТА]', text, doc.filename)
            else:
                self.assertNotIn('[ДАТА]', text, doc.filename)

    @override_settings(LEGAL={**FILLED, 'docs_date': '29 октября 2026 г.'}, MAIL_ENABLED=True)
    def test_changed_documents_take_the_date_from_the_setting(self):
        for slug in ('consent', 'privacy', 'terms', 'consent-mail'):
            html = self.client.get('/legal/%s/' % slug).content.decode('utf-8')
            self.assertIn('от 29 октября 2026 г.', html, slug)

    @override_settings(LEGAL={**FILLED, 'docs_date': '29 октября 2026 г.'})
    def test_unchanged_documents_keep_their_own_date(self):
        """Дата выкатки не должна переписать дату документов, которые не менялись."""
        for slug in ('cookies', 'consent-ai', 'recommendations'):
            html = self.client.get('/legal/%s/' % slug).content.decode('utf-8')
            self.assertIn('Редакция 1 от 20.10.2026', html, slug)
            self.assertNotIn('29 октября 2026 г.', html, slug)

    @override_settings(LEGAL={**FILLED, 'tg_relay': 'Example Hosting B.V., Нидерланды'})
    def test_relay_label_is_substituted(self):
        for slug in ('privacy', 'consent'):
            html = self.client.get('/legal/%s/' % slug).content.decode('utf-8')
            self.assertIn('Example Hosting B.V., Нидерланды', html, slug)
            self.assertNotIn('[ПОСРЕДНИК]', html, slug)
            self.assertNotIn('class="lg-missing"', html, slug)

    @override_settings(LEGAL={**FILLED, 'tg_relay': ''})
    def test_empty_relay_shows_the_stub(self):
        html = self.client.get('/legal/privacy/').content.decode('utf-8')
        self.assertIn('за пределами России: <span class="lg-missing">[не заполнено]</span>', html)
        self.assertNotIn('[ПОСРЕДНИК]', html)

    @override_settings(LEGAL={**FILLED, 'tg_relay': '<b>X</b> & Y'})
    def test_relay_value_is_escaped(self):
        html = self.client.get('/legal/privacy/').content.decode('utf-8')
        self.assertIn('&lt;b&gt;X&lt;/b&gt; &amp; Y', html)
        self.assertNotIn('<b>X</b>', html)

    def test_relay_value_with_a_newline_or_too_long_is_the_stub(self):
        self.assertIn('lg-missing', documents.relay_html('Хостер\nстрана'))
        self.assertIn('lg-missing', documents.relay_html('x' * 201))
        self.assertEqual(documents.relay_html('x' * 200), 'x' * 200)

    def test_privacy_and_consent_name_the_recipients(self):
        for slug in ('privacy', 'consent'):
            html = self.client.get('/legal/%s/' % slug).content.decode('utf-8')
            for name in ('Яндекс.Облако', 'Юнисендер Смарт', 'Telegram Messenger Inc.'):
                self.assertIn(name, html, '%s: %s' % (slug, name))

    def test_privacy_says_there_is_no_third_party_login(self):
        html = self.client.get('/legal/privacy/').content.decode('utf-8')
        self.assertIn('3.4. Войти в Сервис можно только по логину', html)
        self.assertIn('Вход через Telegram, Google, Apple', html)
        self.assertIn('не предусмотрен', html)

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
    """Инвариант: каждый шаблон-документ решает про подвал явно (раунд 4, 29.10.2026).

    Решение владельца: подвал с документами только на главной, в профиле, на /legal/
    и на входе/регистрации. Каждый корневой шаблон либо держит блок
    `{% block site_footer %}` (пустой по умолчанию, страница включает
    `_site_footer.html`), либо сам является такой страницей. Список корней
    собирается обходом: новый корневой шаблон без решения краснит этот тест.
    Ссылки на /legal/ с главной и профиля дают доступность документов на сайте.
    """

    #: Корни, которые сами — страницы с подвалом (документы, вход, регистрация).
    OWN_FOOTER = {'legal/templates/legal/accept.html',
                  'templates/registration/login.html',
                  'templates/registration/register.html'}
    #: 12 корневых шаблонов из отчёта инвентаризации + экран согласия + онбординг.
    INVENTORY_ROOTS = 14

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

    def test_every_root_template_decides_about_the_footer(self):
        base = Path(settings.BASE_DIR)
        roots = self._roots()
        missing = []
        for rel in roots:
            text = (base / rel).read_text(encoding='utf-8')
            if '{% block site_footer %}' in text:
                continue
            if rel in self.OWN_FOOTER and "{% include '_legal_footer.html' %}" in text:
                continue
            missing.append(rel)
        self.assertEqual(missing, [], 'корневой шаблон без решения про подвал')
        self.assertEqual(len(roots), self.INVENTORY_ROOTS)

    def test_footer_pages_include_it_in_the_block(self):
        base = Path(settings.BASE_DIR)
        for rel in ('catalog/templates/catalog/home.html', 'legal/templates/legal/index.html',
                    'legal/templates/legal/document.html',
                    'problems/templates/platform/profile.html',
                    'templates/registration/login.html', 'templates/registration/register.html'):
            text = (base / rel).read_text(encoding='utf-8')
            self.assertIn("{% block site_footer %}{% include '_site_footer.html' %}{% endblock %}",
                          text, rel)


class FooterRenderTests(TestCase):
    LINE = ('© 2026 Weconomics', 'Документы', 'Политика', 'Соглашение', 'Рекомендации',
            'Настройки cookie', '12+')

    def test_footer_is_on_home_legal_login_register(self):
        for url in ('/', '/login/', '/register/', '/legal/', '/legal/privacy/'):
            response = self.client.get(url, follow=True)
            html = response.content.decode('utf-8')
            block = html.split('<p class="legal-foot">', 1)
            self.assertEqual(len(block), 2, url)
            text = re.sub(r'<[^>]+>', ' ', block[1].split('</p>', 1)[0])
            for part in self.LINE:
                self.assertIn(part, text, url)
            for href in ('/legal/', '/legal/privacy/', '/legal/terms/', '/legal/recommendations/'):
                self.assertIn('href="%s"' % href, block[1].split('</p>', 1)[0], url)

    def test_game_calculator_and_catalog_have_no_footer(self):
        """Решение 29.10.2026: в игре, на калькуляторе и в каталоге подвала нет."""
        for url in ('/game/', '/calc2/', '/catalog/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertNotIn('<p class="legal-foot">', html, url)
            self.assertNotIn('class="site-version"', html, url)

    def test_calculator_takes_the_whole_window_under_the_header(self):
        """Полосы в 30 px под строку документов больше нет: приложение — до низа окна."""
        html = self.client.get('/calc2/').content.decode('utf-8')
        self.assertIn('id="scene-picker"', html)
        self.assertNotIn('calc-foot', html)
        self.assertIn('.app { height: calc(100vh - 48px - var(--ck-h, 0px)); }', html)
        self.assertIn('#scene-picker { bottom: var(--ck-h, 0px); }', html)

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
