# -*- coding: utf-8 -*-
"""Фаза 0: реквизиты в одном месте и проверка, не пускающая сайт с заглушками."""
import re
from pathlib import Path

from django.conf import settings
from django.core import checks
from django.test import SimpleTestCase, override_settings

from legal import checks as legal_checks
from legal import documents

MAIL = '@'.join(('office', 'example.org'))   # адрес собран, а не записан: в репозитории писем нет
FILLED = {**settings.LEGAL, 'contact_email': MAIL, 'docs_date': '15 октября 2026 г.'}
EMPTY = {**settings.LEGAL, 'contact_email': '', 'docs_date': ''}


class RequisitesTests(SimpleTestCase):
    def test_constants_are_exactly_the_agreed_ones(self):
        legal = settings.LEGAL
        self.assertEqual(legal['operator_name'], 'Ленглер Андрей Викторович')
        self.assertEqual(legal['operator_inn'], '662333547172')
        self.assertEqual(legal['operator_status'], 'плательщик налога на профессиональный доход')
        self.assertEqual(legal['telegram'], 'weconomics_ru')
        self.assertEqual(legal['docs_version'], '1')

    def test_no_private_data_in_the_public_repository(self):
        """Репозиторий публичный: ни домашнего адреса, ни телефона, ни почты в коде."""
        base = Path(settings.BASE_DIR)
        settings_text = (base / 'config' / 'settings.py').read_text(encoding='utf-8')
        block = settings_text.split('# ─── Правовые документы', 1)[1].split('def _redis_cache', 1)[0]
        texts = {'config/settings.py (блок LEGAL)': block}
        for p in (base / 'legal').rglob('*'):
            if p.is_file() and p.suffix in {'.py', '.html', '.md'} and 'tests' not in p.parts:
                texts[str(p.relative_to(base))] = p.read_text(encoding='utf-8')
        # Чужая фамилия не должна попасть в код; в самом тесте её целиком не пишем.
        forbidden = [re.compile('Фомич' 'ев'),
                     re.compile(r'(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)'),
                     re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')]
        for path, text in texts.items():
            for pattern in forbidden:
                self.assertIsNone(pattern.search(text), '%s: %s' % (path, pattern.pattern))

    def test_every_document_carries_the_current_edition_number(self):
        """Номер в тексте («Редакция N от») и в настройках не должны расходиться."""
        marker = 'Редакция %s от [ДАТА]' % settings.LEGAL['docs_version']
        for doc in documents.all_documents():
            text = doc.path.read_text(encoding='utf-8')
            self.assertEqual(text.count(marker), 1, doc.filename)
            self.assertIn(settings.LEGAL['operator_inn'], text, doc.filename)

    def test_six_documents(self):
        self.assertEqual([d.slug for d in documents.all_documents()],
                         ['privacy', 'consent', 'consent-ai', 'cookies', 'terms', 'recommendations'])


class CheckTests(SimpleTestCase):
    """Проверка legal.E001: при DEBUG=False пустая почта или дата - ошибка."""

    def _run(self):
        return [m for m in legal_checks.legal_requisites_filled(None) if m.id == 'legal.E001']

    @override_settings(DEBUG=False, LEGAL_ENFORCEMENT_ENABLED=True, LEGAL=EMPTY)
    def test_empty_email_and_date_are_errors_when_not_debug(self):
        found = self._run()
        self.assertEqual(len(found), 2)
        self.assertTrue(all(m.level == checks.ERROR for m in found))
        hints = ' '.join(m.hint for m in found)
        self.assertIn('LEGAL_CONTACT_EMAIL', hints)
        self.assertIn('LEGAL_DOCS_DATE', hints)

    @override_settings(DEBUG=False, LEGAL_ENFORCEMENT_ENABLED=True,
                       LEGAL={**EMPTY, 'docs_date': '15 октября 2026 г.'})
    def test_only_the_empty_one_is_reported(self):
        found = self._run()
        self.assertEqual(len(found), 1)
        self.assertIn('LEGAL_CONTACT_EMAIL', found[0].hint)

    @override_settings(DEBUG=False, LEGAL_ENFORCEMENT_ENABLED=True, LEGAL=FILLED)
    def test_filled_values_pass(self):
        self.assertEqual(self._run(), [])

    @override_settings(DEBUG=False, LEGAL_ENFORCEMENT_ENABLED=True,
                       LEGAL={**FILLED, 'contact_email': 'не почта'})
    def test_a_malformed_email_is_an_error_too(self):
        found = [m for m in legal_checks.legal_requisites_filled(None) if m.id == 'legal.E002']
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].level, checks.ERROR)

    @override_settings(DEBUG=True, LEGAL_ENFORCEMENT_ENABLED=True, LEGAL=EMPTY)
    def test_debug_is_not_blocked(self):
        self.assertEqual(self._run(), [])

    @override_settings(DEBUG=False, LEGAL_ENFORCEMENT_ENABLED=False, LEGAL=EMPTY)
    def test_test_runs_are_not_blocked(self):
        self.assertEqual(self._run(), [])

    @override_settings(DEBUG=False, LEGAL_ENFORCEMENT_ENABLED=True, LEGAL=EMPTY)
    def test_the_check_is_registered_with_django(self):
        """Не только функция: Django сам обязан её запускать (`manage.py check`)."""
        from django.core.checks.registry import registry
        ids = {m.id for m in registry.run_checks()}
        self.assertIn('legal.E001', ids)
