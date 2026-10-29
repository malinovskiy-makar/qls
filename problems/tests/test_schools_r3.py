# -*- coding: utf-8 -*-
"""Школы, раунд 3 (29.10.2026): реестр Рособрнадзора, синхронизация, поиск по стране.

Решения владельца 29.10.2026: школа не зависит от города (подсказки по всей стране, школы
введённого города первыми, выбор школы подставляет город); справочник — своя таблица +
еженедельная синхронизация с реестром, а не запрос к Рособрнадзору на каждую букву.
Сеть подменяется целиком: ни одного настоящего запроса.
"""
import io
import os
import tempfile
import zipfile
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from problems import school_registry, school_search, school_sync
from problems.models import School
from problems.models_platform import UserProfile
from problems.models_schools import SchoolSyncRun
from problems.tests.factories import make_user

PROGRAM = ('<EducationalProgram><EduLevelName>{level}</EduLevelName><IsCanceled>{cancel}'
           '</IsCanceled></EducationalProgram>')


def org(oid, short, address, region='г. Москва', full='', branch='', inn='7700000001',
        kpp='770001001'):
    return ('<ActualEducationOrganization><Id>%s</Id><FullName>%s</FullName><ShortName>%s'
            '</ShortName><IsBranch>%s</IsBranch><PostAddress>%s</PostAddress><INN>%s</INN>'
            '<KPP>%s</KPP><HeadName>Иванова Мария Петровна</HeadName><Email>dir@school.ru</Email>'
            '<KindName/><TypeName/><RegionName>%s</RegionName></ActualEducationOrganization>'
            % (oid, full or short, short, branch, address, inn, kpp, region))


def certificate(head, supplements, status='Действующее'):
    body = ''.join(
        '<Supplement><StatusName>%s</StatusName>%s<EducationalPrograms>%s</EducationalPrograms>'
        '</Supplement>' % (st, sup_org, ''.join(PROGRAM.format(level=lv, cancel=c) for lv, c in progs))
        for st, sup_org, progs in supplements)
    return ('<Certificate><StatusName>%s</StatusName>%s<Supplements>%s</Supplements></Certificate>'
            % (status, head, body))


GENERAL = [('Основное общее образование', ''), ('Среднее общее образование', '')]


def registry_xml(*certs):
    return ('<?xml version="1.0" encoding="UTF-8"?><OpenData><Certificates>%s</Certificates>'
            '</OpenData>' % ''.join(certs)).encode('utf-8')


SCHOOL_57 = org('id-57', 'ГБОУ Школа № 57 г. Москвы', 'г. Москва, Малый Знаменский пер., 7/10')
SAMPLE = registry_xml(
    certificate(SCHOOL_57, [('Действующее', SCHOOL_57, GENERAL)]),
    # Недействующее свидетельство — пропуск.
    certificate(org('id-old', 'МОУ «Старая СОШ»', 'с. Кемцы, Тверская область', 'Тверская область'),
                [('Действующее', '', GENERAL)], status='Недействующее'),
    # Колледж — без общего образования — пропуск.
    certificate(org('id-col', 'ГБПОУ Колледж связи', 'г. Москва, ул. Б'),
                [('Действующее', '', [('Среднее профессиональное образование', '')])]),
    # Головная + филиал отдельным приложением со своим адресом.
    certificate(org('id-head', 'МБОУ «Новоселовская ООШ» Орловского муниципального округа',
                    '302532, Орловская область, Орловский муниципальный округ, д. Новосёлово, зд. 18',
                    'Орловская область', inn='5720010403', kpp='572001001'),
                [('Действующее', '', GENERAL),
                 ('Действующее', org('id-br', 'Филиал МБОУ «Новоселовская ООШ»',
                                     'Орловская область, с. Сабурово, ул. Школьная, 1',
                                     'Орловская область', branch='1', inn='5720010403',
                                     kpp='572002001'), GENERAL),
                 # Недействующее приложение — пропуск.
                 ('Недействующее', org('id-dead', 'Филиал старый', 'с. Пусто', 'Орловская область'),
                  GENERAL)]),
    # Отменённая программа не делает организацию школой.
    certificate(org('id-cancel', 'МБОУ «Отменённая СОШ»', 'г. Тула', 'Тульская область'),
                [('Действующее', '', [('Основное общее образование', '1')])]),
)


