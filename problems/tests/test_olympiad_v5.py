"""Эталон ВП + МОШ v5 (сессия 14.10.2026): правки, слои заплаток, защиты
перечитывания, служебные блоки, ключи v4 → v5, max_score, автопроверки.

Страницы, слой PDF и заплатки — выдуманные, во временной папке; модель и база
не нужны. Проверки на настоящих эталонах (нет дубликатов ключа v5, таблица
v4 → v5 покрывает v4) — только если папка данных есть на диске.
"""
import csv
import json
import os
import tempfile

from django.test import SimpleTestCase

from problems.olympiad_audit import assemble, fixes, max_score, sweeps, transcribe, triage
from problems.olympiad_audit import version_keys as vk

DATA = os.environ.get('OLYMPIAD_DATA', 'C:/Users/shipu/weconomics-data/olympiads')
SETS = {'vp': 'audit_vp_20261008', 'mosh': 'audit_mosh_20261009'}
PDF = 'raw/pdf/a.pdf'


def task(**kw):
    row = dict(event_id='e', number='1', task_variant='', title='', statement_md='', parts=[],
               solution_md='', answer='', criteria_md='', figures=[], solution_figures=[],
               source_pages=[f'{PDF}#p1'], solution_pages=[], criteria_pages=[], max_score=None)
    row.update(kw)
    return row


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False)


