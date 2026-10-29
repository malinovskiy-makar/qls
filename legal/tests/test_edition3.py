# -*- coding: utf-8 -*-
"""Редакция 3 (30.10.2026): вход через VK ID и Яндекс ID, дата рождения, анкета.

Две вещи, которые нельзя разъединять:
* тексты в `legal/texts/*.md` описывают то, что сайт делает (сторожа ниже читают
  сами файлы, а не отрисованные страницы: меняется текст – краснеет тест);
* номер редакции в настройках поднят вместе с текстами, и принявшие редакцию 2
  один раз видят экран согласия.
"""
import time
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from legal import consent
from problems.models import SocialAccount, User
from problems.models_legal import ConsentRecord
from problems.tests.factories import make_user

PD = ConsentRecord.Kind.PD
MAIL = ConsentRecord.Kind.MAIL
TEXTS = Path(settings.BASE_DIR) / 'legal' / 'texts'


def text_of(name):
    return (TEXTS / name).read_text(encoding='utf-8')


def old_record(user, kind, version='2', source=ConsentRecord.Source.REGISTER):
    """Запись, принятая на предыдущей редакции (до выкатки ред. 3)."""
    return ConsentRecord.objects.create(user=user, kind=kind, version=version, source=source)


class EditionThreeTextsTests(SimpleTestCase):
    """Тексты ред. 3 описывают реальное поведение сайта (инвентаризация по коду, 30.10.2026)."""

    def test_privacy_and_terms_no_longer_deny_external_login(self):
        for name in ('privacy.md', 'terms.md'):
            text = text_of(name)
            self.assertNotIn('внешние сервисы не предусмотрен', text, name)
            self.assertNotIn('можно только по логину или адресу', text, name)
            self.assertIn('VK ID и Яндекс ID', text, name)

    def test_privacy_names_the_services_and_what_comes_from_them(self):
        text = text_of('privacy.md')
        for fragment in ('VK ID', 'Яндекс ID', 'Дату рождения', 'токен доступа',
                         'не сохраняется', 'идентификатор пользователя'):
            self.assertIn(fragment, text, fragment)
        # Раздел 5: сервисы входа названы источниками, а не получателями. ООО «ВК»
        # уже стоит в строке VK Почта, поэтому смотрим именно пункт 5.7.
        sources = next(line for line in text.splitlines() if line.startswith('5.7.'))
        for fragment in ('VK ID (ООО «ВК»)', 'Яндекс ID (ООО «ЯНДЕКС»)',
                         'источники данных, а не получатели', 'одноразовый код авторизации'):
            self.assertIn(fragment, sources, fragment)

    def test_privacy_describes_the_mandatory_questionnaire(self):
        text = text_of('privacy.md')
        for fragment in ('Анкета при первом входе (обязательна)', 'город', 'школа',
                         'цели подготовки', 'каким классам', '«Другое»',
                         'пока они не даны, пользоваться Сервисом нельзя'):
            self.assertIn(fragment, text, fragment)
        # Профиль остался необязательным и больше не перечисляет ответы анкеты.
        profile_row = next(line for line in text.splitlines()
                           if line.startswith('| Профиль (заполняется по желанию)'))
        for answered_in_questionnaire in ('школа', 'город', 'уровень', 'источник'):
            self.assertNotIn(answered_in_questionnaire, profile_row)

    def test_consent_lists_the_new_categories_and_sources(self):
        text = text_of('consent.md')
        for fragment in ('VK ID', 'Яндекс ID', 'дата рождения', 'ответы анкеты',
                         'Источники данных'):
            self.assertIn(fragment, text, fragment)

    def test_birth_date_has_source_purpose_and_basis_in_privacy(self):
        text = text_of('privacy.md')
        row = next(line for line in text.splitlines()
                   if line.startswith('| Определение возраста пользователя'))
        _empty, purpose, data, basis, _tail = [cell.strip() for cell in row.split('|')]
        self.assertIn('раздела 9', purpose)                    # цель
        self.assertIn('VK ID или Яндекс ID', purpose)          # источник
        self.assertIn('дата рождения', data)                   # данные
        self.assertEqual(basis, 'согласие')                    # основание

    def test_all_three_documents_are_edition_three(self):
        for name in ('privacy.md', 'consent.md', 'terms.md'):
            self.assertIn('Редакция 3 от [ДАТА]', text_of(name), name)

    def test_untouched_documents_keep_their_own_editions(self):
        for name in ('consent_ai.md', 'consent_mail.md', 'cookies.md', 'recommendations.md'):
            self.assertNotIn('Редакция 3', text_of(name), name)


@override_settings(LEGAL_ENFORCEMENT_ENABLED=True, MAIL_ENABLED=True)
class EditionThreeConsentTests(TestCase):
    def setUp(self):
        self.user = make_user('edition_three')
        self.client.force_login(self.user)

    def test_the_site_runs_edition_three(self):
        self.assertEqual(consent.current_version(), '3')

    def test_edition_two_acceptor_is_sent_to_the_consent_screen_once(self):
        old = old_record(self.user, PD)
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/legal/accept/'))

        self.client.post('/legal/accept/', {'agree': '1', 'next': '/profile/'})
        old.refresh_from_db()
        self.assertIsNotNone(old.superseded_at)
        active = ConsentRecord.objects.get(user=self.user, kind=PD,
                                           revoked_at__isnull=True, superseded_at__isnull=True)
        self.assertEqual(active.version, '3')
        self.assertEqual(self.client.get('/profile/').status_code, 200)

    def test_mail_consent_survives_the_edition_bump(self):
        old_record(self.user, PD)
        mail = old_record(self.user, MAIL, version='1')
        self.client.post('/legal/accept/', {'agree': '1', 'next': '/profile/'})
        mail.refresh_from_db()
        self.assertIsNone(mail.superseded_at)
        self.assertTrue(consent.wants_mail(self.user))

    def test_account_created_through_a_service_records_edition_three(self):
        """Экран «Почти готово» пишет согласие текущей редакции – 3."""
        client = self.client_class()
        session = client.session
        session['social_pending'] = {
            'provider': 'yandex', 'uid': '7007', 'first_name': 'Анна', 'last_name': 'Смирнова',
            'email': '', 'email_verified': False, 'birth_date': None, 'avatar_url': '',
            'next': '', 'at': time.time()}
        session.save()
        with override_settings(MAIL_ENABLED=False):
            response = client.post('/auth/finish/', {'consent': 'on'})
        self.assertEqual(response.status_code, 302)
        user = SocialAccount.objects.get(provider='yandex', uid='7007').user
        record = ConsentRecord.objects.get(user=user, kind=PD)
        self.assertEqual((record.version, record.source), ('3', ConsentRecord.Source.REGISTER))
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
