# -*- coding: utf-8 -*-
"""Подсказки городов и школ онбординга (раунд 2, фаза 4): `problems/school_search.py`,
`/welcome/api/cities/`, `/welcome/api/schools/`, `manage.py load_schools`."""
import csv
import os
import tempfile

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from problems import school_search
from problems.models import School
from problems.models_platform import UserProfile
from problems.tests.factories import make_user


class NumberWordsTests(SimpleTestCase):
    def test_ten_examples(self):
        for text, number in (
            ('пятьдесят седьмая', 57), ('пятьдесят семь', 57), ('сто двадцать пятый', 125),
            ('первая', 1), ('тридцать третья', 33), ('одиннадцатый', 11),
            ('тысяча пятьсот тридцать пятый', 1535), ('две тысячи седьмая', 2007),
            ('девятьсот девяносто девять', 999), ('сороковой', 40),
            ('школа номер двести четвертая', 204), ('три тысячи', 3000),
        ):
            self.assertEqual(school_search.words_to_number(text), number, text)

    def test_not_a_number(self):
        for text in ('интеллектуал', 'лицей вшэ', '', 'пять тысяч'):
            self.assertIsNone(school_search.words_to_number(text), text)

    def test_number_in_a_query(self):
        for text in ('57', '№57', '№ 57', 'школа 57', '57-я', 'пятьдесят седьмая'):
            self.assertEqual(school_search.query_number(text), 57, text)
        self.assertEqual(school_search.query_number('лицей 1535'), 1535)


class CityTests(SimpleTestCase):
    def test_mo_gives_moscow_first(self):
        self.assertEqual(school_search.cities('мо')[0]['value'], 'Москва')

    def test_synonyms(self):
        for text in ('питер', 'спб', 'СПБ'):
            self.assertEqual(school_search.cities(text)[0]['value'], 'Санкт-Петербург', text)
        self.assertEqual(school_search.cities('мск')[0]['value'], 'Москва')

    def test_yo_is_e(self):
        self.assertEqual(school_search.cities('орел')[0]['value'], 'Орёл')
        self.assertEqual(school_search.cities('Орёл')[0]['value'], 'Орёл')

    def test_start_of_name_beats_the_middle_and_region_is_second_line(self):
        results = school_search.cities('кур')
        self.assertTrue(results[0]['value'].lower().startswith('кур'))
        self.assertTrue(results[0]['sub'])
        self.assertLessEqual(len(results), school_search.LIMIT)

    def test_empty_query(self):
        self.assertEqual(school_search.cities(''), [])


class SchoolSearchTests(TestCase):
    def setUp(self):
        for name, kind in (('Школа № 571', 'ГБОУ'), ('Школа № 57', 'ГБОУ'),
                           ('Лицей № 579', 'ГБОУ'), ('Лицей № 1535', 'ГБОУ'),
                           ('Школа «Интеллектуал»', 'ГБОУ')):
            School.objects.create(name=name, kind=kind, city='Москва', region='Москва',
                                  number=school_search.number_in_name(name))
        School.objects.create(name='Школа № 57', city='Казань', region='Республика Татарстан',
                              number=57)

    def values(self, query, city='Москва'):
        return [row['value'] for row in school_search.schools(city, query)]

    def test_57_first_then_by_prefix(self):
        self.assertEqual(self.values('57'), ['Школа № 57', 'Школа № 571', 'Лицей № 579'])

    def test_words_find_the_same_school(self):
        for query in ('пятьдесят седьмая', 'школа 57', '№57', '57-я'):
            self.assertEqual(self.values(query)[0], 'Школа № 57', query)

    def test_only_the_chosen_city(self):
        self.assertEqual(self.values('57', city='Казань'), ['Школа № 57'])
        self.assertEqual(self.values('57', city='Омск'), [])

    def test_by_name(self):
        self.assertEqual(self.values('интеллектуал'), ['Школа «Интеллектуал»'])
        # Точный номер — первым, дальше совпадения по названию.
        self.assertEqual(self.values('лицей 1535'), ['Лицей № 1535', 'Лицей № 579'])

    def test_what_people_typed_counts_only_when_repeated(self):
        for name in ('a', 'b'):
            user = make_user(name)
            UserProfile.objects.filter(user=user).update(city='Омск', school='Гимназия № 117')
        lonely = make_user('c')
        UserProfile.objects.filter(user=lonely).update(city='Омск', school='Школа где учится Маша')
        self.assertEqual(self.values('117', city='Омск'), ['Гимназия № 117'])
        self.assertEqual(self.values('маша', city='Омск'), [])


class SuggestApiTests(TestCase):
    def setUp(self):
        cache.clear()
        School.objects.create(name='Школа № 57', city='Москва', region='Москва', number=57)

    def test_guest_is_refused(self):
        for url in ('/welcome/api/cities/?q=мо', '/welcome/api/schools/?city=Москва&q=57'):
            self.assertIn(self.client.get(url).status_code, (302, 403))

    def test_logged_in_gets_json(self):
        self.client.force_login(make_user('u'))
        data = self.client.get('/welcome/api/cities/', {'q': 'мо'}).json()
        self.assertEqual(data['results'][0]['value'], 'Москва')
        data = self.client.get('/welcome/api/schools/', {'city': 'Москва', 'q': '57'}).json()
        self.assertEqual(data['results'][0]['value'], 'Школа № 57')
        self.assertEqual(self.client.get('/welcome/api/cities/', {'q': ''}).json()['results'], [])

    def test_rate_limit(self):
        from problems import views_onboarding
        self.client.force_login(make_user('u'))
        for _ in range(views_onboarding.SUGGEST_PER_MINUTE):
            self.client.get('/welcome/api/cities/', {'q': 'мо'})
        self.assertEqual(self.client.get('/welcome/api/cities/', {'q': 'мо'}).status_code, 429)


class LoadSchoolsTests(TestCase):
    def write(self, rows):
        handle = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8',
                                             newline='')
        writer = csv.DictWriter(handle, fieldnames=['name', 'short_name', 'number', 'kind',
                                                    'city', 'region'])
        writer.writeheader()
        writer.writerows(rows)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_twice_gives_the_same_rows(self):
        path = self.write([
            {'name': 'Школа № 57', 'city': 'Москва', 'region': 'Москва', 'kind': 'ГБОУ'},
            {'name': 'Лицей «Вторая школа»', 'number': '2', 'city': 'Москва', 'region': 'Москва'},
            {'name': '', 'city': 'Москва'},
        ])
        call_command('load_schools', path, '--apply', stdout=open(os.devnull, 'w'))
        self.assertEqual(School.objects.count(), 2)
        call_command('load_schools', path, '--apply', stdout=open(os.devnull, 'w'))
        self.assertEqual(School.objects.count(), 2)
        self.assertEqual(School.objects.get(name='Школа № 57').number, 57)
        self.assertEqual(School.objects.get(number=2).city_norm, 'москва')

    def test_dry_run_writes_nothing(self):
        path = self.write([{'name': 'Школа № 1', 'city': 'Тула', 'region': 'Тульская область'}])
        call_command('load_schools', path, stdout=open(os.devnull, 'w'))
        self.assertEqual(School.objects.count(), 0)
