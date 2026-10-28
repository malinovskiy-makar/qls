"""Строка олимпиады под заголовком задачи (решение 15.10.2026, гейт 1 И3 28.10):
привязки official и ILE, SolveHub не показывается; одинаковые строки склеены;
до трёх строк, дальше «и ещё N»."""
from django.test import TestCase
from django.urls import reverse

from catalog.olympiad_line import olympiad_lines, ref_line
from problems.models import OlympiadRef
from problems.tests.factories import make_problem

VP_FG = 'Олимпиада школьников «Высшая проба» по финансовой грамотности'


def _ref(problem, n, site='official', **kw):
    data = dict(problem=problem, source_site=site, olympiad_slug='vp-fingram', olympiad_name=VP_FG,
                academic_year='2018/2019', year=2019, stage='final', grade='11', variant='v1',
                number=str(n), event_id=f'vp-fingram-2019-final-11-{site}-{n}',
                record_id=f'{site}:{n}', match_method='url_exact', match_score=1.0)
    data.update(kw)
    return OlympiadRef.objects.create(**data)


class OlympiadLineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.with_ref = make_problem('Условие с привязкой.', title='Как не потерять деньги?')
        _ref(cls.with_ref, 3)
        cls.bare = make_problem('Условие без привязки.', title='Без олимпиады')
        cls.only_solvehub = make_problem('Только SolveHub.', title='Агрегатор')
        _ref(cls.only_solvehub, 7, site='solvehub')

    def _html(self, problem):
        return self.client.get(reverse('catalog:problem_detail', args=[problem.pk])).content.decode()

    def test_line_format(self):
        line = ref_line(self.with_ref.olympiad_refs.get())
        self.assertEqual(line, '«Высшая проба» по финансовой грамотности · 2018/19 · '
                               'заключительный этап · 11 класс · задание 3')

    def test_line_on_page_only_with_ref(self):
        self.assertIn('class="pd-olymp"', self._html(self.with_ref))
        self.assertIn('2018/19 · заключительный этап · 11 класс · задание 3', self._html(self.with_ref))
        self.assertNotIn('class="pd-olymp"', self._html(self.bare))

    def test_solvehub_is_not_shown(self):
        self.assertNotIn('class="pd-olymp"', self._html(self.only_solvehub))
        p = make_problem('ILE и SolveHub.', title='Два сайта')
        _ref(p, 1, site='ile', event_id='ile-1')
        _ref(p, 2, site='solvehub', event_id='sh-1')
        self.assertEqual(len(olympiad_lines(p.olympiad_refs.all())['lines']), 1)

    def test_same_lines_are_glued(self):
        p = make_problem('Одна задача, две одинаковые строки.', title='Склейка')
        _ref(p, 4, event_id='a')
        _ref(p, 4, site='ile', event_id='b')
        self.assertEqual(olympiad_lines(p.olympiad_refs.all()), {
            'lines': ['«Высшая проба» по финансовой грамотности · 2018/19 · заключительный этап · '
                      '11 класс · задание 4'], 'more': 0})

    def test_and_n_more(self):
        p = make_problem('Пять туров.', title='Много привязок')
        for n in range(1, 6):
            _ref(p, n, event_id=f'e{n}')
        got = olympiad_lines(p.olympiad_refs.all())
        self.assertEqual((len(got['lines']), got['more']), (3, 2))
        self.assertIn('и ещё 2', self._html(p))

    def test_noise_variant_hidden_and_real_variant_shown(self):
        p = make_problem('Вариант.', title='Вариант')
        _ref(p, 1, variant='v2', grade='9-10', event_id='v2')
        self.assertIn('9–10 классы · вариант 2 · задание 1', ref_line(p.olympiad_refs.get()))
