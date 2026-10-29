# -*- coding: utf-8 -*-
"""Данные входа через VK ID / Яндекс ID и онбординга (фаза 1, решения 29.10.2026).

* В `SocialAccount` нет полей с «token» или «secret» в имени: токены не храним.
* Пара (сервис, uid) уникальна — один VK ID не привязать к двум аккаунтам.
* Привязка уходит вместе с аккаунтом при удалении (`problems/erasure.py`).
* «Откуда узнали» в профиле — ровно 8 кодов стены ВП в её порядке и с её подписями.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase

from problems import erasure
from problems.models import SocialAccount
from problems.models_platform import UserProfile
from problems.tests.factories import make_user
from vp.models import VPWall


class SocialAccountModelTests(TestCase):
    def test_no_token_or_secret_fields(self):
        names = [field.name.lower() for field in SocialAccount._meta.get_fields()]
        self.assertTrue(names)
        for name in names:
            self.assertNotIn('token', name)
            self.assertNotIn('secret', name)

    def test_provider_and_uid_are_unique(self):
        first, second = make_user('soc_a'), make_user('soc_b')
        SocialAccount.objects.create(user=first, provider='vk', uid='42')
        with self.assertRaises(IntegrityError), transaction.atomic():
            SocialAccount.objects.create(user=second, provider='vk', uid='42')
        # Тот же номер у другого сервиса — другой человек.
        SocialAccount.objects.create(user=second, provider='yandex', uid='42')

    def test_erasure_deletes_the_link(self):
        user = make_user('soc_gone')
        SocialAccount.objects.create(user=user, provider='yandex', uid='777')
        erasure.erase_user(user)
        self.assertFalse(SocialAccount.objects.filter(uid='777').exists())


class SourceChannelMatchesWallTests(TestCase):
    def test_same_codes_order_and_labels_as_the_wall(self):
        self.assertEqual(list(UserProfile.SourceChannel.choices),
                         list(VPWall.SOURCE_CHOICES))
