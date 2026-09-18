"""Чат по задаче: реплика, режимы, фото через шаг зрения, журнал, потолок, P0.

Этап 5 редизайна каталога (ADR 0080) и решение владельца 15.09.2026: у чата
свой поставщик (`CATALOG_CHAT_PROVIDER`), три режима, файл решения читает модель
зрения, каждая реплика пишется в `ChatTurn`.
"""
import io
import json
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from catalog import chat
from problems.ai import prompts
from problems.ai.providers import FakeProvider
from problems.models import AiUsageLog, CatalogAttempt, StudentGroup
from problems.models_platform import ChatAttachment, ChatTurn
from problems.tests.factories import (
    make_assignment, make_problem, make_topic, make_user,
)

MEDIA = tempfile.mkdtemp(prefix='qls_chat_media_')
SEEN = 'Q = 10 - P, [неразборчиво]'


def _capture(store, reply='Начните с функции реакции второго игрока. Что он видит?'):
    def fake(system_blocks, user_text):
        if prompts.CATALOG_CHAT_VISION in system_blocks:
            store['vision_text'] = user_text
            return json.dumps({'text': SEEN}, ensure_ascii=False)
        store['text'] = user_text
        store['system'] = ' '.join(system_blocks)
        store['blocks'] = list(system_blocks)
        return json.dumps({'reply': reply}, ensure_ascii=False)
    return fake


class RecordingProvider(FakeProvider):
    """Подставной поставщик, который помнит каждый вызов: модель и картинки."""

    def __init__(self):
        self.calls = []

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 timeout=None, images=None):
        self.calls.append({'model': model, 'images': list(images or []),
                           'system': list(system_blocks), 'text': user_text})
        return super().complete(system_blocks, user_text, schema, model, max_tokens,
                                timeout=timeout, images=images)


