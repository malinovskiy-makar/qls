"""Журнал чата: админка только сотрудникам, файл решения — третья файловая вьюха,
выгрузка `chat_export` по разговорам без полей профиля.

Решение владельца 15.09.2026. Таблица «ресурс × роль × действие» (скилл
`weco-security-boundary-review`), каждая клетка закрыта тестом ниже:

| ресурс                          | гость | ученик | сотрудник без права | суперпользователь |
|---------------------------------|-------|--------|---------------------|-------------------|
| список реплик в админке         | вход  | вход   | 403                 | 200               |
| файл решения `…/<pk>/file/`     | вход  | вход   | 403                 | 200               |
| загрузка `/catalog/api/chat/upload/` | 403 | 200 (своё) | —            | —                 |
| реплика с чужим вложением       | 403   | 400    | —                   | —                 |

(две последние строки — `catalog/tests/test_chat_upload.py` и `test_chat_api.py`).
"""
import io
import json
import os
import tempfile
import uuid
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from problems.models_platform import ChatAttachment, ChatTurn
from problems.tests.factories import make_problem, make_user

MEDIA = tempfile.mkdtemp(prefix='qls_chat_journal_')


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), (0, 0, 0)).save(buf, 'PNG')
    return buf.getvalue()


@override_settings(MEDIA_ROOT=MEDIA)
class ChatAdminTests(TestCase):
    def setUp(self):
        self.student = make_user('ученица', first_name='Ольга', email='olga@example.org')
        self.problem = make_problem('Найдите равновесие.')
        self.png = ChatAttachment.objects.create(
            user=self.student, problem=self.problem, mime='image/png', pages=1,
            file=SimpleUploadedFile('a.png', _png()))
        self.pdf = ChatAttachment.objects.create(
            user=self.student, problem=self.problem, mime='application/pdf', pages=1,
            file=SimpleUploadedFile('b.pdf', b'%PDF-1.4 x'))
        self.turn = ChatTurn.objects.create(user=self.student, problem=self.problem,
                                            mode='check', user_text='Проверь моё решение',
                                            attachment=self.png, reply='Первая ошибка в шаге 2.')
        self.pdf_turn = ChatTurn.objects.create(user=self.student, problem=self.problem,
                                                user_text='вот PDF', attachment=self.pdf)
        self.list_url = reverse('admin:problems_chatturn_changelist')

    def file_url(self, turn):
        return reverse('admin:problems_chatturn_file', args=[turn.pk])

    def test_guest_and_student_are_sent_to_login(self):
        for login in (None, self.student):
            if login:
                self.client.force_login(login)
            with self.subTest(who=getattr(login, 'username', 'гость')):
                for url in (self.list_url, self.file_url(self.turn)):
                    self.assertEqual(self.client.get(url).status_code, 302)

    def test_staff_without_view_right_gets_403(self):
        self.client.force_login(make_user('сотрудник', is_staff=True))
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.get(self.file_url(self.turn)).status_code, 403)

    def test_superuser_sees_turns_and_opens_the_files(self):
        self.client.force_login(make_user('админ', is_staff=True, is_superuser=True))
        page = self.client.get(self.list_url).content.decode()
        self.assertTrue('Проверь моё решение' in page, 'реплики нет в списке')
        change = self.client.get(reverse('admin:problems_chatturn_change', args=[self.turn.pk]))
        self.assertTrue(self.file_url(self.turn) in change.content.decode(), 'нет ссылки на файл')
        image = self.client.get(self.file_url(self.turn))
        self.assertEqual((image.status_code, image['Content-Type']), (200, 'image/png'))
        self.assertEqual(b''.join(image.streaming_content), _png())
        pdf = self.client.get(self.file_url(self.pdf_turn))
        self.assertTrue(pdf['Content-Disposition'].startswith('attachment'),
                        'PDF ученика открывается на нашем домене')

    def test_turn_without_file_is_404(self):
        self.client.force_login(make_user('админ', is_staff=True, is_superuser=True))
        bare = ChatTurn.objects.create(user=self.student, problem=self.problem, user_text='вопрос')
        self.assertEqual(self.client.get(self.file_url(bare)).status_code, 404)


class ChatExportTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = os.path.join(tmp.name, 'chat.jsonl')
        self.student = make_user('ученица', first_name='Ольга', email='olga@example.org')
        self.problem = make_problem('Найдите равновесие.')

    def turn(self, text, thread=None, days_ago=0):
        turn = ChatTurn.objects.create(user=self.student, problem=self.problem, thread=thread,
                                       user_text=text, reply='ответ на «%s»' % text)
        ChatTurn.objects.filter(pk=turn.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago))
        return turn

    def export(self, *args):
        call_command('chat_export', *args, out=self.out, stdout=io.StringIO())
        with open(self.out, encoding='utf-8') as handle:
            return [json.loads(line) for line in handle]

    def test_turns_are_grouped_by_thread_in_order_without_profile_fields(self):
        thread = uuid.uuid4()
        self.turn('первая', thread)
        self.turn('вторая', thread)
        self.turn('без разговора')
        rows = self.export('--since', timezone.localdate().isoformat())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['thread'], str(thread))
        self.assertEqual([t['user_text'] for t in rows[0]['turns']], ['первая', 'вторая'])
        self.assertEqual(rows[0]['user_id'], self.student.pk)
        text = json.dumps(rows, ensure_ascii=False)
        for absent in ('ученица', 'Ольга', 'olga@example.org'):
            self.assertFalse(absent in text, 'в выгрузке поле профиля: %s' % absent)

    def test_since_and_until_bound_the_days(self):
        self.turn('позавчера', days_ago=2)
        self.turn('вчера', days_ago=1)
        self.turn('сегодня')
        today = timezone.localdate()
        # --until включительно: «вчера» при --until вчерашним днём входит.
        rows = self.export('--since', (today - timedelta(days=3)).isoformat(),
                           '--until', (today - timedelta(days=1)).isoformat())
        self.assertEqual([row['turns'][0]['user_text'] for row in rows], ['позавчера', 'вчера'])
