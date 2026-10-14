"""Импорт олимпиады из эталона: `import_olympiad_reference` (сессия И2, 14.10.2026).

Данные выдуманные; кандидаты гибридного поиска подкладываются файлом
(модель в тестах не грузится), KaTeX не запускается (`--no-katex`).
"""
import json
import os
import shutil
import tempfile
from decimal import Decimal

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from catalog.filters import base_queryset
from problems.models import (
    OlympiadRef, Problem, ProblemFigure, ProblemPart, ReviewVerdict, Source,
    SourceReference,
)
from problems.olympiad_audit import reference_import as ri
from problems.olympiad_audit import registry

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06'
       b'\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe'
       b'\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82')
SLUG = 'vp-fingram'
PDF = 'raw/pdf/olymp.hse.ru__data__2019__x__Финграм 11.pdf'
URL = 'https://olymp.hse.ru/data/2019/x/Финграм 11.pdf'

# Длинные тексты с числами: «привязка» должна пройти числовой отпечаток.
BANK_TEXT = ('Вкладчик кладёт 120 000 рублей на депозит под 7,5 % годовых на 18 месяцев '
             'с ежеквартальной капитализацией. Банк Б предлагает 8,2 % без капитализации '
             'на 540 дней, банк В — 6,9 % с ежемесячной капитализацией. Рассчитайте '
             'эффективную ставку каждого банка и выберите лучший вариант для вкладчика.')
DOUBT_TEXT = ('Семья тратит 45 000 рублей в месяц на продукты, 12 000 на транспорт и '
              '18 500 на коммунальные услуги; доход семьи 96 000 рублей. Составьте бюджет '
              'на квартал и найдите, сколько можно отложить, если цены вырастут на 4 %.')


def _row(number, statement, **extra):
    row = {
        'event_id': 'vp-fingram-2019-final-11-v1', 'number': str(number), 'task_variant': '',
        'title': f'Задание {number}', 'year': 2019, 'academic_year': '2018/2019',
        'stage': 'final', 'grade': '11', 'statement_md': statement, 'parts': [],
        'figures': [], 'solution_figures': [], 'solution_md': 'Решение.', 'answer': '42',
        'criteria_md': '', 'max_score': 10, 'source_file': [PDF],
        'source_pages': [PDF + '#p1'], 'official': True, 'source': 'official',
        'olympiad_slug': SLUG, 'auto_publish_ok': True, 'auto_publish_fail': [],
        'auto_publish_notes': [],
    }
    row.update(extra)
    return row


class ImportReferenceCommandTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.sub = os.path.join(self.tmp, 'vp_fingram')
        self.dig = os.path.join(self.sub, 'digitized')
        os.makedirs(os.path.join(self.dig, 'figures_clean_v2'))
        with open(os.path.join(self.dig, 'figures_clean_v2', 'fig_3_1.png'), 'wb') as h:
            h.write(PNG)
        with open(os.path.join(self.sub, 'download_plan.csv'), 'w', encoding='utf-8') as h:
            h.write('url,file,official\n')
            h.write(f'"{URL}",{PDF},true\n')
        entry = registry.get(SLUG)
        self.source = Source.objects.create(name=entry.official_source_name)
        # Задача банка: тот же текст, решение пустое, ответ ЗАПОЛНЕН.
        self.bank = Problem.objects.create(
            statement=BANK_TEXT, answer='старый ответ', solution='',
            status='published', content_format='markdown')
        self.doubt = Problem.objects.create(
            statement=DOUBT_TEXT.replace('45 000', '41 000').replace('квартал', 'полгода')
            .replace('отложить', 'сберечь, откладывая каждый месяц понемногу,'),
            status='published', content_format='markdown')
        rows = [
            _row(1, BANK_TEXT, answer='новый ответ', solution_md='Официальное решение.',
                 criteria_md='*Критерии оценивания:*\n1. Верно — 10 баллов'),
            _row(2, DOUBT_TEXT),
            _row(3, 'На рисунке показан график доходов семьи за 2019 год. Что видно на графике?',
                 figures=[{'path': 'figures_clean_v2/fig_3_1.png', 'caption': 'Доходы семьи',
                           'flag': '', 'page': 1, 'page_dir': 'pages/x'}]),
            _row(4, 'Человеку на проверку: условие без ответа, 2019 год, 15 000 рублей.',
                 auto_publish_ok=False, auto_publish_fail=['нет ответа/решения при файле решений']),
        ]
        self.queue = os.path.join(self.sub, 'import_queue_v2.jsonl')
        with open(self.queue, 'w', encoding='utf-8') as h:
            for r in rows:
                h.write(json.dumps(r, ensure_ascii=False) + '\n')
        self.out = os.path.join(self.sub, 'import_journal')
        os.makedirs(self.out)
        cands = {'vp-fingram-2019-final-11-v1:1': [self.bank.id, self.doubt.id],
                 'vp-fingram-2019-final-11-v1:2': [self.doubt.id, self.bank.id],
                 'vp-fingram-2019-final-11-v1:3': [self.bank.id],
                 'vp-fingram-2019-final-11-v1:4': [self.bank.id]}
        with open(os.path.join(self.out, 'bank_candidates.json'), 'w', encoding='utf-8') as h:
            json.dump({'meta': {}, 'candidates': cands}, h)

    def run_cmd(self, *extra):
        call_command('import_olympiad_reference', '--olympiad', SLUG, '--queue', self.queue,
                     '--out-dir', self.out, '--no-katex', '--bundle-date', '20261014', *extra,
                     stdout=open(os.devnull, 'w', encoding='utf-8'))

    def apply(self):
        self.run_cmd('--apply', '--yes-i-have-owner-approval')
        journals = sorted(f for f in os.listdir(self.out)
                          if f.startswith('import_') and not f.endswith('_dryrun.json'))
        return os.path.join(self.out, journals[-1])

    def new_problems(self):
        return Problem.objects.filter(source_references__source=self.source).distinct()

    def test_1_existing_nonempty_field_never_changes(self):
        self.apply()
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.answer, 'старый ответ')          # непустое — не трогаем
        self.assertIn('Официальное решение.', self.bank.solution)    # пустое — дописано
        self.assertIn('Критерии оценивания', self.bank.solution)
        ref = OlympiadRef.objects.get(problem=self.bank, olympiad_slug=SLUG)
        self.assertEqual(ref.source_site, 'official')

    def test_2_auto_publish_false_creates_hidden(self):
        self.apply()
        hidden = self.new_problems().get(statement__startswith='Человеку')
        self.assertEqual(hidden.status, 'draft')
        self.assertTrue(hidden.hidden_pending_review)
        self.assertEqual(hidden.human_review, '')
        self.assertFalse(ReviewVerdict.objects.filter(problem=hidden).exists())
        self.assertFalse(base_queryset('catalog').filter(pk=hidden.pk).exists())
        with open(os.path.join(self.out, 'human_tasks_import.csv'), encoding='utf-8-sig') as h:
            self.assertIn('vp-fingram-2019-final-11-v1:4', h.read())

    def test_3_auto_published_survives_review_gates(self):
        self.apply()
        visible = self.new_problems().get(statement__startswith='На рисунке')
        self.assertTrue(base_queryset('catalog').filter(pk=visible.pk).exists())
        verdict = ReviewVerdict.objects.get(problem=visible)
        self.assertEqual((verdict.category, verdict.reviewer, verdict.bundle),
                         ('perfect', 'auto:strict_check', 'auto_import_vp-fingram_20261014'))
        devnull = open(os.devnull, 'w', encoding='utf-8')
        call_command('human_review_mark', '--apply', stdout=devnull)
        call_command('pending_review_gate', '--apply', stdout=devnull)
        visible.refresh_from_db()
        self.assertEqual(visible.human_review, 'approved')
        self.assertFalse(visible.hidden_pending_review)
        self.assertTrue(base_queryset('catalog').filter(pk=visible.pk).exists())

    def test_4_second_import_creates_nothing(self):
        self.apply()
        before = (Problem.objects.count(), OlympiadRef.objects.count(),
                  SourceReference.objects.count(), ProblemFigure.objects.count())
        self.apply()
        after = (Problem.objects.count(), OlympiadRef.objects.count(),
                 SourceReference.objects.count(), ProblemFigure.objects.count())
        self.assertEqual(before, after)

    def test_5_rollback_removes_everything_and_empties_filled(self):
        counts = (Problem.objects.count(), ProblemPart.objects.count(),
                  SourceReference.objects.count(), ProblemFigure.objects.count(),
                  OlympiadRef.objects.count(), ReviewVerdict.objects.count())
        journal = self.apply()
        self.assertGreater(Problem.objects.count(), counts[0])
        call_command('import_olympiad_reference', '--olympiad', SLUG, '--rollback', journal,
                     '--apply', '--yes-i-have-owner-approval',
                     stdout=open(os.devnull, 'w', encoding='utf-8'))
        self.assertEqual(counts, (Problem.objects.count(), ProblemPart.objects.count(),
                                  SourceReference.objects.count(), ProblemFigure.objects.count(),
                                  OlympiadRef.objects.count(), ReviewVerdict.objects.count()))
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.solution, '')
        self.assertEqual(self.bank.answer, 'старый ответ')

    def test_6_doubtful_pair_not_linked(self):
        self.apply()
        self.assertFalse(OlympiadRef.objects.filter(problem=self.doubt).exists())
        with open(os.path.join(self.out, 'link_review.csv'), encoding='utf-8-sig') as h:
            text = h.read()
        self.assertIn('vp-fingram-2019-final-11-v1:2', text)
        self.assertFalse(self.new_problems().filter(statement__startswith='Семья').exists())

    def test_7_figure_marker_and_problem_figure(self):
        self.apply()
        p = self.new_problems().get(statement__startswith='На рисунке')
        fig = ProblemFigure.objects.get(problem=p)
        self.assertIn(f'[[FIGURE:{fig.tikz_hash}]]', p.statement)
        self.assertEqual(bytes(fig.image_data), PNG)
        self.assertEqual(fig.source_field, 'statement')
        # Маркер — после абзаца с «рисунке», а не в начале.
        self.assertTrue(p.statement.startswith('На рисунке'))

    def test_8_source_url_is_site_not_local_path(self):
        self.apply()
        for sref in SourceReference.objects.filter(source=self.source):
            self.assertTrue(sref.url.startswith('https://olymp.hse.ru/'), sref.url)
            self.assertNotIn(' ', sref.url)
            self.assertNotIn('raw/pdf', sref.url)
        for ref in OlympiadRef.objects.filter(olympiad_slug=SLUG):
            self.assertTrue(ref.official_url.startswith('https://olymp.hse.ru/'), ref.official_url)

    def test_9_dry_run_writes_nothing(self):
        before = Problem.objects.count(), OlympiadRef.objects.count()
        self.run_cmd()
        self.assertEqual(before, (Problem.objects.count(), OlympiadRef.objects.count()))