class RegistryParserTests(SimpleTestCase):
    def test_only_valid_general_education_and_branches(self):
        rows = school_registry.read_bytes(SAMPLE)
        self.assertEqual(set(rows), {'id-57', 'id-head', 'id-br'})
        self.assertEqual(rows['id-57']['short_name'], 'Школа № 57')
        self.assertEqual(rows['id-57']['number'], 57)
        self.assertEqual(rows['id-57']['city'], 'Москва')
        self.assertEqual(rows['id-head']['short_name'], 'Новоселовская ООШ')
        self.assertEqual(rows['id-head']['city'], 'Новосёлово')
        self.assertTrue(rows['id-br']['is_branch'])
        self.assertEqual(rows['id-br']['city'], 'Сабурово')

    def test_zip_is_read_without_unpacking(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('data-20261029-structure-20160713.xml', SAMPLE)
        self.assertEqual(set(school_registry.read_bytes(buffer.getvalue())),
                         {'id-57', 'id-head', 'id-br'})

    def test_director_and_contacts_are_not_kept(self):
        rows = school_registry.read_bytes(SAMPLE)
        text = repr(rows)
        for secret in ('Иванова', 'dir@school.ru'):
            self.assertNotIn(secret, text)

    def test_human_names(self):
        for short, full, expected in (
            ('ГБОУ Школа № 57 г. Москвы', '', 'Школа № 57'),
            ('МБОУ «Новоселовская ООШ» Орловского муниципального округа', '', 'Новоселовская ООШ'),
            ('ГБОУ СОШ № 28 КАЛИНИНСКОГО РАЙОНА САНКТ-ПЕТЕРБУРГА', '', 'СОШ № 28'),
            ('ГБОУ «ШКОЛА № 71 ИМ. П.Ф. БАТУЛЫ Г.О. ДОНЕЦК»', '', 'Школа № 71 им. П.Ф. Батулы'),
            ('ГБОУ ПО «АКАДЕМИЧЕСКИЙ ЛИЦЕЙ №14 ИМ. А.В. СУВОРОВА»', '',
             'Академический лицей № 14 им. А.В. Суворова'),
            ('БОУ г. Омска "Средняя общеобразовательная школа № 131"', '',
             'Средняя общеобразовательная школа № 131'),
            ('МАОУ "Гимназия №3" г. Перми', '', 'Гимназия № 3'),
            ('ГБОУ «Лицей «Вторая школа»»', '', 'Лицей «Вторая школа»'),
            ('ГБОУ «Лицей «Надежда»', '', 'Лицей «Надежда»'),
            ('МБОУ ШКОЛА НА ЗАРЕ ИМ. Ю.В. МЕДОВОЙ', '', 'Школа на заре им. Ю.В. Медовой'),
            ('муниципальное бюджетное общеобразовательное учреждение Анжеро-Судженского г',
             'муниципальное бюджетное общеобразовательное учреждение Анжеро-Судженского '
             'городского округа «Основная общеобразовательная школа № 36»',
             'Основная общеобразовательная школа № 36'),
        ):
            self.assertEqual(school_registry.human_name(short, full), (expected, False), short)
        self.assertEqual(school_registry.human_name('', 'Полное название школы'),
                         ('Полное название школы', True))

    def test_long_capslock_prefix_does_not_hang(self):
        # 29.10.2026 регулярка с вложенным квантификатором вставала намертво на таком.
        name = 'АБВГДЕЖ ' * 30 + '«Школа»'
        self.assertEqual(school_registry.human_name(name, '')[0], 'Школа')

    def test_city_from_address(self):
        for address, region, city in (
            ('ул. Школьная, дом 18, с. Кемцы, Бологовский район, Тверская область, 171062',
             'Тверская область', 'Кемцы'),
            ('356011 Ставропольский край Новоалександровский район пос.Горьковский пер.Школьный 2',
             'Ставропольский край', 'Горьковский'),
            ('634034 г. Томск, пр. Кирова, 12', 'Томская область', 'Томск'),
            ('454021, ЧЕЛЯБИНСКАЯ ОБЛАСТЬ, ЧЕЛЯБИНСК ГОРОД, 250-ЛЕТИЯ ЧЕЛЯБИНСКА УЛИЦА, 15',
             'Челябинская область', 'Челябинск'),
            ('400093, Россия, Волгоград, ул. им. академика Богомольца, 15', 'Волгоградская область',
             'Волгоград'),
            ('671014, Республика Бурятия, Тункинский район, улус Хужиры, ул.Школьная, 1',
             'Республика Бурятия', 'Хужиры'),
            ('Саратовская область, Энгельсский муниципальный район, рабочий посёлок Приволжский, '
             'ул. Гагарина, дом 17б', 'Саратовская область', 'Приволжский'),
            ('272155, ЗАПОРОЖСКАЯ ОБЛАСТЬ С. РАДОЛОВКА, УЛ. ЛЕНИНА, 18', 'Запорожская область',
             'Радоловка'),
            ('141435, Московская обл., городской округ Химки, микрорайон Новогорск',
             'Московская область', 'Химки'),
            ('пгт. Белая Берёзка, ул. Ленина, 1', 'Брянская область', 'Белая Берёзка'),
            ('ул. Тверская, 1', 'г. Москва', 'Москва'),
            ('Курская область, Курский район, д. 25, ул. Мира', 'Курская область', ''),
        ):
            self.assertEqual(school_registry.city_from_address(address, region), city, address)

    def test_number_is_not_an_anniversary(self):
        self.assertIsNone(school_search.number_in_name('СОШ имени 50-летия Октября'))
        self.assertEqual(school_search.number_in_name('СОШ № 5 имени 50-летия Октября'), 5)


def fields(oid, **over):
    row = {'registry_id': oid, 'inn': '1', 'kpp': oid[-1:], 'name': 'Полное ' + oid,
           'short_name': 'Школа ' + oid, 'number': None, 'city': 'Тула',
           'region': 'Тульская область', 'is_branch': False}
    row.update(over)
    return row


class ApplyRowsTests(TestCase):
    def test_add_change_deactivate_and_repeat_is_zero(self):
        rows = {k: fields(k) for k in ('a1', 'a2', 'a3')}
        self.assertEqual(school_sync.apply_rows(rows, apply=True),
                         {'total': 3, 'added': 3, 'changed': 0, 'deactivated': 0})
        self.assertEqual(school_sync.apply_rows(rows, apply=True),
                         {'total': 3, 'added': 0, 'changed': 0, 'deactivated': 0})
        rows['a2'] = fields('a2', short_name='Лицей a2')
        del rows['a3']
        rows['a4'] = fields('a4')
        self.assertEqual(school_sync.apply_rows(rows, apply=True),
                         {'total': 3, 'added': 1, 'changed': 1, 'deactivated': 1})
        gone = School.objects.get(registry_id='a3')
        self.assertFalse(gone.is_active)                 # выключена, а не удалена
        self.assertEqual(School.objects.get(registry_id='a2').name_norm, 'лицей a2 полное a2')
        self.assertEqual(School.objects.count(), 4)

    def test_same_inn_kpp_under_a_new_id_is_the_same_school(self):
        school_sync.apply_rows({'old': fields('old', inn='77', kpp='01')}, apply=True)
        counts = school_sync.apply_rows({'new': fields('new', inn='77', kpp='01')}, apply=True)
        self.assertEqual((counts['added'], counts['changed'], counts['deactivated']), (0, 1, 0))
        self.assertEqual(list(School.objects.values_list('registry_id', flat=True)), ['new'])

    def test_broken_file_changes_nothing(self):
        school_sync.apply_rows({k: fields(k) for k in ('b1', 'b2', 'b3', 'b4')}, apply=True)
        with self.assertRaises(school_sync.SyncError):
            school_sync.apply_rows({'b1': fields('b1')}, apply=True)
        self.assertEqual(School.objects.filter(is_active=True).count(), 4)

    def test_dry_run_writes_nothing(self):
        school_sync.apply_rows({'c1': fields('c1')}, apply=False)
        self.assertEqual(School.objects.count(), 0)

    def test_csv_rows_are_not_touched(self):
        School.objects.create(name='Школа из CSV', city='Тула', region='Тульская область')
        school_sync.apply_rows({'d1': fields('d1')}, apply=True)
        self.assertTrue(School.objects.get(name='Школа из CSV').is_active)


class FakeResponse(io.BytesIO):
    def __init__(self, body=b'', headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def zipped(payload):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('data.xml', payload)
        # Добить до порога «похоже на архив реестра», как настоящий файл подписи.
        archive.writestr('data.sig', os.urandom(school_sync.MIN_BYTES))
    return buffer.getvalue()


class SyncSchoolsCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.archive = zipped(SAMPLE)
        self.headers = {'Content-Disposition': 'attachment; filename=data-20261029-structure-'
                        '20160713.zip', 'Content-Length': str(len(self.archive))}
        patcher = mock.patch.object(school_sync.time, 'sleep')
        patcher.start()
        self.addCleanup(patcher.stop)

    def network(self, body=None, fail_get=False):
        calls = []

        def request(url, method='GET'):
            calls.append(method)
            if method == 'HEAD':
                return FakeResponse(headers=self.headers)
            if fail_get:
                raise OSError('обрыв')
            return FakeResponse(self.archive if body is None else body)
        return request, calls

    def run_sync(self, *args, **net):
        request, calls = self.network(**net)
        out = io.StringIO()
        with mock.patch.object(school_sync, '_request', request):
            call_command('sync_schools', *args, stdout=out)
        return out.getvalue(), calls

    def test_downloads_parses_and_logs(self):
        out, calls = self.run_sync()
        self.assertIn('добавлено 3, изменено 0, выключено 0', out)
        self.assertEqual(calls, ['HEAD', 'GET'])
        run = SchoolSyncRun.objects.get()
        self.assertEqual((run.status, run.source, run.added), ('ok', 'data-20261029-structure-'
                                                                     '20160713.zip', 3))
        self.assertEqual(School.objects.filter(is_active=True).count(), 3)

    def test_same_file_is_not_downloaded_again(self):
        self.run_sync()
        out, calls = self.run_sync()
        self.assertEqual(calls, ['HEAD'])
        self.assertIn('не изменился', out)
        self.assertEqual(SchoolSyncRun.objects.first().status, 'same')
        out, calls = self.run_sync('--force')
        self.assertIn('добавлено 0, изменено 0, выключено 0', out)

    def test_download_failure_leaves_the_table_alone(self):
        self.run_sync()
        before = list(School.objects.order_by('pk').values_list('registry_id', 'is_active'))
        self.headers['Content-Disposition'] = 'attachment; filename=data-20261030-x.zip'
        with self.assertRaises(CommandError):
            self.run_sync(fail_get=True)
        self.assertEqual(list(School.objects.order_by('pk').values_list('registry_id', 'is_active')),
                         before)
        self.assertEqual(SchoolSyncRun.objects.first().status, 'failed')

    def test_truncated_or_wrong_file_is_refused(self):
        self.headers['Content-Length'] = str(len(self.archive) + 10)
        with self.assertRaises(CommandError):
            self.run_sync()
        self.headers['Content-Length'] = str(school_sync.MIN_BYTES + 10)
        with self.assertRaises(CommandError):
            self.run_sync(body=b'<html>' + b' ' * (school_sync.MIN_BYTES + 4))
        self.assertEqual(School.objects.count(), 0)

    def test_load_schools_raoo_uses_the_same_parser(self):
        handle = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        handle.write(self.archive)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        out = io.StringIO()
        call_command('load_schools', '--format', 'raoo', handle.name, '--apply', stdout=out)
        self.assertIn('новых: 3', out.getvalue())
        call_command('load_schools', '--format', 'raoo', handle.name, '--apply', stdout=out)
        self.assertEqual(School.objects.count(), 3)


class NationwideSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        for name, city, region in (('Школа № 57', 'Москва', 'г. Москва'),
                                   ('СОШ № 57', 'Екатеринбург', 'Свердловская область'),
                                   ('Школа № 57', 'Казань', 'Республика Татарстан'),
                                   ('СОШ № 1', 'Березовка', 'Пермский край'),
                                   ('СОШ № 1', 'Березовка', 'Красноярский край')):
            School.objects.create(name=name, short_name=name, city=city, region=region,
                                  number=school_search.number_in_name(name), registry_id=name + city
                                  + region)
        School.objects.create(name='Школа № 57', short_name='Школа № 57', city='Тула',
                              region='Тульская область', number=57, is_active=False,
                              registry_id='gone')

    def test_57_without_city_comes_from_different_cities_each_with_its_city(self):
        rows = school_search.schools('', '57')
        self.assertEqual({r['city'] for r in rows}, {'Москва', 'Екатеринбург', 'Казань'})
        self.assertTrue(all(r['sub'] for r in rows))
        self.assertNotIn('Тула', {r['city'] for r in rows})        # выключенная не видна

    def test_57_with_moscow_puts_moscow_first(self):
        rows = school_search.schools('Москва', '57')
        self.assertEqual((rows[0]['value'], rows[0]['city']), ('Школа № 57', 'Москва'))
        self.assertEqual(school_search.schools('мск', '57')[0]['city'], 'Москва')

    def test_region_only_when_the_city_name_repeats(self):
        subs = {r['sub'] for r in school_search.schools('', '1')}
        self.assertEqual(subs, {'Березовка, Пермский край', 'Березовка, Красноярский край'})
        self.assertEqual(school_search.schools('', 'школа 57')[0]['sub'], 'Москва')

    def test_api_city_is_optional(self):
        self.client.force_login(make_user('u'))
        data = self.client.get('/welcome/api/schools/', {'q': '57'}).json()['results']
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]['city'], 'Москва')
        data = self.client.get('/welcome/api/schools/', {'q': '57', 'city': 'Казань'}).json()
        self.assertEqual(data['results'][0]['city'], 'Казань')


