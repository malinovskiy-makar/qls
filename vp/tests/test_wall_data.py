"""Стена 2 тура: данные человека — удаление аккаунта, сроки хранения, админка, статистика."""
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems import erasure, retention
from vp import wall
from vp.models import VPTelegramLink, VPTelegramToken, VPWall

User = get_user_model()


def wall_rows(user):
    wall.pass_contact(user, 'tg')
    VPWall.objects.filter(user=user).update(grade='10', tour2_status='passed', source='vk',
                                            survey_at=timezone.now())
    VPTelegramLink.objects.create(user=user, tg_user_id=4242, tg_username='nick', subscribed=True)
    VPTelegramToken.objects.create(user=user, token_hash='a' * 64, slug='demo')


class EraseTests(TestCase):
    def test_erase_user_leaves_no_wall_rows(self):
        user = User.objects.create_user('erase_me', password='p12345')
        wall_rows(user)
        erasure.erase_user(user)
        self.assertEqual(VPWall.objects.count(), 0)
        self.assertEqual(VPTelegramLink.objects.count(), 0)
        self.assertEqual(VPTelegramToken.objects.count(), 0)


class RetentionTests(TestCase):
    def test_tokens_older_than_a_day_go_fresh_stay(self):
        user = User.objects.create_user('ret_u', password='p12345')
        old = VPTelegramToken.objects.create(user=user, token_hash='o' * 64, slug='x')
        VPTelegramToken.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=25), used_at=timezone.now())
        fresh = VPTelegramToken.objects.create(user=user, token_hash='f' * 64, slug='x')
        label = 'vp.VPTelegramToken (старше суток)'
        self.assertEqual(retention.plan()['rows'][label], 1)
        self.assertEqual(VPTelegramToken.objects.count(), 2)  # сухой прогон ничего не тронул
        self.assertEqual(retention.purge()['rows'][label], 1)
        self.assertEqual(list(VPTelegramToken.objects.values_list('pk', flat=True)), [fresh.pk])


class AdminTests(TestCase):
    def test_wall_pages_open_and_links_are_read_only(self):
        admin = User.objects.create_superuser('wall_admin', password='p12345')
        wall_rows(User.objects.create_user('someone', password='p12345'))
        client = Client()
        client.force_login(admin)
        for name in ('vpwall', 'vptelegramlink', 'vptelegramtoken'):
            self.assertEqual(client.get(reverse('admin:vp_%s_changelist' % name)).status_code, 200)
        link = VPTelegramLink.objects.get()
        page = client.get(reverse('admin:vp_vptelegramlink_change', args=[link.pk])).content.decode()
        self.assertNotIn('name="tg_user_id"', page)
        self.assertEqual(client.get(reverse('admin:vp_vptelegramtoken_add')).status_code, 403)
        token = VPTelegramToken.objects.get()
        page = client.get(reverse('admin:vp_vptelegramtoken_change', args=[token.pk])).content.decode()
        self.assertNotIn('a' * 64, page)


class StatsTests(TestCase):
    def test_stats_show_paths_and_survey(self):
        wall_rows(User.objects.create_user('stat_a', password='p12345'))
        b = User.objects.create_user('stat_b', password='p12345')
        wall.pass_contact(b, 'email')
        c = User.objects.create_user('stat_c', password='p12345')
        VPWall.objects.create(user=c)
        VPTelegramToken.objects.create(user=c, token_hash='c' * 64, slug='x')
        out = io.StringIO()
        call_command('vp_wall_stats', '--days', '2', stdout=out)
        text = out.getvalue()
        self.assertRegex(text, r'всего\s+3\s+1 \(33%\)\s+1 \(33%\)\s+1\s+1')
        self.assertIn('Откуда узнал: ВКонтакте – 1', text)
