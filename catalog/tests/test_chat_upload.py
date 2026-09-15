"""Фото и PDF решения к реплике чата: проверка загрузки, картинки для модели, лимит.

Решение владельца 15.09.2026: jpg/png/webp/pdf до 10 МБ, магия файла, 10 файлов в
сутки; PDF — первые пять страниц в PNG шириной 1 400 px, большая картинка —
JPEG до 1 600 px по большей стороне.
"""
import io
import tempfile

from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalog import attachments, chat
from problems.models import Problem
from problems.models_platform import ChatAttachment
from problems.tests.factories import make_problem, make_user

MEDIA = tempfile.mkdtemp(prefix='qls_chat_upload_')


def _png(name='тетрадь.png', size=(20, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (255, 255, 255)).save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def _pdf(pages):
    import fitz

    doc = fitz.open()
    for number in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 72), 'Page %d' % (number + 1))
    data = doc.tobytes()
    doc.close()
    return SimpleUploadedFile('решение.pdf', data, content_type='application/pdf')


@override_settings(MEDIA_ROOT=MEDIA)
class ChatUploadTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('фотограф')
        self.problem = make_problem('Найдите равновесие.')
        self.url = reverse('catalog:api_chat_upload')
        self.client.force_login(self.user)

    def _upload(self, file, problem=None):
        return self.client.post(self.url, {'file': file,
                                           'problem_id': (problem or self.problem).pk})

    def _sizes(self, attachment):
        sizes = []
        for path in attachment.pages_json:
            with default_storage.open(path, 'rb') as handle, Image.open(handle) as image:
                sizes.append(image.size)
        return sizes

    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self._upload(_png()).status_code, 403)
        self.assertFalse(ChatAttachment.objects.exists())

    def test_hidden_problem_is_404(self):
        hidden = make_problem('Черновик.', status=Problem.Status.DRAFT)
        self.assertEqual(self._upload(_png(), problem=hidden).status_code, 404)

    def test_small_photo_is_saved_under_our_name_and_goes_as_is(self):
        resp = self._upload(_png())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        attachment = ChatAttachment.objects.get(pk=data['id'])
        self.assertEqual((data['mime'], data['pages'], data['name']), ('image/png', 1, 'тетрадь.png'))
        self.assertEqual((attachment.user, attachment.problem), (self.user, self.problem))
        self.assertTrue(attachment.file.name.startswith('chat/'), attachment.file.name)
        self.assertFalse('тетрадь' in attachment.file.name, 'имя файла ученика попало в хранилище')
        self.assertEqual(attachment.pages_json, [attachment.file.name])

    def test_wrong_type_fake_image_and_big_file_are_refused(self):
        big = SimpleUploadedFile('большое.pdf', b'%PDF' + b'0' * (attachments.MAX_BYTES + 1),
                                 content_type='application/pdf')
        for file, message in ((SimpleUploadedFile('решение.docx', b'PK\x03\x04'), attachments.WRONG_TYPE),
                              (SimpleUploadedFile('фото.png', b'not an image'), attachments.WRONG_TYPE),
                              (big, attachments.TOO_BIG)):
            with self.subTest(name=file.name):
                resp = self._upload(file)
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.json()['message'], message)
        self.assertFalse(ChatAttachment.objects.exists())

    def test_pdf_of_two_pages_becomes_two_png_1400_wide(self):
        attachment = ChatAttachment.objects.get(pk=self._upload(_pdf(2)).json()['id'])
        self.assertEqual(attachment.pages, 2)
        self.assertTrue(all(path.endswith('.png') for path in attachment.pages_json))
        for width, _height in self._sizes(attachment):
            self.assertTrue(abs(width - chat.PDF_WIDTH) <= 1, 'ширина страницы %d' % width)
        images = chat.attachment_images(attachment)
        self.assertEqual([mime for mime, _data in images], ['image/png', 'image/png'])

    def test_only_first_five_pdf_pages_go_to_the_model(self):
        data = self._upload(_pdf(7)).json()
        self.assertEqual(data['pages'], chat.VISION_PAGES_MAX)

    def test_broken_pdf_is_refused(self):
        resp = self._upload(SimpleUploadedFile('битый.pdf', b'%PDF-1.4 garbage'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['message'], chat.BAD_PDF)
        self.assertFalse(ChatAttachment.objects.exists())

    def test_big_photo_is_shrunk_to_jpeg_1600(self):
        attachment = ChatAttachment.objects.get(
            pk=self._upload(_png('доска.png', size=(2400, 1200))).json()['id'])
        self.assertTrue(attachment.pages_json[0].endswith('.jpg'), attachment.pages_json)
        self.assertEqual(self._sizes(attachment), [(1600, 800)])
        self.assertEqual(chat.attachment_images(attachment)[0][0], 'image/jpeg')

    def test_eleventh_file_of_the_day_is_refused(self):
        for _ in range(chat.UPLOADS_PER_DAY):
            ChatAttachment.objects.create(user=self.user, problem=self.problem,
                                          file='chat/x.png', mime='image/png')
        resp = self._upload(_png())
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()['message'], chat.TOO_MANY_UPLOADS)
        # Лимит — на человека: у другого ученика свой счёт.
        self.client.force_login(make_user('другой'))
        self.assertEqual(self._upload(_png()).status_code, 200)