def _png_bytes(size=(20, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (255, 255, 255)).save(buf, 'PNG')
    return buf.getvalue()


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='glm-5.3-flash', MEDIA_ROOT=MEDIA)
class ChatApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.topic = make_topic('Олигополия и теория игр')
        self.problem = make_problem('Две фирмы выбирают выпуск последовательно.',
                                    title='Штакельберг', topic=self.topic, answer='q1 = 30',
                                    solution='Эталон: лидер выбирает q1 = 30, ведомый отвечает 15.')
        self.user = make_user('маша', first_name='Мария', email='masha@example.org')
        self.teacher = make_user('репетитор', role='teacher')
        self.url = reverse('catalog:api_chat')
        self.page = reverse('catalog:problem_detail', args=[self.problem.pk])

    def _post(self, message='С чего начать?', history=None, **extra):
        body = {'problem_id': self.problem.pk, 'message': message, 'history': history or []}
        body.update(extra)
        return self.client.post(self.url, json.dumps(body), content_type='application/json')

    def test_reply_comes_back_and_prompt_has_no_profile_fields(self):
        from problems.tests.profile_markers import FORBIDDEN, fill_profile_with_markers
        fill_profile_with_markers(self.user)
        self.client.force_login(self.user)
        seen = {}
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            data = json.loads(self._post(history=[{'role': 'me', 'text': 'Привет'},
                                                  {'role': 'ai', 'text': 'Здравствуйте'}]).content)
        self.assertEqual(data['reply'], 'Начните с функции реакции второго игрока. Что он видит?')
        self.assertEqual(data['remaining'], 29)
        text = seen['text']
        for present in ('Две фирмы выбирают выпуск последовательно.', 'Ученик: Привет',
                        'Помощник: Здравствуйте', 'ВОПРОС УЧЕНИКА:', 'С чего начать?'):
            self.assertIn(present, text)
        for absent in ('Мария', 'masha@example.org', 'маша') + FORBIDDEN:
            self.assertNotIn(absent, text)
            self.assertNotIn(absent, seen['system'])
        self.assertNotIn(chat.HOMEWORK_MODE, text)
        self.assertNotIn('q1 = 30', text)   # ответ задачи помощнику не даётся

    def test_last_attempt_and_its_result_reach_the_helper(self):
        self.client.force_login(self.user)
        CatalogAttempt.objects.create(user=self.user, problem=self.problem, text='q1 = 45',
                                      status='checked', verdict='wrong', score=2,
                                      steps=[{'n': 1, 'title': 'Выбор лидера', 'verdict': 'bad',
                                              'comment': ''}], first_error_step=1)
        seen = {}
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            self._post('Почему неверно?')
        self.assertIn('ПОСЛЕДНЯЯ ПОПЫТКА УЧЕНИКА:', seen['text'])
        self.assertIn('q1 = 45', seen['text'])
        self.assertIn('РЕЗУЛЬТАТ ПРОВЕРКИ: неверно, 2 из 10; первая ошибка в шаге 1: Выбор лидера',
                      seen['text'])

    def test_homework_mode_for_open_assignment_by_list_and_by_group(self):
        self.client.force_login(self.user)
        seen = {}
        make_assignment(self.teacher, students=[self.user], problems=[self.problem],
                        deadline=timezone.now() + timedelta(days=3))
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            self._post()
        self.assertIn(chat.HOMEWORK_MODE, seen['text'])
        self.assertIn('ТОЛЬКО НАВОДЯЩИЕ ВОПРОСЫ', seen['system'])

    def test_homework_mode_via_group_and_not_after_deadline(self):
        self.client.force_login(self.user)
        group = StudentGroup.objects.create(teacher=self.teacher, name='9А')
        group.students.add(self.user)
        closed = make_assignment(self.teacher, problems=[self.problem],
                                 deadline=timezone.now() - timedelta(days=1))
        closed.group = group
        closed.save(update_fields=['group'])
        self.assertFalse(chat.in_active_homework(self.user, self.problem))
        open_work = make_assignment(self.teacher, problems=[self.problem], deadline=None)
        open_work.group = group
        open_work.save(update_fields=['group'])
        self.assertTrue(chat.in_active_homework(self.user, self.problem))

    def test_anonymous_gets_403_and_a_login_link_instead_of_the_field(self):
        html = self.client.get(self.page).content.decode()
        self.assertIn('<aside class="help-panel"', html)
        self.assertNotIn('id="ai-text"', html)
        self.assertIn('Войти, чтобы спросить', html)
        self.assertEqual(self._post().status_code, 403)

    def test_logged_in_page_has_three_mode_buttons_and_a_paperclip(self):
        self.client.force_login(self.user)
        html = self.client.get(self.page).content.decode()
        for needle in ('id="ai-text"', 'id="ai-send"',
                       # Режимы по README §4: «Теория / Как решать / Проверь решение»;
                       # текст реплики без набранного вопроса — в data-prompt.
                       'data-mode="theory" data-prompt="Объясни теорию">Теория<',
                       'data-mode="method" data-prompt="Как решать">Как решать<',
                       'data-mode="check" data-prompt="Проверь моё решение">Проверь решение<', 'id="ai-clip"',
                       # `multiple` — до трёх файлов к реплике (18.09.2026).
                       '<input type="file" id="ai-file" multiple hidden accept=".jpg,.jpeg,.png,.webp,.pdf,'
                       'image/jpeg,image/png,image/webp,application/pdf">',
                       '"chatUrl": "/catalog/api/chat/"',
                       '"chatUploadUrl": "/catalog/api/chat/upload/"'):
            self.assertTrue(needle in html, 'нет на странице: %s' % needle)
        self.assertFalse('data-q=' in html, 'старые подсказки-вопросы остались')

    @override_settings(AI_GENERATOR_DAILY_LIMIT=1)
    def test_limit_is_shared_with_the_check_and_is_a_human_reply(self):
        self.client.force_login(self.user)
        with override_settings(AI_FAKE_REPLY=_capture({})):
            self.assertEqual(json.loads(self._post().content)['remaining'], 0)
            data = json.loads(self._post('Ещё вопрос').content)
        self.assertEqual(data['error'], 'limit')
        self.assertEqual(data['reply'], 'Лимит проверок на сегодня исчерпан: завтра снова 1')

    def test_history_is_trimmed_and_reply_is_capped(self):
        history = [{'role': 'me', 'text': 'реплика %d' % i} for i in range(10)]
        self.assertEqual([h['text'] for h in chat.clean_history(history)],
                         ['реплика %d' % i for i in range(4, 10)])
        self.client.force_login(self.user)
        # Потолки — предохранитель (18.09.2026: 8 000 и 10 000): длиннее — режется.
        with override_settings(AI_FAKE_REPLY=_capture({}, reply='x' * 12000)):
            self.assertEqual(len(json.loads(self._post().content)['reply']), chat.REPLY_MAX)
            data = json.loads(self._post('Вот решение: q1 = 30', mode='check').content)
        self.assertEqual(len(data['reply']), chat.CHECK_REPLY_MAX)

    @override_settings(CATALOG_CHAT_PROVIDER='glm')
    def test_without_chat_key_page_has_no_chat_card(self):
        # Ключи поставщиков в тестах погашены (config/test_runner.py): это и есть
        # «на сервере не задан GLM_API_KEY».
        self.client.force_login(self.user)
        resp = self.client.get(self.page)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Поле помощи без чата остаётся только для проверки решения (S3, 18.09.2026):
        # ни разговора, ни режимов «Теория» и «Как решать».
        for absent in ('Спросить ИИ', 'chatUrl', 'chatUploadUrl', 'data-mode="theory"', 'data-mode="method"'):
            self.assertFalse(absent in html, 'без ключа чата на странице: %s' % absent)


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='glm-5.3-flash', MEDIA_ROOT=MEDIA)
class ChatModeTests(TestCase):
    """Режимы: блок режима, эталон только в «Проверь моё решение», P0 в каждом."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Две фирмы выбирают выпуск последовательно.', answer='q1 = 30',
                                    solution='Эталон: лидер выбирает q1 = 30, ведомый отвечает 15.')
        self.user = make_user('маша', first_name='Мария', email='masha@example.org')
        self.client.force_login(self.user)

    def _post(self, **body):
        body.setdefault('problem_id', self.problem.pk)
        return self.client.post(reverse('catalog:api_chat'), json.dumps(body),
                                content_type='application/json')

    def test_each_mode_adds_its_block_and_only_check_sees_the_reference(self):
        for mode in ('free', 'theory', 'method', 'check'):
            seen = {}
            with self.subTest(mode=mode), override_settings(AI_FAKE_REPLY=_capture(seen)):
                self._post(message='Помогите с задачей', mode=mode)
                blocks = seen['blocks']
                self.assertEqual(blocks[:2], prompts.system_blocks('catalog_chat'))
                if mode == 'free':
                    self.assertEqual(len(blocks), 2)
                else:
                    self.assertEqual(blocks[2], prompts.CATALOG_CHAT_MODES[mode])
                reference = 'q1 = 30' in seen['system'] and 'ведомый отвечает 15' in seen['system']
                self.assertEqual(reference, mode == 'check', 'эталон не там, где нужно')
                self.assertFalse('q1 = 30' in seen['text'], 'эталон попал в текст запроса')
                for absent in ('Мария', 'masha@example.org', 'маша'):
                    self.assertFalse(absent in seen['text'] or absent in seen['system'],
                                     'данные профиля ушли в модель: %s' % absent)

    def test_unknown_mode_is_plain_question(self):
        seen = {}
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            self._post(message='Что это?', mode='hack')
        self.assertEqual(len(seen['blocks']), 2)
        self.assertEqual(ChatTurn.objects.get().mode, 'free')

    def test_check_without_text_and_file_is_a_hint_not_a_request(self):
        with override_settings(AI_FAKE_REPLY=_capture({})):
            resp = self._post(message='', mode='check')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)['reply'], chat.CHECK_EMPTY_TEXT)
        self.assertFalse(ChatTurn.objects.exists())


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='glm-5.3-flash', MEDIA_ROOT=MEDIA)
class ChatJournalTests(TestCase):
    """Каждая реплика — строка `ChatTurn`: при ответе, при ошибке, при потолке."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Найдите равновесие.', answer='40')
        self.user = make_user('ученик')
        self.client.force_login(self.user)

    def _post(self, **body):
        body.setdefault('problem_id', self.problem.pk)
        body.setdefault('message', 'С чего начать?')
        return self.client.post(reverse('catalog:api_chat'), json.dumps(body),
                                content_type='application/json')

    def test_turn_is_written_with_mode_model_tokens_and_thread(self):
        thread = uuid.uuid4()
        with override_settings(AI_FAKE_REPLY=_capture({}, reply='Начните с условия равновесия.')):
            self._post(mode='method', thread=str(thread))
        turn = ChatTurn.objects.get()
        self.assertEqual((turn.user, turn.problem, turn.mode, turn.thread),
                         (self.user, self.problem, 'method', thread))
        self.assertEqual((turn.user_text, turn.reply), ('С чего начать?', 'Начните с условия равновесия.'))
        self.assertEqual((turn.provider, turn.model, turn.error), ('fake', 'glm-5.3', ''))
        self.assertTrue(turn.input_tokens > 0 and turn.output_tokens > 0, 'токены не записаны')

    def test_turn_is_written_when_the_provider_fails(self):
        with override_settings(AI_FAKE_REPLY=RuntimeError('сервис лёг')):
            data = json.loads(self._post(thread='не-uuid').content)
        self.assertEqual(data['error'], 'other')
        turn = ChatTurn.objects.get()
        self.assertEqual(turn.reply, '')
        self.assertTrue('сервис лёг' in turn.error, 'ошибка поставщика не записана')
        self.assertIsNone(turn.thread)

    @override_settings(AI_DAILY_COST_CAPS={'catalog_chat': 1.0})
    def test_spent_budget_is_a_human_message_not_500(self):
        AiUsageLog.objects.create(user=None, kind='catalog_chat', model_name='glm-5.3',
                                  cost_usd=Decimal('1.2'))
        with override_settings(AI_FAKE_REPLY=_capture({})):
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual((data['error'], data['reply']), ('budget', chat.BUDGET_TEXT))
        self.assertTrue(ChatTurn.objects.get().error.startswith('limit'), 'отказ не записан')


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='glm-5.3-flash', MEDIA_ROOT=MEDIA)
class ChatVisionTests(TestCase):
    """Фото решения: сначала модель зрения, её расшифровка — в текст для модели чата."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Найдите равновесие.', answer='40')
        self.user = make_user('ученик')
        self.client.force_login(self.user)
        self.provider = RecordingProvider()
        patcher = mock.patch('catalog.chat.chat_provider', return_value=self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _attach(self, user=None, problem=None):
        return ChatAttachment.objects.create(
            user=user or self.user, problem=problem or self.problem, mime='image/png',
            file=SimpleUploadedFile('a.png', _png_bytes()), pages=1)

    def _post(self, attachment, **body):
        attachment.pages_json = [attachment.file.name]
        attachment.save(update_fields=['pages_json'])
        body.update(problem_id=self.problem.pk, attachment_id=attachment.pk)
        body.setdefault('message', 'Проверь моё решение')
        return self.client.post(reverse('catalog:api_chat'), json.dumps(body),
                                content_type='application/json')

    def test_photo_is_read_by_vision_model_then_chat_gets_the_transcript(self):
        attachment = self._attach()
        with override_settings(AI_FAKE_REPLY=_capture({})):
            self._post(attachment, mode='check')
        vision, talk = self.provider.calls
        self.assertEqual(vision['model'], 'glm-5.3-flash')
        self.assertEqual([mime for mime, _data in vision['images']], ['image/png'])
        self.assertTrue(prompts.CATALOG_CHAT_VISION in vision['system'])
        self.assertEqual((talk['model'], talk['images']), ('glm-5.3', []))
        self.assertTrue(chat.VISION_MARK + '\n' + SEEN in talk['text'], 'расшифровки нет в реплике')
        turn = ChatTurn.objects.get()
        self.assertEqual((turn.vision_text, turn.attachment), (SEEN, attachment))
        self.assertTrue(turn.vision_input_tokens > 0, 'токены зрения не записаны')

    @override_settings(CATALOG_CHAT_VISION_MODEL='')
    def test_without_vision_model_the_photo_goes_straight_to_chat(self):
        with override_settings(AI_FAKE_REPLY=_capture({})):
            self._post(self._attach())
        (talk,) = self.provider.calls
        self.assertEqual(len(talk['images']), 1)
        self.assertEqual(ChatTurn.objects.get().vision_text, '')

    def test_someone_elses_or_other_problem_attachment_is_refused(self):
        other = make_user('чужой')
        for attachment in (self._attach(user=other),
                           self._attach(problem=make_problem('Другая задача.'))):
            with self.subTest(owner=attachment.user_id, problem=attachment.problem_id):
                resp = self._post(attachment)
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(json.loads(resp.content)['error'], 'file')
        self.assertEqual(self.provider.calls, [])
        self.assertFalse(ChatTurn.objects.exists())
