"""Выгрузка разговоров беты и читалка (`ai_beta_dialogs`). Данные выдуманные.

P0: из профиля — только номер. Сторож заполняет ВСЕ поля профиля маркерами
(`profile_markers`), даёт ученику узнаваемые имя, логин и почту и ищет их в
обоих файлах.
"""
import io
import json
import os
import re
import tempfile
import uuid
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from problems.models_platform import ChatAttachment, ChatTurn
from problems.tests.factories import make_problem, make_user
from problems.tests.profile_markers import FORBIDDEN, fill_profile_with_markers

MEDIA = tempfile.mkdtemp(prefix='qls_ai_beta_dialogs_')
PERSONAL = ('ученицамаркер', 'Ольгамаркер', 'Фамилиямаркер', 'olga.marker@example.org')


@override_settings(MEDIA_ROOT=MEDIA)
class AiBetaDialogsTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = tmp.name
        self.student = make_user('ученицамаркер', first_name='Ольгамаркер',
                                 last_name='Фамилиямаркер', email='olga.marker@example.org')
        fill_profile_with_markers(self.student)
        self.staff = make_user('сотрудник', is_staff=True)
        self.problem = make_problem('Найдите равновесие: $Q_d = 10 - P$.')
        self.thread = uuid.uuid4()
        now = timezone.now()
        # Создаём не по порядку: выгрузка обязана сама разложить по времени.
        self.turn(self.thread, 'вторая', now - timedelta(minutes=1))
        photo = ChatAttachment.objects.create(
            user=self.student, problem=self.problem, mime='image/png', pages=1,
            file=SimpleUploadedFile('решение.png', b'png'),
            pages_json=['chat/2026/10/p1.png'])
        first = self.turn(self.thread, 'первая', now - timedelta(minutes=5), attachment=photo)
        first.attachments.set([photo])
        self.turn(None, 'без разговора', now)
        self.turn(uuid.uuid4(), 'вопрос сотрудника', now, user=self.staff)

    def turn(self, thread, text, when, user=None, attachment=None):
        turn = ChatTurn.objects.create(
            user=user or self.student, problem=self.problem, thread=thread, mode='method',
            user_text=text, attachment=attachment, reply='Ответ: $\\frac{1}{2}$',
            vision_text='расшифровка' if attachment else '')
        ChatTurn.objects.filter(pk=turn.pk).update(created_at=when)
        return turn

    def run_command(self):
        call_command('ai_beta_dialogs', out=self.out, stdout=io.StringIO())
        with open(os.path.join(self.out, 'dialogs.jsonl'), encoding='utf-8') as handle:
            rows = [json.loads(line) for line in handle]
        with open(os.path.join(self.out, 'reader.html'), encoding='utf-8') as handle:
            html = handle.read()
        return rows, html

    def page_data(self, html):
        blob = re.search(r'<script type="application/json" id="rd-data">(.*?)</script>',
                         html, re.S).group(1)
        return json.loads(blob.replace('<\\/', '</'))

    def test_no_profile_fields_anywhere(self):
        rows, html = self.run_command()
        text = json.dumps(rows, ensure_ascii=False)
        for absent in FORBIDDEN + PERSONAL:
            with self.subTest(absent=absent):
                self.assertNotIn(absent, text, 'в выгрузке поле профиля')
                self.assertNotIn(absent, html, 'на странице поле профиля')
        self.assertEqual(rows[0]['user_id'], self.student.pk)

    def test_thread_counts_match_database(self):
        rows, html = self.run_command()
        in_db = (ChatTurn.objects.exclude(thread=None).values('thread').distinct().count()
                 + ChatTurn.objects.filter(thread=None).count())
        self.assertEqual(len(rows), in_db)
        self.assertEqual(len(self.page_data(html)['threads']), len(rows))
        self.assertEqual(sum(len(r['turns']) for r in rows), ChatTurn.objects.count())

    def test_turns_go_by_time_and_staff_is_marked(self):
        rows, _html = self.run_command()
        main = next(r for r in rows if r['thread'] == str(self.thread))
        self.assertEqual([t['user_text'] for t in main['turns']], ['первая', 'вторая'])
        for row in rows:
            times = [t['time'] for t in row['turns']]
            self.assertEqual(times, sorted(times))
        self.assertEqual({r['staff'] for r in rows if r['user_id'] == self.staff.pk}, {True})
        self.assertFalse(main['staff'])

    def test_file_paths_are_relative_to_media(self):
        rows, _html = self.run_command()
        files = [f for r in rows for t in r['turns'] for f in t['files']]
        self.assertEqual(len(files), 1)
        for path in [files[0]['path']] + files[0]['pages']:
            with self.subTest(path=path):
                self.assertTrue(path.startswith('chat/'), path)
                self.assertNotIn(':', path)
                self.assertNotIn('\\', path)
                self.assertNotIn(MEDIA.replace('\\', '/'), path)

    def test_page_is_self_contained_with_katex(self):
        _rows, html = self.run_command()
        self.assertIsNone(re.search(r'''src\s*=\s*["']?\s*(?:https?:)?//''', html),
                          'внешний src на странице')
        self.assertIsNone(re.search(r'''<link[^>]+href\s*=\s*["']?\s*(?:https?:)?//''', html))
        self.assertIsNone(re.search(r'<script[^>]+src=', html), 'скрипт подключён снаружи')
        self.assertIn('.katex', html)
        self.assertIn('renderMathInElement', html)
        self.assertIn('data:font/woff2;base64', html)
        self.assertIn('ai_beta_marks/1', html)
