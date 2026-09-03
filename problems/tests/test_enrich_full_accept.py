# -*- coding: utf-8 -*-
"""enrich_full_accept — приёмка боевого прогона на всём корпусе. Только
читает журналы и базу, в базу не пишет ничего.

Главное, что здесь проверяется: расхождения (недостача в манифесте,
рассинхрон растра/TikZ, битые ссылки на картинку) находятся и попадают в
нужный файл — а не тонут в «всё сошлось».
"""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.enrich import taxonomy
from problems.models import Problem, ProblemFigure


def _row(problem_id, **overrides):
    row = {
        'problem_id': problem_id, 'defect': False,
        'call1_ok': True, 'call1_retried': False,
        'call2_ok': True, 'call2_retried': False,
        'soft_violations': [], 'dropped_queries': [],
        'topic_primary': '3', 'topics_secondary': [],
        'tags': ['3.1'],
        'given': 'линейные функции спроса и предложения, известны эластичности',
        'find': 'равновесную цену и объём',
        'econ_concepts': ['спрос', 'предложение', 'равновесие'],
        'concepts_offlist': [],
        'task_nature': 'расчётная', 'features_1': [],
        'graphical_solution': False, 'graphical_solution_source': 'none',
        'topic_confidence': 'высокая',
        'search_queries': ['рыночное равновесие', 'эластичность спроса',
                           'излишек потребителя', 'потоварный налог',
                           'кривая предложения'],
        'plot': None, 'hints': None,
        'text_quality': 'чистая', 'text_quality_note': '',
        'problem_type': 'тест: короткий ответ',
        'difficulty': 3, 'difficulty_note': '',
        'answer_consistency': 'согласован',
        'title_candidate': 'Рынок кофе',
        'images_sent': 0, 'has_raster': False,
        'has_tikz': False, 'has_tikz_in_statement': False,
        'tikz': {'replaced': 0, 'truncated': 0},
    }
    row.update(overrides)
    return row


