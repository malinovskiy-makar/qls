"""Помощник ИИ перед бетой (18.09.2026): TeX, длина, несколько файлов,
просмотр своего вложения, PDF, история разговора и цитата условия.

Сторожа P0 (профиль и эталон не в тексте запроса) живут в `test_chat_api`,
здесь — только новое поведение.
"""
import io
import json
import tempfile
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalog import chat
from problems.ai import prompts
from problems.ai.providers import FakeProvider
from problems.models_platform import ChatAttachment, ChatTurn
from problems.tests.factories import make_problem, make_user

MEDIA = tempfile.mkdtemp(prefix='qls_chat_beta_')


def _png_bytes(size=(20, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (255, 255, 255)).save(buf, 'PNG')
    return buf.getvalue()


def _pdf_bytes(pages, password=None):
    import fitz
    doc = fitz.open()
    for number in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 72), 'Page %d' % (number + 1))
    if password:
        data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password,
                           owner_pw=password)
    else:
        data = doc.tobytes()
    doc.close()
    return data


def _reply(text):
    def fake(system_blocks, user_text):
        if prompts.CATALOG_CHAT_VISION in system_blocks:
            return json.dumps({'text': 'расшифровка'}, ensure_ascii=False)
        return json.dumps({'reply': text}, ensure_ascii=False)
    return fake


class RecordingProvider(FakeProvider):
    """Подставной поставщик: помнит системные блоки, текст, картинки и токены."""

    def __init__(self):
        self.calls = []

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 timeout=None, images=None):
        self.calls.append({'system': list(system_blocks), 'text': user_text,
                           'images': list(images or []), 'max_tokens': max_tokens})
        return super().complete(system_blocks, user_text, schema, model, max_tokens,
                                timeout=timeout, images=images)


class _ChatCase(TestCase):
    def setUp(self):
        cache.clear()
        self.problem = make_problem('Монополист выбирает выпуск.', answer='Q = 10')
        self.user = make_user('бета_ученик')
        self.client.force_login(self.user)
        self.provider = RecordingProvider()
        patcher = mock.patch('catalog.chat.chat_provider', return_value=self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, **body):
        body.setdefault('problem_id', self.problem.pk)
        body.setdefault('message', 'С чего начать?')
        return self.client.post(reverse('catalog:api_chat'), json.dumps(body),
                                content_type='application/json')

    def _attach(self, pages=1, user=None, problem=None, mime='image/png', name='тетрадь.png'):
        attachment = ChatAttachment.objects.create(
            user=user or self.user, problem=problem or self.problem, mime=mime, name=name,
            file=SimpleUploadedFile('a.png', _png_bytes()), pages=pages)
        attachment.pages_json = [attachment.file.name] * pages
        attachment.save(update_fields=['pages_json'])
        return attachment

    def _talk(self):
        """Последний вызов модели чата (не зрения)."""
        return [c for c in self.provider.calls
                if prompts.CATALOG_CHAT_VISION not in c['system']][-1]


