# -*- coding: utf-8 -*-
"""Фаза 5: всё, что отправляет данные человека модели, требует согласия `ai`."""
import io
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from legal import consent
from problems.models_legal import ConsentRecord
from problems.models import FileAsset
from problems.models_platform import ChatAttachment
from problems.tests.factories import make_problem, make_topic, make_user

AI = ConsentRecord.Kind.AI
PD = ConsentRecord.Kind.PD
MEDIA = tempfile.mkdtemp(prefix='qls_legal_media_')
def _png():
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), (255, 255, 255)).save(buf, 'PNG')
    return buf.getvalue()


PNG = _png()


@override_settings(LEGAL_ENFORCEMENT_ENABLED=True, AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake',
                   CATALOG_CHAT_MODEL='glm-5.3', CATALOG_CHAT_VISION_MODEL='glm-5.3-flash',
                   MEDIA_ROOT=MEDIA, AI_FAKE_REPLY=json.dumps({'reply': 'ответ', 'text': 'x'}))
class AiConsentTests(TestCase):
    def setUp(self):
        cache.clear()
        topic = make_topic('Олигополия и теория игр')
        self.problem = make_problem('Две фирмы выбирают выпуск.', title='Штакельберг',
                                    topic=topic, answer='q1 = 30')
        self.user = make_user('ai_student')
        # Документы приняты: экран согласия не мешает, проверяется только `ai`.
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self.client.force_login(self.user)

    # -- помощники ---------------------------------------------------------

    def _chat(self):
        return self.client.post(reverse('catalog:api_chat'), json.dumps(
            {'problem_id': self.problem.pk, 'message': 'С чего начать?', 'history': []}),
            content_type='application/json')

    def _attempt(self):
        return self.client.post(reverse('catalog:api_attempt'), json.dumps(
            {'problem_id': self.problem.pk, 'text': 'моё решение'}),
            content_type='application/json')

    def _chat_upload(self):
        return self.client.post(reverse('catalog:api_chat_upload'), {
            'problem_id': self.problem.pk,
            'file': SimpleUploadedFile('s.png', PNG, content_type='image/png')})

    def _attempt_file(self):
        return self.client.post(reverse('catalog:api_attempt_file'), {
            'file': SimpleUploadedFile('s.png', PNG, content_type='image/png')})

    def endpoints(self):
        return {'chat': self._chat, 'attempt': self._attempt,
                'chat_upload': self._chat_upload, 'attempt_file': self._attempt_file}

    # -- отказ без согласия -----------------------------------------------

    def test_without_consent_every_endpoint_refuses_and_nothing_goes_out(self):
        with mock.patch('problems.ai.core.run') as run, \
                mock.patch('problems.ai.core.run_batch', create=True) as batch:
            for name, call in self.endpoints().items():
                response = call()
                self.assertEqual(response.status_code, 403, name)
                self.assertEqual(response.json()['error'], 'ai_consent_required', name)
                self.assertIn('consent-ai', response.json()['consent_url'], name)
            self.assertEqual(run.call_count, 0)
            self.assertEqual(batch.call_count, 0)

    def test_refused_upload_stores_nothing(self):
        files_before = {p for p in Path(MEDIA).rglob('*') if p.is_file()}
        self._chat_upload()
        self._attempt_file()
        self.assertEqual(ChatAttachment.objects.count(), 0)
        self.assertEqual(FileAsset.objects.count(), 0)
        self.assertEqual({p for p in Path(MEDIA).rglob('*') if p.is_file()}, files_before)

    def test_refused_chat_writes_no_turn(self):
        from problems.models_platform import ChatTurn
        self._chat()
        self.assertEqual(ChatTurn.objects.count(), 0)

    # -- с согласием работает -----------------------------------------------

    def test_with_consent_the_chat_is_reached(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        with mock.patch('catalog.chat.answer', return_value='Начните с реакции.') as answer:
            response = self._chat()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reply'], 'Начните с реакции.')
        self.assertEqual(answer.call_count, 1)

    def test_with_consent_uploads_are_accepted(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        self.assertEqual(self._chat_upload().status_code, 200)
        self.assertEqual(self._attempt_file().status_code, 200)

    def test_with_consent_the_attempt_gets_past_the_guard(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        response = self._attempt()
        self.assertNotEqual(response.status_code, 403)

    # -- отзыв и редакция -------------------------------------------------

    def test_revoke_closes_the_chat_again(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        with mock.patch('catalog.chat.answer', return_value='ok') as answer:
            self.assertEqual(self._chat().status_code, 200)
            self.client.post(reverse('legal:ai_revoke'))
            response = self._chat()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'ai_consent_required')
        self.assertEqual(answer.call_count, 1)

    def test_old_edition_of_the_ai_consent_is_not_enough(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        with override_settings(LEGAL={**settings.LEGAL, 'docs_version': '2'}):
            consent.grant(self.user, PD, ConsentRecord.Source.GATE)
            self.assertEqual(self._chat().status_code, 403)

    def test_pd_consent_alone_does_not_open_the_assistant(self):
        self.assertTrue(consent.has_current(self.user, PD))
        self.assertEqual(self._chat().status_code, 403)

    # -- гость и поиск ----------------------------------------------------

    def test_guest_keeps_the_ordinary_login_refusal(self):
        self.client.logout()
        response = self._chat()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'login')

    def test_smart_search_does_not_need_the_consent(self):
        response = self.client.get('/catalog/api/filter-state/?q=%D0%BC%D0%BE%D0%BD%D0%BE%D0%BF%D0%BE%D0%BB%D0%B8%D1%8F')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('ai_consent_required', response.content.decode('utf-8'))

    # -- эндпоинты согласия ---------------------------------------------------

    def test_grant_endpoint_writes_a_chat_record_and_opens_the_assistant(self):
        response = self.client.post(reverse('legal:ai_grant'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        record = ConsentRecord.objects.get(user=self.user, kind=AI)
        self.assertEqual((record.source, record.version), ('chat', '1'))
        with mock.patch('catalog.chat.answer', return_value='ok'):
            self.assertEqual(self._chat().status_code, 200)

    def test_grant_from_the_profile_form_records_the_profile_source(self):
        response = self.client.post(reverse('legal:ai_grant'), {'source': 'profile'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ConsentRecord.objects.get(user=self.user, kind=AI).source, 'profile')

    def test_grant_and_revoke_need_a_post_and_a_login(self):
        self.assertEqual(self.client.get(reverse('legal:ai_grant')).status_code, 405)
        self.client.logout()
        for name in ('legal:ai_grant', 'legal:ai_revoke'):
            response = self.client.post(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].startswith('/login/'))

    def test_one_person_cannot_revoke_another_persons_consent(self):
        other = make_user('ai_other')
        consent.grant(other, AI, ConsentRecord.Source.CHAT)
        self.client.post(reverse('legal:ai_revoke'))
        self.assertTrue(consent.has_current(other, AI))


@override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
class PanelAndProfileTests(TestCase):
    def setUp(self):
        cache.clear()
        self.problem = make_problem('Условие.', title='Задача', topic=make_topic('Рынок труда'))
        self.user = make_user('panel_student')
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self.client.force_login(self.user)
        self.page = reverse('catalog:problem_detail', args=[self.problem.pk])

    @override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake')
    def test_panel_shows_the_consent_block_instead_of_the_input(self):
        html = self.client.get(self.page).content.decode('utf-8')
        self.assertIn('Помощник на основе ИИ', html)
        self.assertIn('Используя помощника, вы соглашаетесь с условиями обработки данных: '
                      'ваши сообщения и фото решений отправляются зарубежной модели.', html)
        # Две кнопки одного веса: один и тот же класс.
        self.assertIn('<button type="button" class="btn btn--quiet btn--sm" id="ai-consent-yes">Да, согласен</button>', html)
        self.assertIn('<button type="button" class="btn btn--quiet btn--sm" id="ai-consent-no">Нет, не согласен</button>', html)
        self.assertIn('<a class="ai-consent-link" href="/legal/consent-ai/" target="_blank" rel="noopener">'
                      'Условия обработки</a>', html)
        # Свёрнутая строка есть в разметке, но скрыта, пока человек не отказался.
        self.assertIn('<div class="ai-consent-off" id="ai-consent-off" hidden>', html)
        self.assertIn('Без согласия помощник не работает. Передумали?', html)
        self.assertIn('id="ai-consent-on">Включить помощника</button>', html)
        # Прежние строки остались только в полном тексте согласия.
        for gone in ('Сингапур', 'Не фотографируйте', 'Не уходят логин', 'Не сейчас',
                     'Полный текст согласия'):
            self.assertNotIn(gone, html.split('id="ai-consent"', 1)[1].split('id="ai-live"', 1)[0])
        block = html.split('id="ai-consent"', 1)[1].split('>', 1)[0]
        self.assertNotIn('hidden', block)
        live = html.split('id="ai-live"', 1)[1].split('>', 1)[0]
        self.assertIn('hidden', live)

    @override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake')
    def test_panel_is_live_after_consent(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        html = self.client.get(self.page).content.decode('utf-8')
        block = html.split('id="ai-consent"', 1)[1].split('>', 1)[0]
        live = html.split('id="ai-live"', 1)[1].split('>', 1)[0]
        self.assertIn('hidden', block)
        self.assertNotIn('hidden', live)

    @override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake')
    def test_panel_pane_response_carries_the_state_too(self):
        data = self.client.get(self.page + '?pane=1').json()
        self.assertIn('id="ai-consent"', data['help_html'])

    def test_config_hands_the_script_the_grant_url(self):
        with override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake'):
            html = self.client.get(self.page).content.decode('utf-8')
        self.assertIn(reverse('legal:ai_grant'), html)

    def test_profile_shows_the_date_and_a_revoke_button(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        html = self.client.get('/profile/?tab=data').content.decode('utf-8')
        self.assertRegex(html, r'Помощник на основе ИИ: согласие дано \d{1,2} \w+ \d{4}')
        self.assertIn(reverse('legal:ai_revoke'), html)
        self.assertIn('Отозвать', html)

    def test_profile_offers_to_give_the_consent_when_there_is_none(self):
        html = self.client.get('/profile/?tab=data').content.decode('utf-8')
        self.assertIn('согласие не дано', html)
        self.assertIn(reverse('legal:ai_grant'), html)
        self.assertNotIn(reverse('legal:ai_revoke'), html)

    def test_profile_revoke_returns_to_the_profile_and_closes_the_assistant(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        response = self.client.post(reverse('legal:ai_revoke'))
        self.assertEqual(response['Location'], '/profile/?tab=data')
        self.assertFalse(consent.has_current(self.user, AI))
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, kind=AI).count(), 1)


@override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
class TutorGenerateTests(TestCase):
    def setUp(self):
        self.tutor = make_user('gen_tutor', role='teacher')
        consent.grant(self.tutor, PD, ConsentRecord.Source.REGISTER)
        self.client.force_login(self.tutor)
        self.url = reverse('teacher:assignment_generate')
        self.body = {'step_action': 'parse', 'text': 'домашка про монополию',
                     'count_open': 2, 'count_test': 0, 'min_difficulty': 1, 'max_difficulty': 5}

    def test_homework_plan_is_refused_without_consent_and_nothing_is_sent(self):
        with mock.patch('problems.hw_generator.is_available', return_value=True), \
                mock.patch('problems.hw_generator.parse_request') as parse, \
                mock.patch('problems.ai.core.run') as run:
            response = self.client.post(self.url, self.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(parse.call_count, 0)
        self.assertEqual(run.call_count, 0)
        self.assertContains(response, 'Помощник работает на зарубежной модели', status_code=403)

    def test_homework_plan_is_reached_with_consent(self):
        consent.grant(self.tutor, AI, ConsentRecord.Source.PROFILE)
        plan = {'rows': [], 'note': ''}
        with mock.patch('problems.hw_generator.is_available', return_value=True), \
                mock.patch('problems.hw_generator.parse_request', return_value=plan) as parse:
            self.client.post(self.url, self.body)
        self.assertEqual(parse.call_count, 1)


class CallSiteInventoryTests(SimpleTestCase):
    """Инвариант: каждое место сайта, вызывающее слой ИИ, учтено.

    Перечень - таблица 2.3 отчёта инвентаризации (на сайте их 7: четыре на
    пути помощника и проверки, одно на подборе домашки, два на сортировке
    умного поиска). Новый вызов `core.run` без записи сюда краснит тест и
    требует решить: нужно ли ему согласие.
    """

    #: файл -> (сколько вызовов `core.run(`, чем закрыт).
    KNOWN = {
        'catalog/chat.py': (2, 'api_chat, api_chat_upload: @ai_consent_required'),
        'catalog/attachments.py': (1, 'api_attempt, api_attempt_file: @ai_consent_required'),
        'catalog/attempts.py': (1, 'api_attempt: @ai_consent_required'),
        'problems/hw_generator.py': (1, 'assignment_generate: проверка перед parse_request'),
        'catalog/rerank.py': (1, 'умный поиск: согласие не требуется (решение 08.10.2026)'),
    }

    def test_every_call_site_is_accounted_for(self):
        base = Path(settings.BASE_DIR)
        found = {}
        for app in ('catalog', 'problems', 'teacher', 'student', 'game', 'calc2', 'vp', 'olympiads'):
            for path in (base / app).rglob('*.py'):
                rel = path.relative_to(base).as_posix()
                if '/tests/' in rel or '/management/' in rel or '/migrations/' in rel:
                    continue
                n = len(re.findall(r'\b(?:core|ai)\.run\(', path.read_text(encoding='utf-8')))
                # Определение самого слоя ИИ не считается местом вызова.
                if n and not rel.startswith('problems/ai/'):
                    found[rel] = n
        self.assertEqual({k: v[0] for k, v in self.KNOWN.items()}, found)

    def test_every_view_that_reaches_the_model_is_decorated(self):
        text = (Path(settings.BASE_DIR) / 'catalog' / 'views.py').read_text(encoding='utf-8')
        for name in ('api_attempt_file', 'api_attempt', 'api_chat', 'api_chat_upload'):
            self.assertRegex(text, r'@ai_consent_required\ndef %s\(' % name)
        # И обратное: лишних защищённых нет, поиск и история чата согласия не требуют.
        self.assertEqual(text.count('@ai_consent_required\n'), 4)
