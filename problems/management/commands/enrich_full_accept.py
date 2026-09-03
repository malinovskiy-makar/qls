# -*- coding: utf-8 -*-
"""enrich_full_accept — приёмка боевого прогона обогащения (Фазы 1-2-4
сессии приёмки, `claude/API_RUN_MASTER_20260830.md` §11).

⚠️ ТОЛЬКО ЧИТАЕТ. Ни строчки в базу, ни одного обращения к API — весь
разбор идёт по уже оплаченным журналам `reports/enrich_pilot/run_raw.jsonl`
и `run_parsed.jsonl` плюс базе (только SELECT).

Пишет:
  reports/enrich_pilot/run_full_accept.json   — фазы 1+2 числами, машиночитаемо
  reports/enrich_pilot/queue_broken_text.jsonl
  reports/enrich_pilot/queue_lost_visuals.jsonl
  reports/enrich_pilot/queue_answer_mismatch.jsonl
  reports/enrich_pilot/queue_not_a_problem.jsonl
  reports/enrich_pilot/report_offlist_terms.md

Запуск:
    manage.py enrich_full_accept
"""
import json
import re
import statistics
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from problems.enrich import taxonomy
from problems.management.commands import glm_enrich_run as run
from problems.management.commands import glm_run_gate as gate
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import AutoTopicAssignment, Problem, ProblemFigure, SourceReference

REPORT_DIR = Path('reports/enrich_pilot')
MANIFEST_PATH = REPORT_DIR / 'run_full_sample_ids.json'
RAW_LOG_PATH = REPORT_DIR / 'run_raw.jsonl'
PARSED_PATH = REPORT_DIR / 'run_parsed.jsonl'
METRICS_PATH = REPORT_DIR / 'run_metrics.json'
OUT_PATH = REPORT_DIR / 'run_full_accept.json'

_TITLE_BAD_RE = re.compile(r'[\$\\]|\d')
_FILENAME_IN_TEXT_RE = re.compile(
    r'\b[\w\-]+\.(?:png|jpe?g|gif|bmp)\b', re.IGNORECASE)
_IMG_TAG_RE = re.compile(r'<img\b', re.IGNORECASE)


