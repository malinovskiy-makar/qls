"""Судья Claude и замена текста банка официальным (решение 28.10.2026, ADR 0163).

Модель не вызывается: `text_judge.call_model` подменяется ответом-строкой.
"""
import json
import os
import shutil
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from problems.models import Problem, ProblemPart, ProblemVersion, ReviewVerdict
from problems.olympiad_audit import text_judge as tj

KEY = 'vp-fingram-2019-final-11-v1:2'
OFFICIAL = ('У семьи доход 96 000 рублей. Таблица расходов:\n\n| статья | руб. |\n|---|---|\n'
            '| еда | 45 000 |\n| транспорт | 12 000 |\n\nСоставьте бюджет на квартал.')
BANK = 'У семьи доход 96 000 рублей. Составьте бюджет на квартал.'


def _quiet():
    return open(os.devnull, 'w', encoding='utf-8')


def _reply(**kw):
    data = {'replace': True, 'missing': ['table'], 'reasons': 'в банке нет таблицы',
            'evidence': ['| еда | 45 000 |'], 'confidence': 0.9}
    data.update(kw)
    return json.dumps(data, ensure_ascii=False), {'input_tokens': 1000, 'output_tokens': 100}


class OfficialTextReplaceTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        dig = os.path.join(self.tmp, 'vp_fingram', 'digitized')
        os.makedirs(dig)
        queue = os.path.join(dig, 'q.jsonl')
        row = {'event_id': 'vp-fingram-2019-final-11-v1', 'number': '2', 'task_variant': '',
               'title': 'Бюджет', 'year': 2019, 'academic_year': '2018/2019', 'stage': 'final',
               'grade': '11', 'statement_md': OFFICIAL, 'parts': [], 'figures': [],
               'solution_figures': [], 'solution_md': '', 'answer': '', 'criteria_md': '',
               'source_file': ['raw/pdf/x.pdf'], 'source_pages': []}
        with open(queue, 'w', encoding='utf-8') as h:
            h.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.bank = Problem.objects.create(statement=BANK, status='published', content_format='plain')
        ProblemPart.objects.create(problem=self.bank, label='а', statement='Старый пункт', order=0)
        self.journal = os.path.join(self.tmp, 'import_vp-fingram_x.json')
        with open(self.journal, 'w', encoding='utf-8') as h:
            json.dump({'command': 'import_olympiad_reference', 'applied': True, 'olympiad': 'vp-fingram',
                       'inputs': {'queue': queue, 'digitized': dig},
                       'plan': [{'key': KEY, 'action': 'link', 'pid': self.bank.id, 'reason': 'сходство'}]}, h)
        self.verdicts = os.path.join(self.tmp, 'verdicts.jsonl')

    def judge(self, reply):
        with mock.patch.object(tj, 'call_model', return_value=reply):
            call_command('olympiad_text_judge', '--kind', 'replace', '--journal', self.journal,
                         '--out', self.verdicts, '--yes', '--max-usd', '1', stdout=_quiet())

    def apply(self, *extra):
        call_command('apply_official_text', '--verdicts', self.verdicts, '--journal', self.journal,
                     '--out-dir', self.tmp, *extra, stdout=_quiet())
        return sorted(f for f in os.listdir(self.tmp) if f.startswith('official_text_') and 'dryrun' not in f)

    def test_replace_snapshot_repeat_rollback(self):
        self.judge(_reply())
        self.apply()                                     # сухой — ничего
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.statement, BANK)
        done = self.apply('--apply', '--yes-i-have-owner-approval')
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.statement, OFFICIAL)
        self.assertEqual(self.bank.content_format, 'markdown')
        version = ProblemVersion.objects.get(problem=self.bank)
        self.assertEqual(version.snapshot['statement'], BANK)
        self.assertTrue(version.note.startswith('замена официальным эталоном: '))
        self.assertEqual(self.bank.parts.get().statement, 'Старый пункт')   # подпункт не удалён
        self.apply('--apply', '--yes-i-have-owner-approval')                  # повтор — ноль
        self.assertEqual(ProblemVersion.objects.filter(problem=self.bank).count(), 1)
        call_command('apply_official_text', '--rollback', os.path.join(self.tmp, done[0]), '--apply',
                     '--yes-i-have-owner-approval', stdout=_quiet())
        self.bank.refresh_from_db()
        self.assertEqual((self.bank.statement, self.bank.content_format), (BANK, 'plain'))
        self.assertFalse(ProblemVersion.objects.filter(problem=self.bank).exists())

    def test_low_confidence_or_no_quotes_not_replaced(self):
        self.judge(_reply(confidence=0.7))
        self.apply('--apply', '--yes-i-have-owner-approval')
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.statement, BANK)

    def test_human_approved_only_structural(self):
        self.bank.human_review = 'approved'
        self.bank.save(update_fields=['human_review'])
        ReviewVerdict.objects.create(problem=self.bank, bundle='b', category='perfect', reviewer='Андрей')
        self.judge(_reply(missing=['text']))
        self.apply('--apply', '--yes-i-have-owner-approval')
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.statement, BANK)
        os.remove(self.verdicts)
        self.judge(_reply(missing=['table']))
        self.apply('--apply', '--yes-i-have-owner-approval')
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.statement, OFFICIAL)

    def test_without_yes_model_not_called(self):
        with mock.patch.object(tj, 'call_model', side_effect=AssertionError('модель позвали')):
            call_command('olympiad_text_judge', '--kind', 'replace', '--journal', self.journal,
                         '--out', self.verdicts, stdout=_quiet())
        self.assertFalse(os.path.exists(self.verdicts))

    def test_pairs_to_decisions(self):
        with open(self.journal, encoding='utf-8') as h:
            j = json.load(h)
        j['plan'][0]['action'] = 'review'
        with open(self.journal, 'w', encoding='utf-8') as h:
            json.dump(j, h)
        out = os.path.join(self.tmp, 'dec.json')
        reply = (json.dumps({'same': 'same', 'evidence': ['96 000'], 'reasons': 'тот же сюжет',
                             'confidence': 0.95}), {'input_tokens': 10, 'output_tokens': 5})
        with mock.patch.object(tj, 'call_model', return_value=reply):
            call_command('olympiad_text_judge', '--kind', 'pairs', '--journal', self.journal,
                         '--out', self.verdicts, '--decisions-out', out, '--yes', '--max-usd', '1',
                         stdout=_quiet())
        with open(out, encoding='utf-8') as h:
            rows = json.load(h)['rows']
        self.assertEqual((rows[0]['key'], rows[0]['decision'], rows[0]['bank_id']), (KEY, 'link', self.bank.id))


class JudgeRulesTests(SimpleTestCase):
    def test_pair_decision(self):
        self.assertEqual(tj.pair_decision({'same': 'different', 'evidence': ['x'], 'confidence': 0.9}), 'new')
        self.assertEqual(tj.pair_decision({'same': 'same', 'evidence': ['x'], 'confidence': 0.6}), 'unsure')
        self.assertEqual(tj.pair_decision({'same': 'same', 'evidence': [], 'confidence': 0.99}), 'unsure')
        self.assertEqual(tj.pair_decision({'same': 'unsure', 'evidence': ['x'], 'confidence': 0.99}), 'unsure')

    def test_parse_replace_filters_kinds_and_bounds(self):
        v = tj.parse_replace('Ответ: {"replace": true, "missing": ["table", "мусор"], "reasons": "r", '
                             '"evidence": ["q"], "confidence": 0.85}')
        self.assertEqual(v['missing'], ['table'])
        with self.assertRaises(ValueError):
            tj.parse_replace('{"replace": true, "confidence": 3}')

    def test_cost(self):
        self.assertAlmostEqual(tj.cost_of('claude-sonnet-5-5', {'input_tokens': 1_000_000,
                                                                 'output_tokens': 0}), 3.0)