class PromptFormatTests(TestCase):
    """Пункт 3 профиля чата: формулы в TeX, длина не задаётся."""

    def test_chat_profile_asks_for_inline_and_display_tex(self):
        system = ' '.join(chat.system_for(make_problem('Условие.'), 'free'))
        self.assertIn('$…$', system)
        self.assertIn('$$…$$', system)

    def test_no_length_limits_left_in_any_mode(self):
        for mode in chat.MODES:
            system = ' '.join(chat.system_for(make_problem('Условие.'), mode))
            self.assertNotIn('900', system, mode)
            self.assertNotIn('1 200', system, mode)

    def test_rules_that_hide_the_answer_are_intact(self):
        profile = ' '.join(prompts.system_blocks('catalog_chat'))
        self.assertIn('НЕ выдавай итоговый ответ и полное решение', profile)
        self.assertIn('РЕЖИМ: ТОЛЬКО НАВОДЯЩИЕ ВОПРОСЫ', profile)


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='', MEDIA_ROOT=MEDIA)
class ReplyLengthTests(_ChatCase):

    def test_five_thousand_characters_arrive_whole(self):
        text = ('Предложение с формулой $MC = 2q$ номер один. ' * 120)[:5000].strip()
        with override_settings(AI_FAKE_REPLY=_reply(text)):
            self.assertEqual(json.loads(self._post().content)['reply'], text)

    def test_overlong_reply_is_cut_at_a_sentence_boundary(self):
        text = ' '.join('Шаг %d решения описан словами.' % i for i in range(400))
        self.assertGreater(len(text), 9000)
        with override_settings(AI_FAKE_REPLY=_reply(text)):
            reply = json.loads(self._post().content)['reply']
        self.assertLessEqual(len(reply), chat.REPLY_MAX)
        self.assertTrue(reply.endswith('словами.' + chat.CUT_MARK), reply[-40:])

    def test_cut_without_sentence_ends_on_a_whole_word(self):
        cut = chat.cut_reply('слово ' * 2000, 100)
        self.assertTrue(cut.endswith('слово' + chat.CUT_MARK), cut)

    def test_provider_is_asked_for_three_thousand_tokens(self):
        with override_settings(AI_FAKE_REPLY=_reply('Ответ.')):
            self._post()
        self.assertEqual(self._talk()['max_tokens'], chat.CHAT_MAX_TOKENS)
        self.assertEqual(chat.CHAT_MAX_TOKENS, 3000)


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='', MEDIA_ROOT=MEDIA)
class SeveralFilesTests(_ChatCase):

    def test_three_files_are_linked_to_the_turn(self):
        files = [self._attach() for _ in range(3)]
        with override_settings(AI_FAKE_REPLY=_reply('Вижу.')):
            self.assertEqual(self._post(attachment_ids=[f.pk for f in files]).status_code, 200)
        turn = ChatTurn.objects.get()
        self.assertEqual(set(turn.attachments.all()), set(files))
        self.assertEqual(turn.attachment, files[0])

    def test_four_files_are_refused(self):
        files = [self._attach() for _ in range(4)]
        resp = self._post(attachment_ids=[f.pk for f in files])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['reply'], chat.TOO_MANY_FILES)

    def test_six_pages_send_five_pictures_and_an_honest_note(self):
        first, second = self._attach(pages=3), self._attach(pages=3)
        with override_settings(AI_FAKE_REPLY=_reply('Вижу.')):
            data = self._post(attachment_ids=[first.pk, second.pk]).json()
        self.assertEqual(len(self._talk()['images']), chat.VISION_PAGES_MAX)
        self.assertEqual(data['note'], chat.PAGES_NOTE)
        self.assertIn(chat.PAGES_NOTE, self._talk()['text'])

    def test_someone_elses_file_is_refused(self):
        stranger = make_user('чужой')
        mine, theirs = self._attach(), self._attach(user=stranger)
        resp = self._post(attachment_ids=[mine.pk, theirs.pk])
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(ChatTurn.objects.exists())

    def test_old_single_attachment_id_still_works(self):
        attachment = self._attach()
        with override_settings(AI_FAKE_REPLY=_reply('Вижу.')):
            self.assertEqual(self._post(attachment_id=attachment.pk).status_code, 200)
        self.assertEqual(ChatTurn.objects.get().attachment, attachment)

    def test_page_offers_several_files(self):
        html = self.client.get(reverse('catalog:problem_detail', args=[self.problem.pk])).content.decode()
        self.assertRegex(html, r'<input type="file" id="ai-file" multiple')