def load_json(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def load_parsed(path):
    rows = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class Command(BaseCommand):
    help = ('Приёмка боевого прогона: фазы 1 (полнота журнала), 2 (16 '
            'инвариантов §11 + доп. статистика) и 4 (четыре очереди на '
            'ручной разбор + отчёт по concepts_offlist). Только читает.')

    def add_arguments(self, parser):
        parser.add_argument('--manifest', type=str, default=str(MANIFEST_PATH))
        parser.add_argument('--raw-log', type=str, default=str(RAW_LOG_PATH))
        parser.add_argument('--parsed', type=str, default=str(PARSED_PATH))
        parser.add_argument('--metrics', type=str, default=str(METRICS_PATH))
        parser.add_argument('--out', type=str, default=str(OUT_PATH))
        parser.add_argument('--report-dir', type=str, default=str(REPORT_DIR),
                            help='Куда писать очереди и report_offlist_terms.md.')

    def handle(self, *args, **options):
        self.manifest_path = Path(options['manifest'])
        self.raw_log_path = Path(options['raw_log'])
        self.parsed_path = Path(options['parsed'])
        self.metrics_path = Path(options['metrics'])
        self.out_path = Path(options['out'])
        self.report_dir = Path(options['report_dir'])
        self.report_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write('=== ФАЗА 1: полнота журнала ===')
        phase1 = self.phase1()

        self.stdout.write('')
        self.stdout.write('=== ФАЗА 2: §11 по всему корпусу ===')
        rows = load_parsed(self.parsed_path)
        metrics = load_json(self.metrics_path)
        ok_rows = [r for r in rows if not r['defect']]
        phase2 = self.phase2(rows, ok_rows, metrics)

        self.stdout.write('')
        self.stdout.write('=== ФАЗА 4: очереди на ручной разбор ===')
        phase4 = self.phase4(ok_rows)

        out = {'phase1': phase1, 'phase2': phase2, 'phase4_counts': phase4}
        with open(self.out_path, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
        self.stdout.write('')
        self.stdout.write('запись: %s' % self.out_path)

    # ------------------------------------------------------------------
    # ФАЗА 1
    # ------------------------------------------------------------------

    def phase1(self):
        manifest = load_json(self.manifest_path)
        manifest_ids = manifest['ids']
        manifest_set = set(manifest_ids)
        self.stdout.write('задач в манифесте: %d' % len(manifest_ids))

        prompt_version = pilot.prompt_fingerprint(run.GLM_VARIANT['concepts'])
        have_call1, have_call2 = set(), set()
        for entry in pilot.iter_raw_log(str(self.raw_log_path)):
            if entry.get('prompt_version') != prompt_version:
                continue
            if (entry['call'] == 'call1'
                    and entry['model'] == run.GLM_VARIANT['call1_model']
                    and entry.get('effort') == run.GLM_VARIANT['call1_effort']):
                have_call1.add(entry['problem_id'])
            elif (entry['call'] == 'call2'
                    and entry['model'] == run.GLM_VARIANT['call2_model']
                    and entry.get('effort') == run.GLM_VARIANT['call2_effort']):
                have_call2.add(entry['problem_id'])

        both = have_call1 & have_call2
        call1_only = sorted(have_call1 - have_call2)
        no_call_at_all = sorted(manifest_set - have_call1)
        outside_manifest_but_done = sorted(both - manifest_set)

        self.stdout.write('задач с обоими вызовами в журнале: %d' % len(both & manifest_set))
        self.stdout.write('задач с вызовом 1, но без вызова 2: %d%s'
                          % (len(call1_only),
                             (' — id: %s' % call1_only) if call1_only else ''))
        self.stdout.write('задач из манифеста без единого вызова в журнале: %d%s'
                          % (len(no_call_at_all),
                             (' — id: %s' % no_call_at_all) if no_call_at_all else ''))
        if outside_manifest_but_done:
            self.stdout.write('⚠️ обработаны, но ВНЕ манифеста (%d): %s'
                              % (len(outside_manifest_but_done),
                                 outside_manifest_but_done[:20]))

        metrics = load_json(self.metrics_path)
        usage = metrics['usage_totals']
        cache_share = (usage['cache_read_tokens']
                      / (usage['input_tokens'] + usage['cache_read_tokens'])
                      if (usage['input_tokens'] + usage['cache_read_tokens']) else 0.0)

        manifest_mtime = self.manifest_path.stat().st_mtime
        raw_mtime = self.raw_log_path.stat().st_mtime
        elapsed_hours = (raw_mtime - manifest_mtime) / 3600.0
        n_processed = metrics['total_processed']
        rate_per_min = n_processed / (elapsed_hours * 60) if elapsed_hours else 0.0

        self.stdout.write('расход по журналу (все попытки, включая неудачные): $%s'
                          % usage['cost_usd'])
        self.stdout.write('входных токенов: %d, кэш прочитан: %d, доля кэша: %.1f%%'
                          % (usage['input_tokens'], usage['cache_read_tokens'],
                             cache_share * 100))
        self.stdout.write(
            '⚠️ поштучных меток времени журнал не хранит (append_raw_log не '
            'пишет timestamp) — время оценено по mtime файлов: манифест '
            'заморожен %s, run_raw.jsonl последний раз записан %s => '
            '%.1f ч суммарно (с учётом всех перезапусков после сетевых '
            'обрывов, видных в battle_run.log)'
            % (_fmt_mtime(manifest_mtime), _fmt_mtime(raw_mtime), elapsed_hours))
        self.stdout.write('обработано задач: %d, средняя скорость: %.1f задач/мин'
                          % (n_processed, rate_per_min))

        return {
            'manifest_total': len(manifest_ids),
            'both_calls_in_manifest': len(both & manifest_set),
            'call1_only_ids': call1_only,
            'missing_entirely_ids': no_call_at_all,
            'done_outside_manifest_ids': outside_manifest_but_done,
            'cost_usd': usage['cost_usd'],
            'input_tokens': usage['input_tokens'],
            'cache_read_tokens': usage['cache_read_tokens'],
            'cache_share_pct': cache_share * 100,
            'elapsed_hours_by_mtime': elapsed_hours,
            'avg_rate_per_min': rate_per_min,
        }

    # ------------------------------------------------------------------
    # ФАЗА 2
    # ------------------------------------------------------------------

    def phase2(self, rows, ok_rows, metrics):
        n_ok = len(ok_rows) or 1
        invariants = self._sixteen_invariants(rows, ok_rows, metrics)
        self.stdout.write('%-18s %-52s %-18s %-24s %s' % (
            'раздел', 'инвариант', 'порог', 'факт', 'сошлось'))
        section = None
        for sec, name, threshold, fact, passed in invariants:
            self.stdout.write('%-18s %-52s %-18s %-24s %s' % (
                sec if sec != section else '', name, threshold, fact,
                'да' if passed else 'НЕТ'))
            section = sec
        n_passed = sum(1 for *_r, p in invariants if p)
        self.stdout.write('')
        self.stdout.write('сошлось %d из %d' % (n_passed, len(invariants)))

        self.stdout.write('')
        self.stdout.write('--- теги ---')
        tags_stats = self._tags_stats(ok_rows)
        self.stdout.write('уникальных тегов использовано: %d из 344' % tags_stats['used_count'])
        self.stdout.write('не использовано ни разу (%d): %s'
                          % (len(tags_stats['unused_names']), tags_stats['unused_names']))
        self.stdout.write('ровно с 1 тегом: %.1f%%, ровно с 5: %.1f%%'
                          % (tags_stats['exactly_1_pct'], tags_stats['exactly_5_pct']))

        self.stdout.write('')
        self.stdout.write('--- картинки ---')
        img_stats = self._image_stats(ok_rows)
        self.stdout.write('задач с растром (по базе): %d, реально отправлено с картинкой: %d'
                          % (img_stats['has_raster'], img_stats['image_sent']))
        if img_stats['mismatch_ids']:
            self.stdout.write('⚠️ расхождение (%d): %s'
                              % (len(img_stats['mismatch_ids']), img_stats['mismatch_ids']))
        self.stdout.write('TikZ у условия: %d, подставлено в вызов 1: %d'
                          % (img_stats['tikz_in_statement'], img_stats['tikz_replaced']))
        if img_stats['tikz_mismatch_ids']:
            self.stdout.write('⚠️ расхождение TikZ (%d): %s'
                              % (len(img_stats['tikz_mismatch_ids']),
                                 img_stats['tikz_mismatch_ids']))

        self.stdout.write('')
        self.stdout.write('--- тесты (problem_type) ---')
        pt_stats = self._problem_type_stats(rows, ok_rows)
        self.stdout.write('problem_type заполнен у %.1f%% задач (жёсткий инвариант — 100%%)'
                          % pt_stats['filled_pct'])
        self.stdout.write('тестов без подтипа (problem_type пуст при task_nature != не_задача): %d'
                          % pt_stats['tests_without_subtype'])
        self.stdout.write('совпадение с check_type SolveHub (там, где однозначен): %.1f%% (%d из %d)'
                          % (pt_stats['check_type_match_pct'], pt_stats['check_type_matched'],
                             pt_stats['check_type_compared']))
        self.stdout.write('распределение по problem_type: %s' % pt_stats['distribution'])

        self.stdout.write('')
        self.stdout.write('--- заголовки (title_candidate) ---')
        title_stats = self._title_stats(ok_rows)
        self.stdout.write('непустых: %.1f%%, длиннее 40 симв.: %d, с $/слэшем/цифрой: %d'
                          % (title_stats['nonempty_pct'], title_stats['too_long'],
                             title_stats['with_forbidden_chars']))
        self.stdout.write('самый частый заголовок повторяется %d раз (порог <= 50)'
                          % title_stats['max_repeat'])
        self.stdout.write('топ-10 повторов: %s' % title_stats['top10'])

        self.stdout.write('')
        self.stdout.write('--- защищённые поля ---')
        self.stdout.write('свип-детектор по всему корпусу: проверено %d, расхождений %d%s'
                          % (metrics['sweep_detector']['checked'],
                             metrics['sweep_detector']['changed'],
                             (' — id: %s' % metrics['sweep_detector']['changed_ids'])
                             if metrics['sweep_detector']['changed'] else ''))

        self.stdout.write('')
        self.stdout.write('--- деньги и кэш ---')
        usage = metrics['usage_totals']
        cache_share = (usage['cache_read_tokens']
                      / (usage['input_tokens'] + usage['cache_read_tokens'])
                      if (usage['input_tokens'] + usage['cache_read_tokens']) else 0.0)
        self.stdout.write('расход по факту usage: $%s (смета из API_RUN_MASTER §9.3 для '
                          'Terra+Luna на 41 307 задач — $134; фактически прогон шёл на '
                          'GLM-5.3-Flash по промо-цене, а не на заявленной паре '
                          'OpenAI-провайдера — расхождение реальное, не ошибка счёта)'
                          % usage['cost_usd'])
        self.stdout.write('доля попаданий в кэш префикса (агрегат по всему прогону): %.1f%%'
                          % (cache_share * 100))

        return {
            'invariants': [
                {'section': s, 'name': n, 'threshold': t, 'fact': f, 'passed': p}
                for s, n, t, f, p in invariants
            ],
            'invariants_passed': n_passed,
            'invariants_total': len(invariants),
            'tags': tags_stats,
            'images': img_stats,
            'problem_type': pt_stats,
            'titles': title_stats,
            'sweep_detector': metrics['sweep_detector'],
            'cost_usd': usage['cost_usd'],
            'cache_share_pct': cache_share * 100,
        }

    def _sixteen_invariants(self, rows, ok_rows, metrics):
        """Те же 16, что и `glm_run_gate.build_invariants`, но пересчитаны
        напрямую (без чтения через сам `glm_run_gate`, чтобы не тащить его
        нечанкованные ORM-запросы — на 41 тысяче id `filter(id__in=...)`
        роняет SQLite, см. `problems/management/commands/CLAUDE.md`)."""
        n_ok = len(ok_rows) or 1
        total = len(rows)

        topics = Counter(str(r.get('topic_primary') or '') for r in ok_rows
                         if r.get('topic_primary'))
        top_theme_pct = (max(topics.values()) / n_ok * 100) if topics else 0.0
        other_pct = topics.get(gate.THEME_OTHER_ID, 0) / n_ok * 100

        matched, compared, human_pct = self._human_topic_match(ok_rows)

        unique_tags = {tag for r in ok_rows for tag in (r.get('tags') or [])}
        tag_counts = Counter(len(r.get('tags') or []) for r in ok_rows)
        one_tag_pct = tag_counts.get(1, 0) / n_ok * 100
        five_tag_pct = tag_counts.get(5, 0) / n_ok * 100
        second_topic_pct = sum(
            1 for r in ok_rows if (r.get('topics_secondary') or [])) / n_ok * 100

        given_lens = [len(r['given']) for r in ok_rows if r.get('given')]
        given_median = statistics.median(given_lens) if given_lens else 0
        sim_median = gate.query_similarity_median(ok_rows)
        digits = gate.digits_in_protected_fields(ok_rows)

        concept_counter = Counter(c for r in ok_rows
                                  for c in set(r.get('econ_concepts') or []))
        top3 = [c for c, _ in concept_counter.most_common(3)]
        top3_cover = sum(1 for r in ok_rows
                         if set(r.get('econ_concepts') or []) & set(top3))
        top3_pct = top3_cover / n_ok * 100
        offlist_pct = sum(
            1 for r in ok_rows if (r.get('concepts_offlist') or [])) / n_ok * 100
        single_letter = gate.single_letter_concepts(ok_rows)

        not_task_pct = sum(
            1 for r in ok_rows if r.get('problem_type') == 'не_задача') / n_ok * 100
        problem_type_pct = sum(
            1 for r in ok_rows if r.get('problem_type')) / n_ok * 100

        sweep_changed = metrics['sweep_detector']['changed']
        first_pass_pct = ((total - metrics['retried_rows']) / total * 100) if total else 0.0

        return [
            ('Тема и теги', 'Ни одна тема не покрывает больше',
             '15 % корпуса', '%.1f %%' % top_theme_pct, top_theme_pct <= 15),
            ('Тема и теги', '«Другое»',
             '<= 2 %', '%.1f %%' % other_pct, other_pct <= 2),
            ('Тема и теги', 'Совпадение с темой, проставленной человеком',
             '>= 70 %', '%.1f %% (%d из %d)' % (human_pct, matched, compared),
             human_pct >= 70),
            ('Тема и теги', 'Уникальных тегов (было: >=90 на выборке 300)',
             '>= 90', '%d из 344' % len(unique_tags), len(unique_tags) >= 90),
            ('Тема и теги', 'Доля задач ровно с 1 тегом / ровно с 5',
             '<= 30 % / <= 15 %', '%.1f %% / %.1f %%' % (one_tag_pct, five_tag_pct),
             one_tag_pct <= 30 and five_tag_pct <= 15),
            ('Тема и теги', 'Доля задач с непустой второй темой',
             '25-40 %', '%.1f %%' % second_topic_pct,
             25 <= second_topic_pct <= 40),

            ('Текстовые поля', 'Цифры в given, find, econ_concepts, plot, запросах',
             '0', '%d' % digits, digits == 0),
            ('Текстовые поля', 'Медианная длина given',
             '40-120 символов', '%d' % given_median, 40 <= given_median <= 120),
            ('Текстовые поля', 'Медианная попарная схожесть запросов одной задачи',
             '< 0,85', '%.3f' % sim_median, sim_median < 0.85),

            ('Понятия и словарь', 'Верхние три термина покрывают',
             '< 50 % задач', '%.1f %%' % top3_pct, top3_pct < 50),
            ('Понятия и словарь', 'Доля заполненного concepts_offlist',
             '2-8 %', '%.1f %%' % offlist_pct, 2 <= offlist_pct <= 8),
            ('Понятия и словарь', 'Однобуквенные обозначения в econ_concepts',
             '0', '%d' % single_letter, single_letter == 0),

            ('Диагностика', 'Доля «не задача» (problem_type)',
             '< 5 %', '%.1f %%' % not_task_pct, not_task_pct < 5),
            ('Диагностика', 'problem_type заполнен у всех задач',
             '100 %', '%.1f %%' % problem_type_pct, problem_type_pct >= 100),

            ('Техника и деньги', 'Свип-детектор: расхождения в защищённых полях',
             '0', '%d' % sweep_changed, sweep_changed == 0),
            ('Техника и деньги', 'Доля ответов, прошедших схему с первого раза',
             '>= 95 %', '%.1f %%' % first_pass_pct, first_pass_pct >= 95),
        ]

    def _human_topic_match(self, ok_rows):
        """Как `glm_run_gate.human_topic_match`, но БЕЗ `filter(id__in=...)`
        на десятках тысяч id — читаем таблицы целиком и фильтруем в Python
        (та же ловушка SQLite, что и в `glm_enrich_run._proportional_by_source`).
        """
        wanted = {row['problem_id'] for row in ok_rows}
        auto = set()
        for pid, topic_id in AutoTopicAssignment.objects.values_list(
                'problem_id', 'topic_id').iterator():
            if pid in wanted:
                auto.add((pid, topic_id))

        human = {}
        for pid, topic_id, topic_name in Problem.objects.values_list(
                'id', 'topics__id', 'topics__name').iterator():
            if pid not in wanted or topic_id is None or (pid, topic_id) in auto:
                continue
            allowed = gate.CANON_TO_V2.get(topic_name)
            if allowed:
                human.setdefault(pid, set()).update(allowed)

        matched = compared = 0
        for row in ok_rows:
            allowed = human.get(row['problem_id'])
            if not allowed:
                continue
            compared += 1
            if str(row.get('topic_primary') or '') in allowed:
                matched += 1
        pct = (matched / compared * 100) if compared else 0.0
        return matched, compared, pct

    def _tags_stats(self, ok_rows):
        used_ids = {tag for r in ok_rows for tag in (r.get('tags') or [])}
        all_ids = set(taxonomy.tag_ids())
        unused_ids = sorted(all_ids - used_ids)
        unused_names = [taxonomy.tag_name_from_id(i) for i in unused_ids]
        tag_counts = Counter(len(r.get('tags') or []) for r in ok_rows)
        n = len(ok_rows) or 1
        return {
            'used_count': len(used_ids),
            'total_canonical': len(all_ids),
            'unused_ids': unused_ids,
            'unused_names': unused_names,
            'exactly_1_pct': tag_counts.get(1, 0) / n * 100,
            'exactly_5_pct': tag_counts.get(5, 0) / n * 100,
        }

    def _image_stats(self, ok_rows):
        has_raster = [r for r in ok_rows if r.get('has_raster')]
        image_sent = [r for r in ok_rows if r.get('images_sent')]
        raster_ids = {r['problem_id'] for r in has_raster}
        sent_ids = {r['problem_id'] for r in image_sent}
        mismatch = sorted(raster_ids ^ sent_ids)

        tikz_in_stmt = [r for r in ok_rows if r.get('has_tikz_in_statement')]
        tikz_replaced = [r for r in ok_rows if (r.get('tikz') or {}).get('replaced')]
        tikz_stmt_ids = {r['problem_id'] for r in tikz_in_stmt}
        tikz_repl_ids = {r['problem_id'] for r in tikz_replaced}
        tikz_mismatch = sorted(tikz_stmt_ids ^ tikz_repl_ids)

        return {
            'has_raster': len(has_raster),
            'image_sent': len(image_sent),
            'mismatch_ids': mismatch,
            'tikz_in_statement': len(tikz_in_stmt),
            'tikz_replaced': len(tikz_replaced),
            'tikz_mismatch_ids': tikz_mismatch,
        }

    def _problem_type_stats(self, rows, ok_rows):
        n = len(rows) or 1
        filled = sum(1 for r in ok_rows if r.get('problem_type'))
        filled_pct = filled / n * 100
        tests_without_subtype = sum(
            1 for r in ok_rows
            if r.get('task_nature') != 'не_задача' and not r.get('problem_type'))
        distribution = dict(Counter(r.get('problem_type') for r in ok_rows
                                    if r.get('problem_type')))

        matched, compared = self._check_type_crosswalk(ok_rows)
        pct = (matched / compared * 100) if compared else 0.0
        return {
            'filled_pct': filled_pct,
            'tests_without_subtype': tests_without_subtype,
            'distribution': distribution,
            'check_type_matched': matched,
            'check_type_compared': compared,
            'check_type_match_pct': pct,
        }

    #: `problems/enrich/prompts_v2.py` — соответствие check_type SolveHub
    #: нашему `problem_type` (дословно из комментария там же).
    #:
    #: ⚠️ Правка владельца 2026-09-04 (§5.5): `открытый_ответ` разведён
    #: обратно на «тест: короткий ответ» / «задача с развёрнутым ответом».
    #: `single_freetext` перешёл сюда ИЗ CHECK_TYPE_AMBIGUOUS — SolveHub сам
    #: определяет его как «список принимаемых написаний» (короткий ответ без
    #: обоснования), соответствие однозначное 1:1, а не «оба варианта
    #: возможны», как было при склеенном значении.
    CHECK_TYPE_MAP = {
        'single_choice': 'единственный_выбор',
        'multiple_choice': 'множественный_выбор',
        'true_false': 'верно_неверно',
        'matching_list': 'сопоставление',
        'single_freetext': 'тест: короткий ответ',
    }
    #: Неоднозначные check_type — решает модель, в сверку не идут.
    #: `uncheckable` значит «ответа в источнике нет вовсе» — это свойство
    #: ДАННЫХ источника, а не тип задачи: текст может оказаться и коротким
    #: ответом, и развёрнутым, и вовсе не задачей — соответствия 1:1 нет.
    CHECK_TYPE_AMBIGUOUS = {'uncheckable', 'multiple_questions'}

    def _check_type_crosswalk(self, ok_rows):
        """Сверка `problem_type` с `check_type` SolveHub там, где он
        ОДНОЗНАЧЕН. Raw JSON лежит вне репозитория (`data_root()/solvehub/
        problems/*.json`) — то же место, что читает `import_solvehub`."""
        from problems.corpus_converter.ingest import data_root
        from problems.management.commands.import_solvehub import SOURCE_NAME
        problems_dir = Path(data_root()) / 'solvehub' / 'problems'
        if not problems_dir.is_dir():
            self.stdout.write('⚠️ данные SolveHub не найдены (%s) — сверка '
                              'check_type пропущена' % problems_dir)
            return 0, 0

        by_row = {r['problem_id']: r for r in ok_rows}
        wanted = set(by_row)
        # external_id (=имя файла без .json= SourceReference.problem_number)
        # -> problem_id, ТОЛЬКО для источника SolveHub.
        ext_to_pid = {}
        for pid, source_name, ext_id in SourceReference.objects.values_list(
                'problem_id', 'source__name', 'problem_number').iterator():
            if pid in wanted and source_name == SOURCE_NAME and ext_id:
                ext_to_pid[ext_id] = pid

        matched = compared = 0
        for json_path in problems_dir.glob('*.json'):
            ext_id = json_path.stem
            pid = ext_to_pid.get(ext_id)
            if pid is None:
                continue
            try:
                raw = json.loads(json_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            check_type = raw.get('check_type')
            expected = self.CHECK_TYPE_MAP.get(check_type)
            if expected is None:
                continue  # неоднозначный или неизвестный check_type
            compared += 1
            if by_row[pid].get('problem_type') == expected:
                matched += 1
        return matched, compared

    def _title_stats(self, ok_rows):
        n = len(ok_rows) or 1
        titles = [(r['problem_id'], r.get('title_candidate') or '') for r in ok_rows]
        nonempty = sum(1 for _pid, t in titles if t.strip())
        too_long = sum(1 for _pid, t in titles if len(t) > 40)
        forbidden = sum(1 for _pid, t in titles if _TITLE_BAD_RE.search(t))
        counts = Counter(t for _pid, t in titles if t.strip())
        top10 = counts.most_common(10)
        max_repeat = top10[0][1] if top10 else 0
        return {
            'nonempty_pct': nonempty / n * 100,
            'too_long': too_long,
            'with_forbidden_chars': forbidden,
            'max_repeat': max_repeat,
            'top10': top10,
        }

    # ------------------------------------------------------------------
    # ФАЗА 4 — четыре очереди + отчёт по concepts_offlist
    # ------------------------------------------------------------------

    def phase4(self, ok_rows):
        broken = [r for r in ok_rows if r.get('text_quality') == 'серьёзные_дефекты']
        not_task = [r for r in ok_rows if r.get('problem_type') == 'не_задача']
        mismatch = [r for r in ok_rows
                   if r.get('answer_consistency') == 'ответ_не_совпадает_с_решением']
        lost_visuals = self._lost_visuals_queue(ok_rows)

        self._write_queue('queue_broken_text.jsonl', broken)
        self._write_queue('queue_not_a_problem.jsonl', not_task)
        self._write_queue('queue_answer_mismatch.jsonl', mismatch)
        self._write_queue('queue_lost_visuals.jsonl', lost_visuals)
        offlist_count = self._offlist_report(ok_rows)

        self.stdout.write('queue_broken_text.jsonl: %d (text_quality = серьёзные_дефекты)'
                          % len(broken))
        by_source = Counter(self._source_name(r['problem_id']) for r in broken)
        self.stdout.write('  по источникам: %s' % dict(by_source.most_common(10)))
        self.stdout.write('queue_not_a_problem.jsonl: %d' % len(not_task))
        self.stdout.write('queue_answer_mismatch.jsonl: %d' % len(mismatch))
        self.stdout.write('queue_lost_visuals.jsonl: %d' % len(lost_visuals))
        self.stdout.write('report_offlist_terms.md: %d уникальных терминов вне списка'
                          % offlist_count)

        return {
            'broken_text': len(broken), 'not_a_problem': len(not_task),
            'answer_mismatch': len(mismatch), 'lost_visuals': len(lost_visuals),
            'offlist_unique_terms': offlist_count,
        }

    def _source_name(self, problem_id):
        if getattr(self, '_source_cache', None) is None:
            cache = {}
            for pid, name in SourceReference.objects.values_list(
                    'problem_id', 'source__name').iterator():
                cache.setdefault(pid, name)
            self._source_cache = cache
        return self._source_cache.get(problem_id, '(без источника)')

    _LOST_VISUAL_NOTE_RE = re.compile('содержание в утраченном визуальном элементе')

    def _lost_visuals_queue(self, ok_rows):
        """Битые ссылки на растровую картинку (нет `ProblemFigure`, но в
        тексте — имя файла картинки или `<img>`) + всё, что модель пометила
        как «упоминается рисунок, а его нет» (`text_quality_note`)."""
        by_pid = {r['problem_id']: r for r in ok_rows}
        wanted = set(by_pid)
        has_figure = set()
        for pid in ProblemFigure.objects.values_list('problem_id', flat=True).iterator():
            if pid in wanted:
                has_figure.add(pid)

        broken_link_ids = set()
        for pid, statement in Problem.objects.values_list('id', 'statement').iterator():
            if pid not in wanted or pid in has_figure:
                continue
            if _FILENAME_IN_TEXT_RE.search(statement or '') or _IMG_TAG_RE.search(statement or ''):
                broken_link_ids.add(pid)
        # Подпункты — тем же критерием, отдельным проходом (join развернул бы
        # строки задач без причины).
        from problems.models import ProblemPart
        for pid, statement in ProblemPart.objects.values_list(
                'problem_id', 'statement').iterator():
            if pid not in wanted or pid in has_figure or pid in broken_link_ids:
                continue
            if _FILENAME_IN_TEXT_RE.search(statement or '') or _IMG_TAG_RE.search(statement or ''):
                broken_link_ids.add(pid)

        note_flagged = {
            r['problem_id'] for r in ok_rows
            if r.get('text_quality') == 'серьёзные_дефекты'
            and self._LOST_VISUAL_NOTE_RE.search(r.get('text_quality_note') or '')
        }
        combined_ids = broken_link_ids | note_flagged
        out = []
        for pid in sorted(combined_ids):
            row = dict(by_pid.get(pid) or {'problem_id': pid})
            row['_reason'] = ([] + (['битая_ссылка'] if pid in broken_link_ids else [])
                              + (['модель_отметила_утрату'] if pid in note_flagged else []))
            out.append(row)
        return out

    def _write_queue(self, filename, rows):
        path = self.report_dir / filename
        with open(path, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False))
                fh.write('\n')

    def _offlist_report(self, ok_rows):
        counter = Counter()
        examples = {}
        for r in ok_rows:
            for term in (r.get('concepts_offlist') or []):
                term = (term or '').strip()
                if not term:
                    continue
                counter[term] += 1
                examples.setdefault(term, []).append(r['problem_id'])

        lines = [
            '# concepts_offlist по всему корпусу',
            '',
            '> Термины, которые модель хотела написать в `econ_concepts`, но их '
            'не было в шорт-листе. Кандидаты в пополнение словаря — ничего из '
            'этого не попадает в базу автоматически.',
            '',
            'Уникальных терминов: **%d**, всего упоминаний: **%d**.' % (
                len(counter), sum(counter.values())),
            '',
            '## Топ-100 по частоте',
            '',
            '| # | Термин | Задач | Примеры id |',
            '|---:|---|---:|---|',
        ]
        for i, (term, count) in enumerate(counter.most_common(100), start=1):
            examples_str = ', '.join(str(x) for x in examples[term][:5])
            lines.append('| %d | %s | %d | %s |' % (i, term, count, examples_str))

        path = self.report_dir / 'report_offlist_terms.md'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
        return len(counter)


def _fmt_mtime(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
