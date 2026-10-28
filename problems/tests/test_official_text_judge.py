"""Судья Claude и замена текста банка официальным (решение 28.10.2026, ADR 0163).

Модель не вызывается: `text_judge.call_model` подменяется ответом-строкой,
пакетный путь — подменой `submit_batch` / `batch_status` / `batch_results`.
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

    def test_one_problem_two_tasks_replaced_once(self):
        """Задача банка привязана к двум заданиям (варианты классов) — одна замена, повтор ноль."""
        with open(self.journal, encoding='utf-8') as h:
            j = json.load(h)
        with open(j['inputs']['queue'], encoding='utf-8') as h:
            row = json.loads(h.readline())
        row2 = dict(row, event_id='vp-fingram-2019-final-10-v1', statement_md=OFFICIAL + ' Вариант 10.')
        with open(j['inputs']['queue'], 'a', encoding='utf-8') as h:
            h.write(json.dumps(row2, ensure_ascii=False) + '\n')
        j['plan'].append({'key': 'vp-fingram-2019-final-10-v1:2', 'action': 'link', 'pid': self.bank.id,
                          'reason': 'сходство'})
        with open(self.journal, 'w', encoding='utf-8') as h:
            json.dump(j, h)
        self.judge(_reply())
        self.apply('--apply', '--yes-i-have-owner-approval')
        self.assertEqual(ProblemVersion.objects.filter(problem=self.bank).count(), 1)
        self.bank.refresh_from_db()
        first = self.bank.statement
        self.apply('--apply', '--yes-i-have-owner-approval')                  # повтор — ноль
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.statement, first)
        self.assertEqual(ProblemVersion.objects.filter(problem=self.bank).count(), 1)

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


    def test_batch_submit_once_resume_and_half_price(self):
        """--batch: один пакет, id в F.batch.json; обрыв ожидания → повтор не шлёт второй пакет."""
        sent = []

        def submit(requests):
            sent.append(requests)
            return 'msgbatch_1'

        reply = _reply()
        with mock.patch.object(tj, 'submit_batch', side_effect=submit), \
                mock.patch.object(tj, 'batch_status', side_effect=KeyboardInterrupt), \
                mock.patch.object(tj, 'call_model', side_effect=AssertionError('синхронный вызов')):
            with self.assertRaises(KeyboardInterrupt):
                call_command('olympiad_text_judge', '--kind', 'replace', '--journal', self.journal,
                             '--out', self.verdicts, '--yes', '--max-usd', '1', '--batch', stdout=_quiet())
        self.assertEqual(len(sent), 1)
        cid, params = sent[0][0]
        self.assertNotIn('temperature', params)
        self.assertTrue(os.path.isfile(self.verdicts + '.batch.json'))
        with mock.patch.object(tj, 'submit_batch', side_effect=AssertionError('второй пакет')), \
                mock.patch.object(tj, 'batch_status', return_value=('ended', {})), \
                mock.patch.object(tj, 'batch_results', return_value={cid: reply}):
            call_command('olympiad_text_judge', '--kind', 'replace', '--journal', self.journal,
                         '--out', self.verdicts, '--max-usd', '1', stdout=_quiet())
        self.assertFalse(os.path.isfile(self.verdicts + '.batch.json'))
        with open(self.verdicts, encoding='utf-8') as h:
            rec = json.loads(h.readline())
        self.assertTrue(rec['verdict']['replace'])
        self.assertAlmostEqual(rec['usd'], tj.cost_of('claude-sonnet-5-5', reply[1]) / 2)

    def test_batch_cut_by_budget(self):
        with mock.patch.object(tj, 'submit_batch', side_effect=AssertionError('пакет сверх потолка')):
            call_command('olympiad_text_judge', '--kind', 'replace', '--journal', self.journal,
                         '--out', self.verdicts, '--yes', '--max-usd', '0.001', '--batch', stdout=_quiet())
        self.assertFalse(os.path.exists(self.verdicts + '.batch.json'))


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
                                                                 'output_tokens': 0}), 2.0)
        self.assertAlmostEqual(tj.cost_of('claude-sonnet-5-5', {'output_tokens': 1_000_000}, batch=True), 5.0)

    def test_request_has_no_temperature_and_cut_reply_is_error(self):
        params = tj.request_params('s', [{'type': 'text', 'text': 'x'}])
        self.assertNotIn('temperature', params)
        msg = mock.Mock(stop_reason='max_tokens', content=[])
        with self.assertRaises(ValueError):
            tj.reply_text(msg)