class SchoolStepCityTests(TestCase):
    def setUp(self):
        School.objects.create(name='ГБОУ Школа № 57', short_name='Школа № 57', city='Москва',
                              region='г. Москва', number=57, registry_id='m57')
        self.user = make_user('learner')
        UserProfile.objects.filter(user=self.user).update(role='student', grade='10',
                                                          level='basic', goals=['listed'])
        self.client.force_login(self.user)

    def test_school_with_empty_city_fills_the_city(self):
        self.client.post('/welcome/school/', {'city': '', 'school': 'Школа № 57'})
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual((profile.city, profile.school), ('Москва', 'Школа № 57'))

    def test_school_from_another_city_keeps_the_typed_city(self):
        response = self.client.post('/welcome/school/', {'city': 'Химки', 'school': 'Школа № 57'})
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual((profile.city, profile.school), ('Химки', 'Школа № 57'))

    def test_unknown_school_without_city_asks_for_the_city(self):
        response = self.client.post('/welcome/school/', {'city': '', 'school': 'Моя школа'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Укажите город.')

    def test_both_fields_are_shown_at_once(self):
        html = self.client.get('/welcome/school/').content.decode()
        self.assertIn('id="ob-city"', html)
        self.assertIn('id="ob-school"', html)
        self.assertNotIn('data-ob-school', html)
        self.assertNotIn('initSchool', open('static/onboarding/onboarding.js', encoding='utf-8').read())