class EnrichFullAcceptTests(TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.problems = [Problem.objects.create(statement='Задача %d.' % i)
                        for i in range(6)]
        self.rows = [_row(p.id) for p in self.problems]
        self.manifest_ids = [p.id for p in self.problems]

    def _write(self, name, obj_or_lines, jsonl=False):
        path = self.tmp / name
        with open(path, 'w', encoding='utf-8') as fh:
            if jsonl:
                for row in obj_or_lines:
                    fh.write(json.dumps(row, ensure_ascii=False) + '\n')
            else:
                json.dump(obj_or_lines, fh, ensure_ascii=False)
        return path

    def _raw_log_lines(self, ids, prompt_version, both_calls=True):
        import problems.management.commands.glm_enrich_run as run
        lines = []
        usage = {'input_tokens': 1, 'output_tokens': 1,
                 'cache_write_tokens': 0, 'cache_read_tokens': 0,
                 'reasoning_tokens': 0}
        for pid in ids:
            lines.append({
                'problem_id': pid, 'call': 'call1', 'prompt_version': prompt_version,
                'model': run.GLM_VARIANT['call1_model'],
                'effort': run.GLM_VARIANT['call1_effort'],
                'raw_response': {}, 'usage': usage,
            })
            if both_calls:
                lines.append({
                    'problem_id': pid, 'call': 'call2', 'prompt_version': prompt_version,
                    'model': run.GLM_VARIANT['call2_model'],
                    'effort': run.GLM_VARIANT['call2_effort'],
                    'raw_response': {}, 'usage': usage,
                })
        return lines

    def _run(self, rows=None, manifest_ids=None, extra_metrics=None,
             report_dir=None, raw_log_extra_ids=(), missing_call2_ids=()):
        rows = self.rows if rows is None else rows
        manifest_ids = self.manifest_ids if manifest_ids is None else manifest_ids
        report_dir = report_dir or (self.tmp / 'out')

        import problems.management.commands.glm_enrich_run as run
        import problems.management.commands.pilot_enrich_v2 as pilot
        prompt_version = pilot.prompt_fingerprint(run.GLM_VARIANT['concepts'])

        manifest_path = self._write('manifest.json',
                                    {'seed': 1, 'limit': len(manifest_ids), 'ids': manifest_ids})
        # ⚠️ Журнал строится по `rows` (то, что реально разобрано), НЕ по
        # манифесту — иначе задача, лишь ЗАЯВЛЕННАЯ в манифесте, но без
        # единой строки в журнале, получила бы вызовы «бесплатно» и Фаза 1
        # не смогла бы обнаружить именно эту недостачу.
        row_ids = [r['problem_id'] for r in rows]
        full_call_ids = [pid for pid in row_ids if pid not in missing_call2_ids]
        raw_lines = self._raw_log_lines(full_call_ids, prompt_version)
        raw_lines += self._raw_log_lines(missing_call2_ids, prompt_version, both_calls=False)
        raw_lines += self._raw_log_lines(raw_log_extra_ids, prompt_version)
        raw_log_path = self._write('raw.jsonl', raw_lines, jsonl=True)

        parsed_path = self._write('parsed.jsonl', rows, jsonl=True)

        metrics = {
            'total_processed': len(rows),
            'retried_rows': sum(1 for r in rows if r['call1_retried'] or r['call2_retried']),
            'sweep_detector': {'checked': len(rows), 'changed': 0, 'changed_ids': []},
            'usage_totals': {'input_tokens': 100, 'cache_read_tokens': 900,
                             'cache_write_tokens': 0, 'output_tokens': 50,
                             'reasoning_tokens': 0, 'cost_usd': '1.23'},
        }
        if extra_metrics:
            metrics.update(extra_metrics)
        metrics_path = self._write('metrics.json', metrics)

        out_path = self.tmp / 'accept.json'
        call_command('enrich_full_accept', manifest=str(manifest_path),
                    raw_log=str(raw_log_path), parsed=str(parsed_path),
                    metrics=str(metrics_path), out=str(out_path),
                    report_dir=str(report_dir))
        return json.loads(out_path.read_text(encoding='utf-8')), report_dir

    # --- Фаза 1 -----------------------------------------------------------

    def test_полный_журнал_без_недостачи(self):
        result, _ = self._run()
        p1 = result['phase1']
        self.assertEqual(p1['manifest_total'], 6)
        self.assertEqual(p1['both_calls_in_manifest'], 6)
        self.assertEqual(p1['call1_only_ids'], [])
        self.assertEqual(p1['missing_entirely_ids'], [])

    def test_находит_задачу_без_вызова_2(self):
        missing = self.problems[0].id
        result, _ = self._run(missing_call2_ids=[missing])
        p1 = result['phase1']
        self.assertEqual(p1['call1_only_ids'], [missing])
        self.assertEqual(p1['both_calls_in_manifest'], 5)

    def test_находит_задачу_вне_манифеста_в_журнале(self):
        extra = Problem.objects.create(statement='Лишняя задача.')
        result, _ = self._run(raw_log_extra_ids=[extra.id])
        self.assertIn(extra.id, result['phase1']['done_outside_manifest_ids'])

    def test_недостача_из_манифеста_целиком(self):
        stray = Problem.objects.create(statement='Пропавшая задача.')
        manifest_ids = self.manifest_ids + [stray.id]
        result, _ = self._run(manifest_ids=manifest_ids)
        self.assertEqual(result['phase1']['missing_entirely_ids'], [stray.id])

    # --- Фаза 2 -----------------------------------------------------------

    def test_шестнадцать_инвариантов_печатаются(self):
        result, _ = self._run()
        self.assertEqual(result['phase2']['invariants_total'], 16)
        for inv in result['phase2']['invariants']:
            self.assertTrue(inv['threshold'])
            self.assertTrue(inv['fact'])

    def test_цифра_в_given_ловится_инвариантом(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['given'] = 'цена 100 рублей'
        result, _ = self._run(rows=rows)
        digits = [i for i in result['phase2']['invariants'] if 'Цифры' in i['name']][0]
        self.assertFalse(digits['passed'])

    def test_неиспользованные_теги_перечислены_поимённо(self):
        # Все строки используют только тег «3.1» — 343 остальных не тронуты.
        result, _ = self._run()
        tags = result['phase2']['tags']
        self.assertEqual(tags['used_count'], 1)
        self.assertEqual(len(tags['unused_names']), 343)
        self.assertNotIn(taxonomy.tag_name_from_id('3.1'), tags['unused_names'])

    def test_расхождение_растра_с_отправкой_видно_поимённо(self):
        rows = [dict(r) for r in self.rows]
        # У задачи 0 растр в базе есть, а отправлен — 0 (расхождение).
        rows[0]['has_raster'] = True
        rows[0]['images_sent'] = 0
        result, _ = self._run(rows=rows)
        self.assertIn(self.problems[0].id, result['phase2']['images']['mismatch_ids'])

    def test_заголовок_с_цифрой_считается_запрещённым(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['title_candidate'] = 'Задача 2'
        result, _ = self._run(rows=rows)
        self.assertEqual(result['phase2']['titles']['with_forbidden_chars'], 1)

    def test_самый_частый_заголовок_считается_верно(self):
        rows = [dict(r, title_candidate='Рынок кофе') for r in self.rows]
        result, _ = self._run(rows=rows)
        self.assertEqual(result['phase2']['titles']['max_repeat'], len(rows))

    def test_single_freetext_маппится_на_короткий_ответ(self):
        """Правка владельца 2026-09-04 (§5.5): `открытый_ответ` разведён
        обратно на два значения. `single_freetext` перешёл из
        `CHECK_TYPE_AMBIGUOUS` в `CHECK_TYPE_MAP` — SolveHub сам определяет
        его как короткий ответ без обоснования, соответствие 1:1."""
        from problems.management.commands.enrich_full_accept import Command
        self.assertEqual(Command.CHECK_TYPE_MAP['single_freetext'],
                         'тест: короткий ответ')
        self.assertNotIn('single_freetext', Command.CHECK_TYPE_AMBIGUOUS)
        self.assertIn('uncheckable', Command.CHECK_TYPE_AMBIGUOUS)

    def test_check_type_без_solvehub_source_reference_даёт_ноль(self):
        """Ни одна тестовая задача не привязана к источнику SolveHub —
        сверка обязана тихо вернуть 0/0 (не найдено что сверять), а не
        упасть, независимо от того, есть ли сырые JSON SolveHub на диске в
        этом окружении (в норме они лежат вне репозитория)."""
        result, _ = self._run()
        pt = result['phase2']['problem_type']
        self.assertEqual(pt['check_type_compared'], 0)
        self.assertEqual(pt['check_type_match_pct'], 0.0)

    # --- Фаза 4 -------------------------------------------------------

    def test_очередь_битого_текста_по_text_quality(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['text_quality'] = 'серьёзные_дефекты'
        result, report_dir = self._run(rows=rows)
        self.assertEqual(result['phase4_counts']['broken_text'], 1)
        queue = [json.loads(line) for line in
                (report_dir / 'queue_broken_text.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([q['problem_id'] for q in queue], [self.problems[0].id])

    def test_очередь_не_задача(self):
        rows = [dict(r) for r in self.rows]
        rows[1]['problem_type'] = 'не_задача'
        result, _ = self._run(rows=rows)
        self.assertEqual(result['phase4_counts']['not_a_problem'], 1)

    def test_очередь_несходящегося_ответа(self):
        rows = [dict(r) for r in self.rows]
        rows[2]['answer_consistency'] = 'ответ_не_совпадает_с_решением'
        result, _ = self._run(rows=rows)
        self.assertEqual(result['phase4_counts']['answer_mismatch'], 1)

    def test_битая_ссылка_на_картинку_без_problemfigure_попадает_в_очередь(self):
        broken = self.problems[3]
        broken.statement = 'В задаче на графике apl_0.PNG показан сдвиг спроса.'
        broken.save()
        result, report_dir = self._run()
        self.assertGreaterEqual(result['phase4_counts']['lost_visuals'], 1)
        queue = [json.loads(line) for line in
                (report_dir / 'queue_lost_visuals.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertIn(broken.id, [q['problem_id'] for q in queue])

    def test_задача_с_problemfigure_не_считается_битой_ссылкой(self):
        ok_problem = self.problems[4]
        ok_problem.statement = 'См. картинку apl_0.PNG на графике.'
        ok_problem.save()
        ProblemFigure.objects.create(
            problem=ok_problem, tikz_hash='h1', tikz_source='',
            source_field='statement', content_type='image/png',
            image_data=b'\x89PNG\r\n\x1a\n' + b'0' * 10)
        result, _ = self._run()
        self.assertEqual(result['phase4_counts']['lost_visuals'], 0)

    def test_модель_отметила_утрату_визуала_попадает_в_очередь(self):
        rows = [dict(r) for r in self.rows]
        rows[5]['text_quality'] = 'серьёзные_дефекты'
        rows[5]['text_quality_note'] = 'содержание в утраченном визуальном элементе: на графике...'
        result, report_dir = self._run(rows=rows)
        self.assertGreaterEqual(result['phase4_counts']['lost_visuals'], 1)
        queue = [json.loads(line) for line in
                (report_dir / 'queue_lost_visuals.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertIn(self.problems[5].id, [q['problem_id'] for q in queue])

    def test_отчёт_offlist_считает_уникальные_термины(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['concepts_offlist'] = ['внешний эффект', 'общественное благо']
        rows[1]['concepts_offlist'] = ['внешний эффект']
        result, report_dir = self._run(rows=rows)
        self.assertEqual(result['phase4_counts']['offlist_unique_terms'], 2)
        text = (report_dir / 'report_offlist_terms.md').read_text(encoding='utf-8')
        self.assertIn('внешний эффект', text)
        self.assertIn('| 1 | внешний эффект | 2 |', text)