class TmpDigitized(SimpleTestCase):
    """Папка digitized: манифест страниц `a.pdf` p1–p3 → pages/aaaa/pN."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        with open(os.path.join(self.root, 'pages_manifest.jsonl'), 'w', encoding='utf-8') as fh:
            for n in (1, 2, 3):
                fh.write(json.dumps({'file': PDF, 'page': n, 'page_dir': 'pages/aaaa'}) + '\n')

    def page(self, n, blocks, folder='pages', **extra):
        write_json(os.path.join(self.root, folder, 'aaaa', f'p{n}.json'),
                   {'page_dir': 'pages/aaaa', 'page': n, 'blocks': blocks, **extra})

    def layer(self, n, text):
        path = os.path.join(self.root, 'pages', 'aaaa', f'p{n}.txt')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)

    def ctx(self, rows, layers=('pages_v5', 'pages_v3')):
        return sweeps.Ctx('t', rows, self.root, layers)


# ── 1. Правка не применяется, если строка найдена 0 раз или больше ожидаемого ──

class FixesTests(TmpDigitized):
    def run_fix(self, rows, *fix):
        by_ref, by_hash = fixes.page_map(self.root)
        data = {'vp': fixes.Dataset(rows, by_ref, by_hash)}
        _orig, log = fixes.run([('vp', 'aaaa/p1', *fix)], data)
        return data['vp'].rows, log[0]['status']

    def test_1a_not_found_leaves_text(self):
        rows, status = self.run_fix([task(statement_md='2 бала')], 'lit', 'баллл', 'балл', 1, '')
        self.assertEqual(status, 'not_found')
        self.assertEqual(rows[0]['statement_md'], '2 бала')

    def test_1b_more_than_max_leaves_text(self):
        text = 'бала, бала и ещё бала'
        rows, status = self.run_fix([task(statement_md=text, solution_md='бала')],
                                    'lit', 'бала', 'балла', 1, '', 2)
        self.assertEqual(status, 'too_many(4)')
        self.assertEqual((rows[0]['statement_md'], rows[0]['solution_md']), (text, 'бала'))
        # не больше max — применяется; без max — поведение v4 (сколько найдено)
        rows, status = self.run_fix([task(statement_md='2 бала')], 'lit', 'бала', 'балла', 1, '', 1)
        self.assertEqual((status, rows[0]['statement_md']), ('applied', '2 балла'))
        rows, status = self.run_fix([task(statement_md=text)], 'lit', 'бала', 'балла', 1, '')
        self.assertEqual((status, rows[0]['statement_md']), ('applied', 'балла, балла и ещё балла'))

    def test_1c_regex_more_than_max(self):
        rows, status = self.run_fix([task(statement_md='Р = 5, Р = 6')], 're', r'Р(?= =)', 'P', 1, '', 1)
        self.assertEqual(status, 'too_many(2)')
        self.assertEqual(rows[0]['statement_md'], 'Р = 5, Р = 6')

    def test_1d_load_fixes_max(self):
        path = os.path.join(self.root, 'fixes.json')
        write_json(path, {'fixes': [
            {'set': 'vp', 'page': 'aaaa/p1', 'op': 'lit', 'find': 'а', 'rep': 'б', 'max': 1},
            {'set': 'vp', 'page': 'aaaa/p1', 'op': 'lit', 'find': 'в', 'rep': 'г', 'min': 2}]})
        loaded = fixes.load_fixes(path)
        self.assertEqual([(f[5], f[7]) for f in loaded], [(1, 1), (2, None)])

    def test_1e_ported_v4_idempotent(self):
        rows, status = self.run_fix([task(statement_md='2 бала')], 'lit', 'бала', 'балла', 1, '')
        self.assertEqual((status, rows[0]['statement_md']), ('applied', '2 балла'))
        rows, status = self.run_fix(rows, 'lit', 'бала', 'балла', 1, '')
        self.assertEqual(status, 'already_fixed')


# ── 2–3. Слои заплаток и защита перечитывания ────────────────────────────────

class LayerTests(TmpDigitized):
    def setUp(self):
        super().setUp()
        self.page(1, [{'type': 'task', 'number': '1', 'text': 'v2'},
                      {'type': 'task', 'number': '2', 'text': 'v2, задание 2', 'points': 5}])

    def patch(self, folder, blocks, status='fixed', **extra):
        self.page(1, blocks, folder=folder, status=status, **extra)

    def apply(self, names=('pages_v3', 'pages_v5')):
        base = triage.read_json(os.path.join(self.root, 'pages', 'aaaa', 'p1.json'))
        return triage.layer_stack(self.root, names).apply('pages/aaaa', 1, base)

    def texts(self, out):
        return [b['text'] for b in out['blocks']]

    def test_2a_layers_in_order_v5_over_v3(self):
        self.patch('pages_v3', [{'type': 'task', 'number': '1', 'text': 'v3'},
                                {'type': 'task', 'number': '2', 'text': 'v3, задание 2', 'points': 5}])
        self.assertEqual(self.texts(self.apply()), ['v3', 'v3, задание 2'])
        self.patch('pages_v5', [{'type': 'task', 'number': '1', 'text': 'v5'},
                                {'type': 'task', 'number': '2', 'text': 'v5, задание 2'}])
        out = self.apply()
        self.assertEqual(self.texts(out), ['v5', 'v5, задание 2'])
        self.assertTrue(all(b.get('_v5') for b in out['blocks']))
        # баллы, потерянные перечитыванием, — из прежней расшифровки (слой v3)
        self.assertEqual(out['blocks'][1].get('points'), 5)
        # порядок важен: поздний слой перекрывает ранний
        self.assertEqual(self.texts(self.apply(('pages_v5', 'pages_v3'))), ['v3', 'v3, задание 2'])

    def test_2b_sweeps_read_v5_first(self):
        self.patch('pages_v3', [{'type': 'task', 'number': '1', 'text': 'v3'}])
        self.patch('pages_v5', [{'type': 'task', 'number': '1', 'text': 'v5'}])
        ctx = self.ctx([task()])
        self.assertEqual(ctx.pjson('aaaa/p1')['blocks'][0]['text'], 'v5')
        ctx = self.ctx([task()], layers=('pages_v3',))
        self.assertEqual(ctx.pjson('aaaa/p1')['blocks'][0]['text'], 'v3')

    def test_3a_reread_lost_numbers_rejected(self):
        self.patch('pages_v3', [{'type': 'task', 'number': '1', 'text': 'v3'},
                                {'type': 'task', 'number': '2', 'text': 'v3, задание 2'}])
        self.patch('pages_v5', [{'type': 'task', 'number': '1', 'text': 'v5 — одним блоком'}])
        out = self.apply()
        self.assertEqual(out['status'], triage.SKELETON_LOST)
        self.assertTrue(out['needs_eyes'])
        self.assertEqual(self.texts(out), ['v3', 'v3, задание 2'])
        # человек проверил по картинке: номер 2 был выдуман моделью
        self.patch('pages_v5', [{'type': 'task', 'number': '1', 'text': 'v5 — одним блоком'}],
                   numbers_loss_ok='проверено по картинке')
        self.assertEqual(self.texts(self.apply()), ['v5 — одним блоком'])

    def test_3b_human_reread_needs_same_skeleton(self):
        self.patch('pages_v5', [{'type': 'task', 'number': '1', 'text': 'v5'}], status='human')
        self.assertEqual(self.texts(self.apply()), ['v2', 'v2, задание 2'])

    def test_3c_solution_turned_into_task_rejected(self):
        self.page(1, [{'type': 'solution', 'number': '1', 'text': 'Решение 1.'}])
        self.patch('pages_v5', [{'type': 'task', 'number': '1', 'text': 'Условие 1'}])
        out = self.apply()
        self.assertEqual(out['status'], triage.SKELETON_LOST)
        self.assertEqual(out['blocks'][0]['type'], 'solution')

    def test_3d_solutions_shrunk_rejected(self):
        """Решений и критериев на странице осталось меньше 80 % — не берётся."""
        self.page(1, [{'type': 'solution', 'number': '1', 'text': 'Решение 1. ' * 30},
                      {'type': 'criteria', 'text': 'Типичные ошибки. ' * 20}])
        self.patch('pages_v5', [{'type': 'solution', 'number': '1', 'text': 'Решение 1. ' * 30},
                                {'type': 'noise', 'text': 'Типичные ошибки. ' * 20}])
        self.assertEqual(self.apply()['status'], triage.SKELETON_LOST)
        self.patch('pages_v5', [{'type': 'solution', 'number': '1', 'text': 'Решение 1. ' * 30},
                                {'type': 'criteria', 'text': 'Типичные ошибки. ' * 18}])
        self.assertEqual(self.apply()['status'], 'fixed')


# ── 4. Служебный блок не становится заданием; задание с тем же номером цело ──

class ServiceBlockTests(TmpDigitized):
    def write_page(self, page_dir, n, blocks):
        transcribe.Transcriber._write(
            os.path.join(self.root, page_dir, f'p{n}.json'),
            {'status': 'ok', 'blocks': blocks, 'layer_ratio': 0.97, 'numbers_ok': True,
             'retries': 0, 'needs_eyes': False})

    def build(self, event_id, blocks):
        self.write_page('pages/t', 1, blocks)
        event = {'event_id': event_id, 'year': 2024, 'stage': event_id.split('-')[2],
                 'grade': '9', 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t',
                                               'pages': 1}], 'solution_files': []}
        tasks, report, _ = assemble.build_event(self.root, event, 'figs', crop=False,
                                                profile=assemble.ECON)
        return tasks, event

    @staticmethod
    def question(n, v, text):
        return {'type': 'task', 'number': str(n), 'task_variant': str(v),
                'text': f'{text}\n\n1) да\n2) нет'}

    def test_4a_qualifying_block_service_and_same_number(self):
        """«Блок 2» с номером 1 — инструкция, не задание; вопрос 1 блока 2 —
        задание 3 (сквозная нумерация), и вопрос 1 блока 1 не потерян."""
        blocks = [{'type': 'task', 'title': 'Блок 1', 'text': 'Выберите один правильный ответ.'}]
        blocks += [self.question(n, v, f'Б1 вопрос {n}/{v}?') for n in (1, 2) for v in (1, 2, 3)]
        blocks += [{'type': 'task', 'number': '1', 'title': 'Блок 2',
                    'text': 'Выберите все верные ответы.'},
                   # служебный без указания формата — ловит только разметка блоков
                   {'type': 'task', 'number': '2', 'text': 'Внимание! На блок отводится 15 минут.'}]
        blocks += [self.question(1, v, f'Б2 вопрос 1/{v}?') for v in (1, 2, 3)]
        tasks, event = self.build('mosh-2024-qualifying-9-v1', blocks)
        keys = [(t.number, t.task_variant) for t in tasks]
        self.assertEqual(keys, [(str(n), str(v)) for n in (1, 2, 3) for v in (1, 2, 3)])
        by_key = {(t.number, t.task_variant): t for t in tasks}
        self.assertEqual(by_key[('1', '1')].statement, ['Б1 вопрос 1/1?\n\n1) да\n2) нет'])
        self.assertEqual(by_key[('3', '2')].statement, ['Б2 вопрос 1/2?\n\n1) да\n2) нет'])
        record = assemble.task_record(by_key[('3', '1')], event, 'm')
        self.assertTrue(record['statement_md'].startswith('Выберите все верные ответы.'))
        self.assertEqual(record['section_md'], 'Выберите все верные ответы.')
        everything = ' '.join(' '.join(t.statement) + ' '.join(t.leads) for t in tasks)
        self.assertNotIn('Блок 2', everything)
        self.assertNotIn('Внимание', everything)

    def test_4b_numbered_section_instruction(self):
        """«Раздел III … выбрать ВСЕ верные ответы» с номером 3 не сливается с
        вопросом 3: инструкция — в начало его условия, текст вопроса цел."""
        question = 'Какие из благ являются общественными?\n\nа) маяк\nб) хлеб'
        lead = ('Раздел III (5 вопросов, 20 баллов). Из нескольких вариантов нужно '
                'выбрать ВСЕ верные ответы.')
        tasks, event = self.build('mosh-2009-final-9-v1', [
            {'type': 'task', 'number': '3', 'text': lead},
            {'type': 'task', 'number': '3', 'text': question}])
        self.assertEqual([(t.number, t.statement) for t in tasks], [('3', [question])])
        record = assemble.task_record(tasks[0], event, 'm')
        self.assertEqual(record['statement_md'], f'{lead}\n\n{question}')


# ── 5–6. Ключи v5 и таблица v4 → v5 ──────────────────────────────────────────

class KeyTests(SimpleTestCase):
    def test_5a_duplicates_found(self):
        rows = [task(number='1'), task(number='1', task_variant='2'), task(number='1')]
        self.assertEqual(vk.duplicates(rows), [('e', '1', '')])
        self.assertEqual(vk.duplicates(rows[:2]), [])

    def test_6a_key_table_covers_every_old_task(self):
        q = 'Какой из перечисленных товаров является товаром Гиффена для бедной семьи?'
        old = [
            task(event_id='a', number='1', statement_md='Найдите цену равновесия на рынке.'),
            task(event_id='a', number='2', statement_md='Найдите объём продаж фирмы.'),
            task(event_id='q', number='1', task_variant='1',
                 statement_md='Блок 2. Выберите все верные ответы.'),
            task(event_id='q', number='2', task_variant='1', statement_md=q),
            task(event_id='q', number='3', task_variant='1', statement_md='Совсем другой текст про налоги.'),
            task(event_id='d', number='5', statement_md='Пункт 5) задачи 4.'),
        ]
        new = [
            task(event_id='a', number='1', statement_md='Найдите цену равновесия на рынке.'),
            task(event_id='a', number='2', statement_md='Найдите объём продаж фирмы.'),
            task(event_id='q', number='7', task_variant='1', statement_md=q),
            task(event_id='q', number='8', task_variant='1', statement_md='Про выпуск облигаций.'),
            task(event_id='d', number='4', statement_md='Задача 4 с пунктами.'),
        ]
        rows, changed = vk.key_table(old, new, 'mosh', {'d': 'дефект 3: пункт 5) задачи 4'},
                                     {'d': ('d', '4', '')})
        self.assertEqual(len(rows), len(old))
        self.assertEqual([tuple(r[1:4]) for r in rows], [vk.key(r) for r in sorted(
            old, key=lambda r: r['event_id'])])
        verdicts = {(r[1], r[2]): (r[7], tuple(r[4:7])) for r in rows}
        self.assertEqual(verdicts[('a', '1')][0], vk.SAME)
        self.assertEqual(verdicts[('q', '1')][0], vk.SERVICE)
        self.assertEqual(verdicts[('q', '2')], (vk.RENUMBERED, ('q', '7', '1')))
        self.assertEqual(verdicts[('q', '3')][0], vk.MISSING)
        self.assertEqual(verdicts[('d', '5')], ('удалено: пункт 5) задачи 4', ('d', '4', '')))
        self.assertEqual(set(changed), {'q', 'd'})


def _data(name, sub):
    return os.path.join(DATA, SETS[name], 'digitized', sub)


class DataInvariantTests(SimpleTestCase):
    """Настоящие эталоны v4/v5 (если папка данных на диске)."""

    def test_5b_no_duplicate_keys_in_v5(self):
        for name in SETS:
            path = _data(name, 'v5/reference_problems_v5.jsonl')
            if not os.path.isfile(path):
                self.skipTest('нет данных v5')
            self.assertEqual(vk.duplicates(fixes.read_rows(path)), [], name)

    def test_6b_key_csv_covers_v4(self):
        for name in SETS:
            v4, table = _data(name, 'v4/reference_problems_v4.jsonl'), _data(name, 'v5/v4_to_v5_keys.csv')
            if not (os.path.isfile(v4) and os.path.isfile(table)):
                self.skipTest('нет данных v4/v5')
            with open(table, encoding='utf-8-sig', newline='') as fh:
                rows = list(csv.reader(fh, delimiter=';'))[1:]
            keys = [tuple(r[1:4]) for r in rows]
            self.assertEqual(sorted(keys), sorted(vk.key(r) for r in fixes.read_rows(v4)), name)


# ── 7. max_score не заполняется при расхождении источников ───────────────────

class MaxScoreTests(SimpleTestCase):
    def test_7a_conflict_not_filled(self):
        row = task(statement_md='Задача 1. «Рынок» (20 баллов)\n\nА) (5 баллов) Найдите цену.\n'
                                'Б) (10 баллов) Найдите объём.')
        res = max_score.infer(row)
        self.assertEqual(res['status'], 'conflict')
        self.assertEqual(res['sources'], {'шапка': 20, 'пункты условия': 15})
        log = max_score.fill([row])
        self.assertIsNone(row['max_score'])
        self.assertEqual(log[0][1], 'conflict')

    def test_7b_agreeing_sources_filled(self):
        row = task(statement_md='Задача 1. «Рынок» (15 баллов)\n\nА) (5 баллов) Найдите цену.\n'
                                'Б) (10 баллов) Найдите объём.',
                   criteria_md='Итого за задачу: 15 баллов')
        max_score.fill([row])
        self.assertEqual(row['max_score'], 15)
        self.assertEqual(row['max_score_source'], 'шапка, пункты условия, итог критериев')

    def test_7c_existing_value_not_changed(self):
        row = task(statement_md='Задача 1 (25 баллов)', max_score=6)
        max_score.fill([row])
        self.assertEqual(row['max_score'], 6)
        self.assertEqual(max_score.infer(row)['status'], 'differs')
        criteria = task(criteria_md='(1) 1 балл за верную формулу\n(2) 2 балла за ответ\nИтого: 3 балла')
        self.assertEqual(max_score.infer(criteria)['status'], 'none')


# ── 8. Каждая из 9 автопроверок краснеет на подложенном дефекте ──────────────

class SweepTests(TmpDigitized):
    def classes(self, func, rows, **kw):
        return [x['cls'] for x in func(self.ctx(rows), **kw)]

    def test_8_1_mixed_alphabets(self):
        self.assertGreaterEqual(len(self.classes(
            sweeps.sweep1_mixed, [task(statement_md='Фирма арбитрajsa; Qd=14-Р; товар Х и товар У.')])), 3)
        self.assertEqual(self.classes(sweeps.sweep1_mixed, [task(
            statement_md='Раздел Х. Фирма продаёт товар $X$ и товар Y. У меня есть идея.')]), [])

    def test_8_2_duplicate_answer(self):
        self.assertEqual(len(self.classes(sweeps.sweep2_dupans, [
            task(solution_md='Ответ: 5\nводу\nОтвет: 5'), task(answer='Ответ: **Ответ:** 7')])), 2)
        self.assertEqual(self.classes(sweeps.sweep2_dupans, [task(solution_md='Ответ: 5\nОтвет: 6')]), [])

    def test_8_3_answer_without_source(self):
        self.layer(1, 'Задача 1. Найдите цену. Ответ: 42 рубля.')
        self.assertEqual(self.classes(sweeps.sweep3_answer_src, [task(solution_md='Ответ: 47')]),
                         ['3_ответ_без_источника'])
        self.assertEqual(self.classes(sweeps.sweep3_answer_src, [task(solution_md='Ответ: 42')]), [])

    def test_8_4_footnotes(self):
        self.assertEqual(len(self.classes(sweeps.sweep4_footnotes, [task(statement_md='слово¹ и ещё')])), 1)
        self.assertEqual(len(self.classes(sweeps.sweep4_footnotes, [task(statement_md='Кард^1 сказал')])), 1)
        self.assertEqual(self.classes(sweeps.sweep4_footnotes,
                                      [task(statement_md='слово¹ и ещё\n\n¹ Сноска.')]), [])
        self.layer(1, 'Условие задачи про рынок.\n1 Данные Росстата за последний доступный год.')
        self.assertEqual(self.classes(sweeps.sweep4_footnotes, [task(statement_md='Условие задачи про рынок.')]),
                         ['4_сноска_нет_в_тексте'])
        self.assertEqual(self.classes(sweeps.sweep4_footnotes, [task(
            statement_md='Условие задачи про рынок.\n\n¹ Данные Росстата за последний доступный год.')]), [])

    def test_8_5_artifacts(self):
        found = self.classes(sweeps.sweep5_artifacts, [task(statement_md='вер\u00adно [нечитаемо]')])
        self.assertEqual(found.count('5_артефакты'), 2)
        self.assertEqual(self.classes(sweeps.sweep5_artifacts, [task(statement_md='верно и чисто')]), [])

    def test_8_6_dictionary(self):
        self.assertEqual(self.classes(sweeps.sweep6_spell, [task(statement_md='Найдите оснвое равновесие.')]),
                         ['6_орфография'])
        self.assertEqual(self.classes(sweeps.sweep6_spell, [task(statement_md='Найдите равновесие рынка.')]),
                         [])

    def test_8_7_figure_and_table(self):
        self.page(1, [{'type': 'task', 'number': '1', 'text': '|a|b|\n|---|---|\n|1|2|'},
                      {'type': 'figure', 'bbox': [0, 0, 500, 500]}], flags={'has_figure': True})
        self.assertEqual(sorted(self.classes(sweeps.sweep7_figs_tables, [task(statement_md='Текст.')])),
                         ['7_рисунок_не_привязан', '7_таблица_не_передана'])
        self.assertEqual(self.classes(sweeps.sweep7_figs_tables, [task(
            statement_md='| a | b |\n|---|---|\n| 1 | 2 |', figures=[{'page': 1, 'file': 'f.png'}])]), [])

    def test_8_8_service_block(self):
        self.assertEqual(len(self.classes(sweeps.sweep8_service_tasks, [task(
            statement_md='В **задании 7** отнесите события и их последствия. За каждый верный ответ – 3 балла.')])), 1)
        self.assertEqual(self.classes(sweeps.sweep8_service_tasks,
                                      [task(statement_md='Найдите цену. Сколько будет?', answer='5')]), [])

    def test_8_9_lost_layer_lines(self):
        line = 'Постоянные издержки фирмы составляют сорок рублей ежемесячно независимо от выпуска'
        self.layer(1, f'Задача 1. Найдите цену равновесия.\n{line}')
        self.assertEqual(self.classes(sweeps.sweep9_layer_loss, [task(
            statement_md='Задача 1. Найдите цену равновесия.')]), ['9_потеря_текста_слоя'])
        self.assertEqual(self.classes(sweeps.sweep9_layer_loss, [task(
            statement_md=f'Задача 1. Найдите цену равновесия.\n{line}')]), [])

    def test_8_all_classes_registered(self):
        self.assertEqual([n for n, _f in sweeps.ALL], [str(n) for n in range(1, 10)])