class ReferenceRulesTests(SimpleTestCase):
    def test_tail_parts_cut_and_points(self):
        st = 'Вводный текст задачи.\n\n- а) (2 балла) Первый пункт;\n- б) (5 баллов) Второй пункт.'
        parts = [{'label': 'а', 'text': '(2 балла) Первый пункт;'},
                 {'label': 'б', 'text': '(5 баллов) Второй пункт.'}]
        head, ok, _why = ri.split_parts_from_statement(st, parts)
        self.assertTrue(ok)
        self.assertEqual(head, 'Вводный текст задачи.')
        self.assertEqual(ri.part_points(parts[1]['text']), Decimal('5'))

    def test_woven_parts_stay(self):
        st = 'Интервью.\n\n1. Вопрос один?\n\nОтвет эксперта длинный.\n\n2. Вопрос два?'
        parts = [{'label': '1', 'text': 'Вопрос один?'}, {'label': '2', 'text': 'Вопрос два?'}]
        _head, ok, _why = ri.split_parts_from_statement(st, parts)
        self.assertFalse(ok)

    def test_answer_split_only_when_labels_match(self):
        self.assertEqual(ri.split_answer('а) 1; б) 2', ['а', 'б']), {'а': '1', 'б': '2'})
        self.assertIsNone(ri.split_answer('а) 1; в) 2', ['а', 'б']))

    def test_markup_adapted(self):
        text, counts = ri.adapt_markup('| a<br>b | <u>c</u> |\n# Заголовок\n---\nx<br>y')
        self.assertEqual(text, '| a b | *c* |\n**Заголовок**\n\nx\ny')
        self.assertEqual(counts, {'br в таблице': 1, 'u': 1, '#': 1, '---': 1, 'br': 1})

    def test_figure_anchor_after_block(self):
        text, how = ri.place_figures('Абзац первый про банк.\n\nАбзац второй о доходах семьи.',
                                     [('[[F]]', '', ('after', 'Абзац первый про банк.'))])
        self.assertEqual(text, 'Абзац первый про банк.\n\n[[F]]\n\nАбзац второй о доходах семьи.')
        self.assertEqual(how, ['по странице PDF'])

    def test_url_quoted(self):
        self.assertEqual(ri.quote_url('https://olymp.hse.ru/data/Финграм 11.pdf'),
                         'https://olymp.hse.ru/data/%D0%A4%D0%B8%D0%BD%D0%B3%D1%80%D0%B0%D0%BC%2011.pdf')