@override_settings(MEDIA_ROOT=MEDIA)
class AttachmentViewTests(_ChatCase):

    def _get(self, pk):
        return self.client.get(reverse('catalog:chat_attachment', args=[pk]))

    def test_owner_gets_the_file_with_its_stored_type(self):
        attachment = self._attach()
        resp = self._get(attachment.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/png')
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')
        self.assertTrue(resp['Content-Disposition'].startswith('inline'))
        self.assertIn('private', resp['Cache-Control'])

    def test_pdf_is_downloaded_not_opened_on_our_domain(self):
        attachment = self._attach(mime='application/pdf', name='решение.pdf')
        resp = self._get(attachment.pk)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp['Content-Disposition'].startswith('attachment'))

    def test_someone_elses_file_is_404(self):
        attachment = self._attach(user=make_user('другой'))
        self.assertEqual(self._get(attachment.pk).status_code, 404)

    def test_guest_gets_404_not_a_login_redirect(self):
        attachment = self._attach()
        self.client.logout()
        self.assertEqual(self._get(attachment.pk).status_code, 404)

    def test_missing_file_is_404(self):
        self.assertEqual(self._get(999999).status_code, 404)

    def test_staff_can_open_any_file(self):
        attachment = self._attach(user=make_user('третий'))
        staff = make_user('сотрудник')
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        self.assertEqual(self._get(attachment.pk).status_code, 200)


class PdfTests(TestCase):

    def test_seven_page_pdf_gives_five_pictures(self):
        self.assertEqual(len(chat.derived_images(_pdf_bytes(7), 'application/pdf')),
                         chat.VISION_PAGES_MAX)

    def test_password_pdf_is_refused_honestly(self):
        with self.assertRaisesMessage(ValueError, chat.BAD_PDF):
            chat.derived_images(_pdf_bytes(1, password='secret'), 'application/pdf')

    def test_empty_pdf_is_refused_honestly(self):
        with self.assertRaisesMessage(ValueError, chat.BAD_PDF):
            chat.derived_images(b'', 'application/pdf')


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   CATALOG_CHAT_VISION_MODEL='', MEDIA_ROOT=MEDIA)
class HistoryAndQuoteTests(_ChatCase):

    def _history(self, problem=None):
        return self.client.get(reverse('catalog:api_chat_history',
                                       args=[(problem or self.problem).pk]))

    def test_own_history_comes_back_in_order(self):
        with override_settings(AI_FAKE_REPLY=_reply('Первый ответ.')):
            self._post(message='Первый вопрос')
        with override_settings(AI_FAKE_REPLY=_reply('Второй ответ.')):
            self._post(message='Второй вопрос')
        turns = self._history().json()['turns']
        self.assertEqual([t['message'] for t in turns], ['Первый вопрос', 'Второй вопрос'])
        self.assertEqual(turns[1]['reply'], 'Второй ответ.')

    def test_someone_elses_history_is_empty(self):
        with override_settings(AI_FAKE_REPLY=_reply('Ответ.')):
            self._post()
        self.client.force_login(make_user('сосед'))
        self.assertEqual(self._history().json()['turns'], [])

    def test_guest_gets_401(self):
        self.client.logout()
        self.assertEqual(self._history().status_code, 401)

    def test_history_lists_attachments_with_view_links(self):
        attachment = self._attach(name='лист.png')
        with override_settings(AI_FAKE_REPLY=_reply('Вижу.')):
            self._post(attachment_ids=[attachment.pk])
        files = self._history().json()['turns'][0]['attachments']
        self.assertEqual(files[0]['name'], 'лист.png')
        self.assertEqual(files[0]['url'], reverse('catalog:chat_attachment', args=[attachment.pk]))

    def test_quote_goes_into_the_text_not_the_system_block(self):
        with override_settings(AI_FAKE_REPLY=_reply('Ответ.')):
            self._post(quote='выпуск максимизирует прибыль')
        talk = self._talk()
        self.assertIn('Фрагмент условия: «выпуск максимизирует прибыль»', talk['text'])
        self.assertNotIn('выпуск максимизирует прибыль', ' '.join(talk['system']))

    def test_quote_over_three_hundred_is_refused(self):
        self.assertEqual(self._post(quote='я' * 301).status_code, 400)
