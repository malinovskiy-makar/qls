# -*- coding: utf-8 -*-
"""Блок согласия в панели помощника: отказ, «Включить помощника», входы без согласия (09.10.2026).

Уровень проверки – разметка, ответ сервера и код скрипта страницы (`stol_task.js`):
браузерного прогона здесь нет. Что держат тесты.

* «Нет, не согласен» и «Включить помощника» не создают записи согласия: в разметке у них
  нет адреса, а их обработчики в скрипте на сервер не ходят вовсе.
* Вход в помощника через плитку «Спросить ИИ» (и любые другие входы) без согласия поля
  ввода не открывает: поле скрыто сервером, все входы скрипта сначала проверяют согласие
  и показывают блок, а сервер отвечает 403 и ничего не пишет.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from legal import consent
from problems.models_legal import ConsentRecord
from problems.models_platform import ChatTurn
from problems.tests.factories import make_problem, make_topic, make_user

AI = ConsentRecord.Kind.AI
PD = ConsentRecord.Kind.PD
JS = Path(settings.BASE_DIR) / 'catalog' / 'static' / 'catalog' / 'js' / 'stol_task.js'
#: Признаки обращения к серверу в коде обработчика.
NETWORK = ('post(', 'fetch(', 'aiConsentUrl', 'XMLHttpRequest')


def _function_body(js, name):
    """Тело однострочной функции `function name() { … }` из скрипта страницы."""
    match = re.search(r'function %s\(\) \{(.*)\}\n' % name, js)
    assert match, 'в stol_task.js нет функции %s' % name
    return match.group(1)


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', LEGAL_ENFORCEMENT_ENABLED=True)
class ConsentBlockTests(TestCase):
    def setUp(self):
        cache.clear()
        self.problem = make_problem('Условие.', title='Задача', topic=make_topic('Рынок труда'))
        self.user = make_user('block_student')
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self.client.force_login(self.user)
        self.page = reverse('catalog:problem_detail', args=[self.problem.pk])
        self.js = JS.read_text(encoding='utf-8')

    def _ai_records(self):
        return ConsentRecord.objects.filter(user=self.user, kind=AI).count()

    def test_decline_creates_no_record(self):
        html = self.client.get(self.page).content.decode('utf-8')
        button = re.search(r'<button[^>]*id="ai-consent-no"[^>]*>', html).group(0)
        # У кнопки нет ни формы, ни адреса: отправлять ей нечего и некуда.
        for attr in ('formaction', 'data-url', 'href'):
            self.assertNotIn(attr, button)
        body = _function_body(self.js, 'decline')
        for sign in NETWORK:
            self.assertNotIn(sign, body, 'отказ ходит на сервер')
        self.assertIn('rememberDeclined(true)', body)
        self.assertIn("no.addEventListener('click', decline)", self.js)
        self.assertEqual(self._ai_records(), 0)

    def test_reopen_creates_no_record(self):
        html = self.client.get(self.page).content.decode('utf-8')
        button = re.search(r'<button[^>]*id="ai-consent-on"[^>]*>', html).group(0)
        for attr in ('formaction', 'data-url', 'href'):
            self.assertNotIn(attr, button)
        body = _function_body(self.js, 'reopen')
        for sign in NETWORK:
            self.assertNotIn(sign, body, '«Включить помощника» ходит на сервер')
        self.assertIn("on.addEventListener('click', reopen)", self.js)
        # Согласие пишет только «Да, согласен»: единственное место с адресом согласия.
        self.assertEqual(self.js.count('post(t.cfg.aiConsentUrl'), 1)
        self.assertIn("yes.addEventListener('click'", self.js)
        self.assertEqual(self._ai_records(), 0)

    def test_tile_without_consent_does_not_open_the_input(self):
        html = self.client.get(self.page).content.decode('utf-8')
        # Плитки «Спросить ИИ» на месте, а поле ввода скрыто сервером.
        self.assertIn('data-step="ai"', html)
        self.assertIn('data-phone="ai"', html)
        live = re.search(r'<div class="ai-live" id="ai-live"[^>]*>', html).group(0)
        self.assertIn('hidden', live)
        box = re.search(r'<div class="ai-consent" id="ai-consent"[^>]*>', html).group(0)
        self.assertNotIn('hidden', box)
        # Скрипт: ступень «ai» сначала спрашивает о согласии, и каждый вход в разговор
        # (фокус, отправка, подстановка) проверяет его до того, как тронуть поле.
        self.assertIn('if (t.consent && t.consent.needed()) t.consent.show();\n'
                      '      else if (t.chat) t.chat.focus();', self.js)
        for entry in ("send: function (text) { if (blocked()) return;",
                      "focus: function () { if (blocked()) return;",
                      "prefill: function (prefix, q, source) {\n        if (blocked()) return;"):
            self.assertIn(entry, self.js)
        # Сервер: без записи `ai` разговор не начинается и ничего не сохраняется.
        response = self.client.post(reverse('catalog:api_chat'), json.dumps(
            {'problem_id': self.problem.pk, 'message': 'С чего начать?', 'history': []}),
            content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'ai_consent_required')
        self.assertEqual(ChatTurn.objects.filter(user=self.user).count(), 0)
        self.assertEqual(self._ai_records(), 0)

    def test_collapsed_state_lives_only_in_the_browser(self):
        # Свёрнутость – отметка в localStorage в try/catch, на сервере отказ не хранится.
        self.assertIn("var DECLINED_KEY = 'weco_ai_declined';", self.js)
        remember = re.search(r'function rememberDeclined\(on\) \{(.*?)\n  \}', self.js, re.S).group(1)
        self.assertIn('try {', remember)
        self.assertIn('localStorage', remember)
        html = self.client.get(self.page).content.decode('utf-8')
        self.assertNotIn('weco_ai_declined', html)

    def test_the_old_button_name_is_gone_from_the_repository(self):
        base = Path(settings.BASE_DIR)
        hits = []
        for folder in ('catalog', 'legal', 'templates', 'problems', 'static', 'docs'):
            for path in (base / folder).rglob('*'):
                if path.suffix not in ('.py', '.html', '.js', '.md', '.css', '.txt') or not path.is_file():
                    continue
                if path.name == Path(__file__).name:
                    continue
                if 'Согласен, открыть помощника' in path.read_text(encoding='utf-8', errors='ignore'):
                    hits.append(str(path.relative_to(base)))
        self.assertEqual(hits, [])
        text = (base / 'legal' / 'texts' / 'consent_ai.md').read_text(encoding='utf-8')
        self.assertIn('Нажимая кнопку «Да, согласен» в блоке помощника, я даю', text)
