"""solvehub_parts_restore: возврат потерянных пунктов SolveHub (13.10.2026).

Данные синтетические, во временной папке: «августовская» выгрузка (запись 1 +
`image_map.json`) и «перекачка» (`_parts` + `parts_summary.csv`). Задачи в базе
создаёт тот же `create_problem` из текста того же конвейера, что настоящий
импорт, — значит, база в тесте устроена как дома, а не как удобно тесту.
"""
import base64
import csv
import hashlib
import json
import shutil
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from problems.corpus_converter.ingest import create_problem
from problems.corpus_converter.reconvert import solvehub_records
from problems.management.commands import solvehub_parts_restore as cmd
from problems.models import Problem, ProblemFigure, ProblemPart, Source

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32


def rec(h, md, parent='', answer=None, check_type='single_freetext', options=None, solution=''):
    value = answer if answer is not None else None
    return {'hash': h, 'parent_hash': parent, 'md': md, 'answer_md': solution,
            'check_type': check_type,
            'check_options': json.dumps(options, ensure_ascii=False) if options else '',
            'correct_answer': json.dumps({'type': check_type, 'value': value}, ensure_ascii=False),
            'title': ''}


def chain(h, records):
    """Записи 2..N получают свои хэши и родителя — предыдущую запись."""
    out = [dict(records[0], hash=h, parent_hash='')]
    for i, r in enumerate(records[1:], start=2):
        out.append(dict(r, hash='%s-%d' % (h, i), parent_hash=out[-1]['hash']))
    return out


A_RECORDS = [
    rec('', 'Фирма производит товар.\n\nа) Найдите прибыль.', answer=['10'], solution='Прибыль 10.'),
    rec('', 'б) Найдите выручку.', answer=['20'], solution='Выручка 20.'),
    rec('', 'в) Выберите издержки.', answer=1, check_type='single_choice', options=['5', '7'],
        solution='Издержки 7.'),
]
B_RECORDS = [
    rec('', 'Рынок задан функциями спроса и предложения.\n\n$а)$ ( $5$ баллов) Найдите равновесие.',
        answer=['P=5'], solution='Равновесие P=5.'),
    rec('', '$б)$ ( $5$ баллов) Найдите излишек.', answer=['12'], solution='Излишек 12.'),
    rec('', '$в)$ ( $5$ баллов) Введите налог.', answer=None, check_type='ai_graded'),
    rec('', '$г)$ ( $5$ баллов) Сравните.', answer=None, check_type='ai_graded', solution='Сравнение.'),
]


