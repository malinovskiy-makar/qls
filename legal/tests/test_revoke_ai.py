# -*- coding: utf-8 -*-
"""Часть Б, фаза 4: отзыв согласия на помощника удаляет диалоги и файлы чата.

Согласие на помощника, п. 8: «После отзыва помощник отключается, а мои диалоги и
файлы на сервере Оператора удаляются». Окно подтверждения – свой диалог сайта.
"""
import io
import os
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from legal import consent
from problems.models_legal import ConsentRecord
from problems.models_platform import ChatAttachment, ChatTurn
from problems.tests.factories import make_problem, make_user

AI = ConsentRecord.Kind.AI
MEDIA = tempfile.mkdtemp(prefix='qls_revoke_media_')


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (1, 2, 3)).save(buf, 'PNG')
    return buf.getvalue()


def _exists(name):
    return os.path.exists(os.path.join(MEDIA, name))


@override_settings(MEDIA_ROOT=MEDIA)
class RevokeDeletesChatTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.problem = make_problem('Две фирмы выбирают выпуск.')
        self.user = make_user('revoke_me')
        self.other = make_user('revoke_other')
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        consent.grant(self.other, AI, ConsentRecord.Source.CHAT)
        self.mine = self._chat_data(self.user, 'mine')
        self.theirs = self._chat_data(self.other, 'theirs')
        self.client.force_login(self.user)

    def _chat_data(self, user, tag):
        """Две реплики, вложение и его картинки страниц (отдельные файлы)."""
        attachment = ChatAttachment(user=user, problem=self.problem, mime='application/pdf', size=4)
        attachment.file.save('%s.pdf' % tag, ContentFile(b'%PDF'), save=False)
        attachment.save()
        pages = [default_storage.save('chat/%s_p%d.png' % (tag, n), ContentFile(_png())) for n in (1, 2)]
        attachment.pages_json = pages
        attachment.save(update_fields=['pages_json'])
        for text in ('первая', 'вторая'):
            ChatTurn.objects.create(user=user, problem=self.problem, user_text=text)
        return [attachment.file.name] + pages

    def test_after_the_revoke_there_is_nothing_of_mine_and_everything_of_others(self):
        self.assertEqual(ChatTurn.objects.filter(user=self.user).count(), 2)
        response = self.client.post(reverse('legal:ai_revoke'))
        self.assertEqual(response['Location'], '/profile/?tab=data')
        self.assertFalse(consent.has_current(self.user, AI))
        self.assertEqual(ChatTurn.objects.filter(user=self.user).count(), 0)
        self.assertEqual(ChatAttachment.objects.filter(user=self.user).count(), 0)
        self.assertEqual([p for p in self.mine if _exists(p)], [])
        # Запись согласия не стёрта: она доказательство, помечена отозванной.
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, kind=AI).count(), 1)
        # Чужое не пропало.
        self.assertEqual(ChatTurn.objects.filter(user=self.other).count(), 2)
        self.assertEqual(ChatAttachment.objects.filter(user=self.other).count(), 1)
        self.assertTrue(all(_exists(p) for p in self.theirs))
        self.assertTrue(consent.has_current(self.other, AI))

    def test_the_history_endpoint_is_empty_after_the_revoke(self):
        self.client.post(reverse('legal:ai_revoke'))
        self.assertEqual(ChatTurn.objects.filter(user=self.user, problem=self.problem).count(), 0)

    def test_revoke_without_any_chat_still_works(self):
        ChatTurn.objects.filter(user=self.user).delete()
        ChatAttachment.objects.filter(user=self.user).delete()
        self.client.post(reverse('legal:ai_revoke'))
        self.assertFalse(consent.has_current(self.user, AI))

    def test_revoke_needs_post_and_login(self):
        self.assertEqual(self.client.get(reverse('legal:ai_revoke')).status_code, 405)
        self.assertEqual(ChatTurn.objects.filter(user=self.user).count(), 2)
        self.client.logout()
        response = self.client.post(reverse('legal:ai_revoke'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ChatTurn.objects.filter(user=self.user).count(), 2)

    def test_the_profile_asks_before_it_deletes_with_the_site_dialog(self):
        html = self.client.get('/profile/?tab=data').content.decode('utf-8')
        self.assertIn('<dialog class="pf-confirm-dlg" id="pf-revoke-dlg"', html)
        self.assertIn('Помощник отключится. Ваши диалоги с ним и загруженные файлы будут удалены. '
                      'Это нельзя отменить.', html)
        self.assertIn('Отозвать и удалить</button>', html)
        self.assertIn('data-close>Отмена</button>', html)
        # Первая кнопка только открывает окно: прямой отправки формы без подтверждения нет.
        self.assertIn('<button type="button" class="btn-quiet" id="pf-revoke-open">Отозвать</button>', html)
        self.assertEqual(html.count('action="%s"' % reverse('legal:ai_revoke')), 1)

    def test_no_native_confirm_in_the_profile(self):
        base = Path(settings.BASE_DIR)
        for rel in ('problems/templates/platform/profile.html', 'problems/static/platform/profile.js'):
            text = (base / rel).read_text(encoding='utf-8')
            self.assertNotIn('confirm(', text, rel)
        js = (base / 'problems/static/platform/profile.js').read_text(encoding='utf-8')
        self.assertIn("revokeDialog.showModal()", js)
