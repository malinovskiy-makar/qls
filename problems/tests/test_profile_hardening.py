# -*- coding: utf-8 -*-
"""Профиль после 22.09: сохранение «Аккаунта», аватар в админке, имя файла (24.09.2026).

**Почему старые тесты не поймали «Имя пользователя пустое».** Они слали руками
собранный словарь, где `username` был всегда. А на странице поле стояло ВНЕ
формы данных, и браузер его не отправлял. Здесь форма собирается так, как её
собирает браузер: по разметке страницы — поля внутри `<form>` плюс поля с
атрибутом `form="…"`.
"""
import io
import os
import tempfile
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from problems.forms_accounts import ProfileForm
from problems.models_platform import UserProfile

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='qls_profile_media_')


class _Forms(HTMLParser):
    """Поля каждой формы страницы — так, как их увидит браузер.

    `controls[id формы]` — все именованные поля формы (для проверки
    «принадлежит ли»), `submitted[id формы]` — пары, которые уйдут при отправке
    без правок: отмеченные галочки, выбранный пункт списка, текст полей.
    """

    def __init__(self):
        super().__init__()
        self.stack = []          # открытые <form>: их ключи
        self.count = 0
        self.keys = {}           # id или порядковый номер → ключ
        self.controls = {}
        self.submitted = {}
        self.select = None
        self.textarea = None

    def _form_key(self, attrs):
        if attrs.get('form'):
            return attrs['form']
        return self.stack[-1] if self.stack else None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.count += 1
            key = attrs.get('id') or 'form-%d' % self.count
            self.stack.append(key)
            self.controls.setdefault(key, set())
            self.submitted.setdefault(key, [])
            return
        name = attrs.get('name')
        if tag == 'option' and self.select:
            key, sname, state = self.select
            if state['first'] is None:
                state['first'] = attrs.get('value', '')
            if 'selected' in attrs:
                state['chosen'] = attrs.get('value', '')
            return
        if not name or tag not in ('input', 'select', 'textarea', 'button'):
            return
        key = self._form_key(attrs)
        if key is None:
            return
        self.controls.setdefault(key, set()).add(name)
        bucket = self.submitted.setdefault(key, [])
        kind = (attrs.get('type') or 'text').lower()
        if tag == 'input':
            if kind in ('checkbox', 'radio') and 'checked' not in attrs:
                return
            if kind in ('submit', 'button', 'file', 'image', 'reset'):
                return
            bucket.append((name, attrs.get('value', '' if kind not in ('checkbox', 'radio') else 'on')))
        elif tag == 'select':
            self.select = (key, name, {'first': None, 'chosen': None})
        elif tag == 'textarea':
            self.textarea = (key, name, [])

    def handle_data(self, data):
        if self.textarea:
            self.textarea[2].append(data)

    def handle_endtag(self, tag):
        if tag == 'form' and self.stack:
            self.stack.pop()
        elif tag == 'select' and self.select:
            key, name, state = self.select
            value = state['chosen'] if state['chosen'] is not None else state['first']
            if value is not None:
                self.submitted[key].append((name, value))
            self.select = None
        elif tag == 'textarea' and self.textarea:
            key, name, parts = self.textarea
            self.submitted[key].append((name, ''.join(parts)))
            self.textarea = None


def _data_form(html):
    parser = _Forms()
    parser.feed(html)
    keys = [k for k, pairs in parser.submitted.items() if ('action', 'data') in pairs]
    return parser, keys


class AccountTabSubmitsAsBrowserTests(TestCase):
    """Форма «Аккаунта» уходит без правок и не теряет логин."""

    def setUp(self):
        self.user = User.objects.create_user('brauzer_masha', password='p12345', role='student')
        UserProfile.objects.update_or_create(user=self.user, defaults={
            'role': 'student', 'grade': '10', 'telegram': 'masha'})
        self.client = Client()
        self.client.force_login(self.user)

    def _page(self):
        return self.client.get('/profile/?tab=data').content.decode()

    def test_every_profile_form_field_belongs_to_the_data_form(self):
        parser, keys = _data_form(self._page())
        self.assertEqual(len(keys), 1, 'форма данных на странице ровно одна')
        missing = set(ProfileForm.base_fields) - parser.controls[keys[0]]
        self.assertEqual(missing, set(), 'поля вне формы данных — браузер их не отправит')

    def test_unchanged_form_saves_and_keeps_the_username(self):
        parser, keys = _data_form(self._page())
        pairs = parser.submitted[keys[0]]
        data = {}
        for name, value in pairs:
            data.setdefault(name, []).append(value)
        response = self.client.post('/profile/?tab=data', data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:500])
        self.assertIn('saved=1', response['Location'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'brauzer_masha')


@override_settings(MEDIA_ROOT=MEDIA)
class AvatarFileNameTests(TestCase):
    """`avatars/<id>.jpg` без двойной папки, и повторная загрузка не копит копии."""

    def setUp(self):
        self.user = User.objects.create_user('ava_name', password='p12345', role='student')
        UserProfile.objects.update_or_create(user=self.user, defaults={'role': 'student'})
        self.client = Client()
        self.client.force_login(self.user)

    def _upload(self):
        buffer = io.BytesIO()
        Image.new('RGB', (300, 300), (10, 200, 10)).save(buffer, 'PNG')
        return self.client.post('/profile/?tab=data', {
            'action': 'avatar',
            'avatar': SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')})

    def test_name_and_no_leftover_copies(self):
        self._upload()
        self._upload()
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar.name, 'avatars/%d.jpg' % self.user.pk)
        folder = os.path.join(MEDIA, 'avatars')
        self.assertEqual(sorted(os.listdir(folder)), ['%d.jpg' % self.user.pk])


@override_settings(MEDIA_ROOT=MEDIA)
class AvatarInAdminTests(TestCase):
    """Админка показывает аватар через вьюху `avatar`, а не ссылкой на /media/."""

    def setUp(self):
        self.admin = User.objects.create_superuser('glavny', 'g@example.com', 'p12345')
        self.user = User.objects.create_user('s_avatarom', password='p12345', role='student')
        profile, _ = UserProfile.objects.update_or_create(user=self.user,
                                                          defaults={'role': 'student'})
        buffer = io.BytesIO()
        Image.new('RGB', (256, 256), (200, 10, 10)).save(buffer, 'JPEG')
        from django.core.files.base import ContentFile
        profile.avatar.save('%d.jpg' % self.user.pk, ContentFile(buffer.getvalue()), save=True)
        self.profile = profile
        self.client = Client()
        self.client.force_login(self.admin)

    def test_change_page_links_the_avatar_view_not_media(self):
        url = reverse('admin:problems_userprofile_change', args=[self.profile.pk])
        html = self.client.get(url).content.decode()
        self.assertNotIn('/media/', html)
        avatar_url = reverse('avatar', args=[self.user.pk])
        self.assertIn(avatar_url, html)
        response = self.client.get(avatar_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')

    def test_admin_action_removes_the_photo(self):
        changelist = reverse('admin:problems_userprofile_changelist')
        self.client.post(changelist, {'action': 'remove_avatar',
                                      '_selected_action': [self.profile.pk]})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)