class _Data(TestCase):
    """Строит выгрузки на диске и «импортирует» задачи в тестовую базу."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='qls-shparts-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.old = self.tmp / 'solvehub'
        self.new = self.tmp / 'solvehub_v2'
        self.report = self.tmp / 'report'
        for d in (self.old / 'problems', self.old / 'images', self.new / 'problems'):
            d.mkdir(parents=True)
        (self.old / 'image_map.json').write_text('{}', encoding='utf-8')
        self.source = Source.objects.create(name='SolveHub – банк задач по экономике')
        self.rows = []

    def add_image(self, url):
        name = hashlib.md5(url.encode()).hexdigest() + '.png'
        (self.old / 'images' / name).write_bytes(PNG)
        mapping = json.loads((self.old / 'image_map.json').read_text(encoding='utf-8'))
        mapping[url] = name
        (self.old / 'image_map.json').write_text(json.dumps(mapping), encoding='utf-8')

    def add(self, h, records, db_parts_now=None):
        """Записи на диск + задача в базу так, как её положил бы импорт."""
        records = chain(h, records)
        first = dict(records[0])
        (self.old / 'problems' / ('%s.json' % h)).write_text(
            json.dumps(first, ensure_ascii=False), encoding='utf-8')
        (self.new / 'problems' / ('%s.json' % h)).write_text(
            json.dumps(dict(first, _parts=records), ensure_ascii=False), encoding='utf-8')
        r = solvehub_records(str(self.old), only={h})[h]
        p = create_problem(source=self.source, external_id=h, title='', statement_md=r.statement,
                           answer_md=r.answer, solution_md=r.solution,
                           parts=[{'label': lab, 'statement_md': t} for lab, t in r.parts])
        self.rows.append({'hash': h, 'problem_id': p.pk, 'lost': 'True',
                          'db_parts_now': db_parts_now if db_parts_now is not None else len(r.parts)})
        self.write_summary()
        return p

    def write_summary(self):
        with open(self.new / 'parts_summary.csv', 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=['hash', 'problem_id', 'lost', 'db_parts_now'])
            w.writeheader()
            w.writerows(self.rows)

    def run_cmd(self, *args):
        out = StringIO()
        call_command('solvehub_parts_restore', '--data-dir', str(self.new), '--old-dir', str(self.old),
                     '--report-dir', str(self.report), *args, stdout=out, stderr=out)
        return out.getvalue()

    def summary(self, name='dryrun_summary.json'):
        return json.loads((self.report / name).read_text(encoding='utf-8'))

    def latest(self, name):
        """Свежий список: при --apply имена с префиксом applied_<время>_."""
        return max(self.report.glob('*' + name), key=lambda path: path.stat().st_mtime_ns)

    def manual(self):
        with open(self.latest('manual_list.csv'), encoding='utf-8-sig') as fh:
            return {int(r['problem_id']): r['reason'] for r in csv.DictReader(fh)}

    def snapshots(self):
        return sorted(self.report.glob('snapshot_*.json'))

    def state(self, *problems):
        """Всё, что команда могла бы задеть, — побайтно."""
        rows = []
        for p in problems:
            p = Problem.objects.get(pk=p.pk)
            rows.append([p.statement, p.answer, p.solution, p.content_hash, p.problem_type,
                         list(ProblemPart.objects.filter(problem=p).order_by('pk').values_list(
                             'pk', 'label', 'statement', 'answer', 'solution', 'points', 'order'))])
        rows.append([Problem.objects.count(), ProblemPart.objects.count(), ProblemFigure.objects.count()])
        return hashlib.sha256(repr(rows).encode('utf-8')).hexdigest()

    def parts(self, p):
        return list(ProblemPart.objects.filter(problem=p).order_by('order', 'pk'))

    def assert_untouched(self, p, reason_part, *args):
        """Не прошла гейт: не меняется и попадает в список с причиной."""
        before = self.state(p)
        self.run_cmd('--apply', *args)
        self.assertEqual(self.state(p), before)
        self.assertIn(p.pk, self.manual())
        self.assertIn(reason_part, self.manual()[p.pk])


class GroupATests(_Data):
    def test_adds_missing_parts_and_touches_nothing_else(self):
        p = self.add('A1', A_RECORDS)
        before = Problem.objects.get(pk=p.pk)
        a_before = self.parts(p)[0]
        self.assertEqual([x.label for x in self.parts(p)], ['а'])
        self.run_cmd('--apply')
        after = Problem.objects.get(pk=p.pk)
        self.assertEqual((after.statement, after.answer, after.solution),
                         (before.statement, before.answer, before.solution))
        parts = self.parts(p)
        self.assertEqual([x.label for x in parts], ['а', 'б', 'в'])
        self.assertEqual([x.order for x in parts], [0, 1, 2])
        a = parts[0]
        self.assertEqual((a.pk, a.label, a.statement, a.answer, a.solution, a.order),
                         (a_before.pk, a_before.label, a_before.statement, a_before.answer,
                          a_before.solution, a_before.order))
        self.assertEqual(parts[1].statement, 'Найдите выручку.')
        self.assertEqual(parts[1].answer, '20')
        self.assertEqual(parts[1].solution, 'Выручка 20.')
        # Варианты выбора — в тексте пункта, ответ — номером варианта с единицы.
        self.assertIn('Варианты ответа:', parts[2].statement)
        self.assertEqual(parts[2].answer, '2. 7')
        self.assertIsNone(parts[1].points)


class GroupBTests(_Data):
    def test_statement_becomes_header_and_all_parts_created(self):
        p = self.add('B1', B_RECORDS)
        old_statement = p.statement
        old_answer, old_solution = p.answer, p.solution
        self.assertEqual(self.parts(p), [])
        self.run_cmd('--apply')
        p.refresh_from_db()
        self.assertEqual(p.statement, 'Рынок задан функциями спроса и предложения.')
        self.assertEqual((p.answer, p.solution), (old_answer, old_solution))
        parts = self.parts(p)
        self.assertEqual([x.label for x in parts], ['а', 'б', 'в', 'г'])
        self.assertEqual([x.order for x in parts], [0, 1, 2, 3])
        self.assertTrue(parts[0].statement.startswith('( $5$ баллов) Найдите равновесие'))
        self.assertEqual(parts[0].answer, 'P=5')
        self.assertEqual(parts[1].answer, '12')
        self.assertEqual(parts[2].answer, '')
        self.assertEqual(parts[3].solution, 'Сравнение.')
        # Старое условие — в снимке группы B и в полном состоянии «до».
        snap_b = [s for s in self.snapshots() if '_B_' in s.name]
        self.assertEqual(len(snap_b), 1)
        snap = json.loads(snap_b[0].read_text(encoding='utf-8'))
        self.assertEqual(snap['problems'][0]['old']['statement'], old_statement)
        state = json.loads(next(self.report.glob('state_before_B_*.json')).read_text(encoding='utf-8'))
        self.assertEqual(state[str(p.pk)]['statement'], old_statement)

    def test_groups_get_separate_snapshots(self):
        self.add('A1', A_RECORDS)
        self.add('B1', B_RECORDS)
        self.run_cmd('--apply')
        names = [s.name for s in self.snapshots()]
        self.assertEqual(len(names), 2)
        self.assertTrue(any('_A_' in n for n in names) and any('_B_' in n for n in names))


class IdempotenceTests(_Data):
    def test_second_run_changes_nothing(self):
        a = self.add('A1', A_RECORDS)
        b = self.add('B1', B_RECORDS)
        self.run_cmd('--apply')
        state = self.state(a, b)
        self.run_cmd()
        s = self.summary()
        for g in ('A', 'B'):
            self.assertEqual(s['groups'][g]['parts_to_create'], 0)
            self.assertEqual(s['groups'][g]['statements_to_change'], 0)
            self.assertEqual(s['groups'][g]['already_done'], 1)
            self.assertEqual(s['groups'][g]['manual'], 0)
        snaps = len(self.snapshots())
        self.run_cmd('--apply')
        self.assertEqual(len(self.snapshots()), snaps)
        self.assertEqual(self.state(a, b), state)


class GateTests(_Data):
    """Задача, не прошедшая гейт, не меняется и попадает в список с причиной."""

    def test_broken_chain(self):
        p = self.add('A1', A_RECORDS)
        path = self.new / 'problems' / 'A1.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['_parts'][2]['parent_hash'] = 'чужой'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.assert_untouched(p, 'цепочка')

    def test_part_a_text_differs(self):
        p = self.add('A1', A_RECORDS)
        ProblemPart.objects.filter(problem=p).update(statement='Найдите убыток.')
        self.assert_untouched(p, 'текст подпункта а)')

    def test_two_parts_in_group_a(self):
        p = self.add('A1', A_RECORDS)
        ProblemPart.objects.create(problem=p, label='б', statement='чужой пункт', answer='', order=1)
        self.rows[-1]['db_parts_now'] = 2
        self.write_summary()
        self.assert_untouched(p, 'в базе 2 подпунктов')

    def test_edited_after_import(self):
        p = self.add('A1', A_RECORDS)
        Problem.objects.filter(pk=p.pk).update(updated_at=p.created_at + timedelta(days=1))
        self.assert_untouched(p, 'правилась после импорта')

    def test_edited_allowed_with_flag_only_if_answer_untouched(self):
        p = self.add('A1', A_RECORDS)
        Problem.objects.filter(pk=p.pk).update(updated_at=p.created_at + timedelta(days=1),
                                               answer='ручной ответ')
        self.assert_untouched(p, 'ответ или решение задачи изменены', '--include-edited')

    def test_header_differs_in_group_b(self):
        p = self.add('B1', B_RECORDS)
        Problem.objects.filter(pk=p.pk).update(statement=p.statement + ' Дописано.')
        self.assert_untouched(p, 'условие в базе')

    def test_image_not_in_map_is_blocked(self):
        records = [dict(r) for r in A_RECORDS]
        records[1] = dict(records[1], md='б) Посмотрите на график ![](https://media.solvehub.app/g.png)')
        p = self.add('A1', records)
        before = self.state(p)
        self.run_cmd('--apply')
        self.assertEqual(self.state(p), before)
        with open(self.latest('blocked_images.csv'), encoding='utf-8-sig') as fh:
            blocked = {int(r['problem_id']): r for r in csv.DictReader(fh)}
        self.assertIn(p.pk, blocked)
        self.assertIn('https://media.solvehub.app/g.png', blocked[p.pk]['urls'])

    def test_image_in_map_becomes_marker_and_figure(self):
        url = 'https://media.solvehub.app/g.png'
        self.add_image(url)
        records = [dict(r) for r in A_RECORDS]
        records[1] = dict(records[1], md='б) Посмотрите на график ![](%s)' % url)
        p = self.add('A1', records)
        self.run_cmd('--apply')
        digest = hashlib.sha256(url.encode()).hexdigest()
        self.assertIn('[[FIGURE:%s]]' % digest, self.parts(p)[1].statement)
        fig = ProblemFigure.objects.get(problem=p, tikz_hash=digest)
        self.assertEqual(bytes(fig.image_data), PNG)
        self.assertEqual(fig.content_type, 'image/png')

    def test_always_manual_problem(self):
        p = self.add('B1', B_RECORDS)
        self.assertIn(61281, cmd.ALWAYS_MANUAL)
        with mock.patch.object(cmd, 'ALWAYS_MANUAL', {p.pk}):
            self.assert_untouched(p, 'всегда вручную')

    def test_labels_out_of_order(self):
        records = [dict(r) for r in A_RECORDS]
        records[2] = dict(records[2], md='г) Выберите издержки.')
        p = self.add('A1', records)
        self.assert_untouched(p, 'метка записи 3 не по порядку')


class RevertTests(_Data):
    def test_revert_restores_byte_for_byte(self):
        a = self.add('A1', A_RECORDS)
        b = self.add('B1', B_RECORDS)
        before = self.state(a, b)
        self.run_cmd('--apply')
        self.assertNotEqual(self.state(a, b), before)
        for snap in self.snapshots():
            call_command('solvehub_parts_restore', '--revert', str(snap), stdout=StringIO())
        self.assertEqual(self.state(a, b), before)
        self.assertEqual(self.parts(b), [])


class DryRunTests(_Data):
    def test_dry_run_writes_nothing(self):
        a = self.add('A1', A_RECORDS)
        b = self.add('B1', B_RECORDS)
        before = self.state(a, b)
        out = self.run_cmd()
        self.assertEqual(self.state(a, b), before)
        self.assertEqual(self.snapshots(), [])
        s = self.summary()
        self.assertEqual(s['groups']['A']['parts_to_create'], 2)
        self.assertEqual(s['groups']['B']['parts_to_create'], 4)
        self.assertEqual(s['groups']['B']['statements_to_change'], 1)
        self.assertIn('сухой прогон', (self.report / next(
            n for n in sorted(p.name for p in self.report.glob('REPORT_*.md')))).read_text(encoding='utf-8'))
        self.assertIn('Группа A: применимо 1', out)


TEST_TYPE = 'тест: короткий ответ'
OPEN_TYPE = 'задача с развёрнутым ответом'


class RetypeTests(_Data):
    """Тестовый тип у задачи с пунктами → «несколько_подвопросов» (решение 13.10.2026)."""

    def typed(self, h, records, problem_type):
        p = self.add(h, records)
        Problem.objects.filter(pk=p.pk).update(problem_type=problem_type)
        return p

    def ptype(self, p):
        return Problem.objects.get(pk=p.pk).problem_type

    def test_test_type_with_parts_becomes_multi_question_in_both_groups(self):
        a = self.typed('A1', A_RECORDS, TEST_TYPE)
        b = self.typed('B1', B_RECORDS, 'единственный_выбор')
        self.run_cmd('--apply')
        self.assertEqual(self.ptype(a), cmd.MULTI_QUESTION_TYPE)
        self.assertEqual(self.ptype(b), cmd.MULTI_QUESTION_TYPE)
        self.assertEqual(len(self.parts(a)), 3)
        self.assertEqual(len(self.parts(b)), 4)

    def test_open_type_is_not_changed(self):
        a = self.typed('A1', A_RECORDS, OPEN_TYPE)
        self.run_cmd('--apply')
        self.assertEqual(self.ptype(a), OPEN_TYPE)
        self.assertEqual(len(self.parts(a)), 3)

    def test_single_record_test_is_not_changed(self):
        self.assertIsNone(cmd.retype_to(TEST_TYPE, 1))
        self.assertEqual(cmd.retype_to(TEST_TYPE, 2), cmd.MULTI_QUESTION_TYPE)
        self.assertIsNone(cmd.retype_to(OPEN_TYPE, 3))
        p = self.typed('S1', A_RECORDS[:1], TEST_TYPE)
        self.run_cmd('--apply')
        self.assertEqual(self.ptype(p), TEST_TYPE)

    def test_revert_restores_old_type(self):
        a = self.typed('A1', A_RECORDS, TEST_TYPE)
        b = self.typed('B1', B_RECORDS, 'верно_неверно')
        before = self.state(a, b)
        self.run_cmd('--apply')
        snaps = {s.name.split('_')[1]: json.loads(s.read_text(encoding='utf-8')) for s in self.snapshots()}
        self.assertEqual(snaps['A']['problems'][0]['old']['problem_type'], TEST_TYPE)
        self.assertEqual(snaps['B']['problems'][0]['old']['problem_type'], 'верно_неверно')
        for snap in self.snapshots():
            call_command('solvehub_parts_restore', '--revert', str(snap), stdout=StringIO())
        self.assertEqual(self.ptype(a), TEST_TYPE)
        self.assertEqual(self.ptype(b), 'верно_неверно')
        self.assertEqual(self.state(a, b), before)

    def test_dry_run_keeps_type(self):
        a = self.typed('A1', A_RECORDS, TEST_TYPE)
        self.run_cmd()
        self.assertEqual(self.ptype(a), TEST_TYPE)
        self.assertEqual(self.summary()['groups']['A']['types_to_change'], 1)

    def test_idempotent(self):
        a = self.typed('A1', A_RECORDS, TEST_TYPE)
        b = self.typed('B1', B_RECORDS, TEST_TYPE)
        self.run_cmd('--apply')
        state = self.state(a, b)
        self.run_cmd()
        for g in ('A', 'B'):
            self.assertEqual(self.summary()['groups'][g]['types_to_change'], 0)
            self.assertEqual(self.summary()['groups'][g]['already_done'], 1)
        snaps = len(self.snapshots())
        self.run_cmd('--apply')
        self.assertEqual(len(self.snapshots()), snaps)
        self.assertEqual(self.state(a, b), state)

    def test_parts_already_restored_only_type_changes(self):
        """Пилот 13.10 записан до перетипизации: пункты есть, тип остался тестом."""
        a = self.typed('A1', A_RECORDS, OPEN_TYPE)
        self.run_cmd('--apply')
        parts_before = [(x.pk, x.statement) for x in self.parts(a)]
        Problem.objects.filter(pk=a.pk).update(problem_type=TEST_TYPE)
        self.run_cmd('--apply')
        self.assertEqual(self.ptype(a), cmd.MULTI_QUESTION_TYPE)
        self.assertEqual([(x.pk, x.statement) for x in self.parts(a)], parts_before)


class LabelTests(TestCase):
    def test_split_label_styles(self):
        cases = {
            'б) Текст': ('б', 'Текст'),
            '$б)$ ( $10$ баллов) Текст': ('б', '( $10$ баллов) Текст'),
            'Задание $2.$ ( $20$ баллов)\n\nТекст': ('2', '( $20$ баллов)\n\nТекст'),
            '**(b) (10 rp)** In the first': ('b', '**(10 rp)** In the first'),
            '**2.(7 баллов)** Лису': ('2', '**(7 баллов)** Лису'),
            '**б)** *(2 балла)* Пусть': ('б', '*(2 балла)* Пусть'),
            '$3.$ Какие плюсы': ('3', 'Какие плюсы'),
        }
        for md, expected in cases.items():
            self.assertEqual(cmd.split_label(md), expected, md)

    def test_no_label(self):
        self.assertEqual(cmd.split_label('Сколько денег')[0], None)

    def test_formula_after_label_keeps_its_dollar(self):
        """Дефект 13.10: `$` формулы после `б) ` съедался как «закрывающий»
        метки (185 записей в 61 задаче полного прогона)."""
        cases = {
            'б) $x_1 = 2$': ('б', '$x_1 = 2$'),
            'б)$x$': ('б', '$x$'),
            '$б)$ текст': ('б', 'текст'),
            '**б)** $x$': ('б', '$x$'),
            '(б) $x$': ('б', '$x$'),
            'Задание $2.$ условие': ('2', 'условие'),
            '1. $a$': ('1', '$a$'),
            'б) $$\\begin{cases} a \\end{cases}$$': ('б', '$$\\begin{cases} a \\end{cases}$$'),
        }
        for md, expected in cases.items():
            self.assertEqual(cmd.split_label(md), expected, md)

    def test_closing_dollar_only_after_opening(self):
        for md in ('б) $x$', 'b) $x$', '2. $x$', '(в) $x$'):
            m = cmd.LABEL_RE.match(md)
            self.assertIsNone(m.group('d2'), md)
        self.assertIsNotNone(cmd.LABEL_RE.match('$б)$ x').group('d2'))


class ConversionGateUnitTests(TestCase):
    def test_lost_dollar_and_dash_are_defects(self):
        raw = r'б) $y_1 = 12 - 2x_1, \quad y_2 = 6 - 2x_2$'
        broken = r'y_1 = 12 — 2x_1,  y_2 = 6 — 2x_2\$'
        found = ' | '.join(cmd.conversion_defects(raw, broken))
        for part in ('чётность', r'\$', r'\quad', 'минус'):
            self.assertIn(part, found)

    def test_formula_followed_by_text(self):
        """`б) $6$ минут` → `6\\$ минут`: `\\$` не в конце, команд нет — ловит чётность."""
        self.assertTrue(cmd.conversion_defects('б) $6$ минут', r'6\$ минут'))

    def test_clean_conversion_and_currency_pass(self):
        self.assertEqual(cmd.conversion_defects(r'б) $a \quad b - c$', r'$a \quad b - c$'), [])
        # Валюта: одинокий `$` сырья законно становится `\$`.
        self.assertEqual(cmd.conversion_defects('subsidy s = $5,000.', r'subsidy s = \$5,000.'), [])
        self.assertEqual(cmd.conversion_defects('до $ $2457$ ;', r'до \$ $2457$ ;'), [])


#: Настоящий PNG 1×1.
PNG_1x1_B64 = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')


class ConversionPipelineTests(_Data):
    """Сквозь всю команду: сырьё → база."""

    def test_formula_part_survives_unchanged(self):
        records = [dict(r) for r in A_RECORDS]
        records[1] = dict(records[1], md='б) $a \\quad b - c$')
        p = self.add('A1', records)
        self.run_cmd('--apply')
        part = self.parts(p)[1]
        self.assertEqual(part.label, 'б')
        self.assertEqual(part.statement, '$a \\quad b - c$')
        self.assertNotIn('\\$', part.statement)
        self.assertNotIn('—', part.statement)

    def test_broken_conversion_goes_to_manual_not_to_base(self):
        records = [dict(r) for r in A_RECORDS]
        records[1] = dict(records[1], md='б) $a - b$')
        p = self.add('A1', records)
        real = cmd.convert_for_import

        def spoiled(**kw):
            result = real(**kw)
            if 'a - b' in result['statement_md']:
                result['statement_md'] = 'a — b\\$'
            return result

        with mock.patch.object(cmd, 'convert_for_import', spoiled):
            self.assert_untouched(p, 'конвертация исказила пункт б)')

    def test_data_image_becomes_figure(self):
        uri = 'data:image/png;base64,' + PNG_1x1_B64
        records = [dict(r) for r in A_RECORDS]
        records[1] = dict(records[1], answer_md='Выручка 20. ![](%s)' % uri)
        p = self.add('A1', records)
        self.run_cmd('--apply')
        digest = hashlib.sha256(uri.encode()).hexdigest()
        part = self.parts(p)[1]
        self.assertIn('[[FIGURE:%s]]' % digest, part.solution)
        self.assertNotIn('data:image', part.solution)
        fig = ProblemFigure.objects.get(problem=p)
        self.assertEqual(fig.tikz_hash, digest)
        self.assertEqual(bytes(fig.image_data), base64.b64decode(PNG_1x1_B64))
        self.assertEqual(fig.content_type, 'image/png')

    def test_broken_data_image_goes_to_manual(self):
        records = [dict(r) for r in A_RECORDS]
        records[1] = dict(records[1], answer_md='Выручка 20. ![](data:image/png;base64,@@@@)')
        p = self.add('A1', records)
        self.assert_untouched(p, 'некорректный base64')
        self.assertEqual(ProblemFigure.objects.filter(problem=p).count(), 0)
