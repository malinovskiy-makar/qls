# -*- coding: utf-8 -*-
"""Разведка источника «МатЭк — Overleaf архивы (2021–2025)». ТОЛЬКО ЧИТАЕТ.

Один вопрос: можно ли отдавать МатЭк человеку на ревью целиком прямо сейчас,
или сначала нужна механика, или отдавать частями. Команда ничего не пишет в
базу и ничего не чинит — только считает и складывает числа в
reports/matek_recon/recon_data.json, откуда их берёт RECON.md.

Что считается:
  1. Инвентаризация: статусы, темы, сложность, наличие решения/ответа/
     подпунктов, длина условия, язык, происхождение (пути .tex в note).
  2. Разложение «сигналов оставшейся механики» (тех самых 9% из
     reports/ile_triage/source_readiness.md) по группам И ПО ПЕРЕСЕЧЕНИЯМ.
     Детекторы взяты дословно из ile_source_readiness (ветка
     feat/ile-review-triage) — второй набор эвристик разошёлся бы с замером,
     который мы объясняем.
  3. Срез МатЭк из уже готового аудита применённых откатов
     (reports/batch2_sweep/applied_revert_audit.md и его сырьё).
  4. Пересечения: игровой пул Econ Rush, отревьюенный ILE, пакет АА,
     дубли внутри самого источника.
  6. Профиль срабатываний детекторов МатЭк против профиля ILE (доли).

⚠️ Числа детекторов — НЕ оценка доли дефектных задач. Калибровка на 2 401
вердикте (решение Notion 3abb11c92bc18133aea8c3ee9d8716bd) показала 60%
ложных срабатываний и почти нулевую полноту по четырём категориям из семи.
Здесь они значат ровно одно: «сюда ещё придёт механика».

    ./venv/bin/python manage.py matek_recon
    ./venv/bin/python manage.py matek_recon --source-id 13 --seed 20260808
"""

import json
import os
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from problems.diagnostics import (
    LIST_LINE_RE, detect_latex_junk, detect_truncated, line_ends_badly,
    strip_math_regions)
from problems.management.commands.audit_render_quality import check_field
from problems.management.commands.detect_flattened_tables import is_table_field
from problems.models import Problem, ProblemPart, ReviewVerdict, SourceReference
from problems.revert_damage import compare_field

REPORT_DIR = 'reports/matek_recon'
OUT_JSON = os.path.join(REPORT_DIR, 'recon_data.json')

MATEK_SOURCE_ID = 13
ILE_SOURCE_ID = 2
AA_SOURCE_ID = 6

BATCH2_IDS = 'reports/batch2/changed_problem_ids.txt'
BATCH2_REIMPORT = 'reports/batch2/skipped_flagged.txt'
BATCH2_DIGIT_CANDIDATES = 'reports/batch2_sweep/digit_sign_candidates.json'
REVERT_BACKUP = 'reports/batch2_sweep/backup_revert_20260721_112821.json'
REVERT_RENDER = 'reports/batch2_sweep/render_result.json'

# Папка zip-архивов Overleaf, из которых собран источник (DEFAULT_ZIP_DIR
# импортёра import_matek).
ZIP_DIR = ('materials/Archive 6/Archive 5/Archive 3/Archive 2/'
           'Overleaf Projects (20 items)')

CHUNK = 500


def _nfc(s):
    """macOS отдаёт имена в NFD, база хранит NFC — без нормализации «МатЭк»
    из zip и «МатЭк» из note не совпадут ни одним символом с диакритикой."""
    return unicodedata.normalize('NFC', s or '')

# ── Детекторы, дословно перенесённые из ile_source_readiness ────────────────
# Ветка feat/ile-review-triage в эту линию не влита; копируем, а не выдумываем
# заново, иначе объясняемые 9% посчитаются другой линейкой.

TIKZ_RE = re.compile(r'\\begin\{tikzpicture\}|\\addplot|\\draw\[|\\foreach')
REPLACEMENT_RE = re.compile('\ufffd')
_ESCAPED_DOLLAR_RE = re.compile(r'\\\$')

# Markdown-таблица палочками: строка, где не меньше двух «|» вне математики.
# Отдельно от flattened_table (тот ловит & и tabular) — палочка это чужой
# формат, попавший в LaTeX-банк, KaTeX её не рисует.
_PIPE_ROW_RE = re.compile(r'(?m)^[^\n]*\|[^\n|]*\|[^\n]*$')

# Инлайновые маркеры подпунктов, слипшиеся в строку — из ile_detector_calibration.
MERGED_LIST_RE = re.compile(
    r'[а-яa-z]\)\s*\S.{5,}?[а-яa-z]\)|\d\)\s*\S.{5,}?\d\)')
CAND_LEAK_RE = re.compile(r'(?:^|[\s.;)])(?:Решение|Ответы?)\s*[:.]\s', re.M)
CAND_STRAY_ANSWERS_RE = re.compile(r'^\s*\d\)\s*\S')


def unpaired_dollar(text):
    return _ESCAPED_DOLLAR_RE.sub('', text or '').count('$') % 2 == 1


def glue_v2_candidate(text):
    """Пустая строка ПОСРЕДИ предложения (кандидат склейки v2)."""
    if not text or '\n\n' not in text:
        return False
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip():
            continue
        prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j].strip()), None)
        nxt = next((lines[j] for j in range(i + 1, len(lines)) if lines[j].strip()), None)
        if prev is None or nxt is None:
            continue
        if LIST_LINE_RE.match(prev) or LIST_LINE_RE.match(nxt):
            continue
        first = nxt.strip()[0]
        if first.isalpha() and first.islower() and line_ends_badly(prev):
            return True
    return False


def pipe_table(text):
    """Markdown-таблица палочками вне математики."""
    if not text or '|' not in text:
        return False
    return bool(_PIPE_ROW_RE.search(strip_math_regions(text)))


def field_signals(text, is_statement=False, is_solution=False):
    """Все детекторные сигналы одного поля — из ile_detector_calibration."""
    if not text:
        return set()
    out = {t for _sev, t, _snip in check_field('field', text, is_statement)}
    if is_solution:
        if CAND_STRAY_ANSWERS_RE.match(text) or CAND_LEAK_RE.search(text[:80]):
            out.add('cand_leak')
    elif CAND_LEAK_RE.search(text):
        out.add('cand_leak')
    if detect_latex_junk(text):
        out.add('latex_junk')
    if detect_truncated(text):
        out.add('truncated')
    if is_table_field(text):
        out.add('flattened_table')
    if glue_v2_candidate(text):
        out.add('glue_v2')
    if MERGED_LIST_RE.search(text):
        out.add('merged_list')
    if TIKZ_RE.search(text):
        out.add('tikz')
    return out


# ── Мелкие утилиты ──────────────────────────────────────────────────────────

_CYR_RE = re.compile(r'[а-яёА-ЯЁ]')
_LAT_RE = re.compile(r'[a-zA-Z]')
_WORD_RE = re.compile(r'[^\W\d_]{2,}', re.UNICODE)
_NORM_WS_RE = re.compile(r'\s+')


def language_of(text):
    """ru / en / mixed / none — по доле кириллицы среди буквенных слов.

    Считаем по СЛОВАМ, а не по буквам: латиница в русском тексте почти всегда
    это переменные формул (Q, P, TC), и посимвольный счёт объявил бы половину
    банка смешанной.
    """
    bare = strip_math_regions(text or '')
    words = _WORD_RE.findall(bare)
    if not words:
        return 'none'
    cyr = sum(1 for w in words if _CYR_RE.search(w))
    lat = sum(1 for w in words if _LAT_RE.search(w) and not _CYR_RE.search(w))
    total = cyr + lat
    if not total:
        return 'none'
    share = 1.0 * cyr / total
    if share >= 0.9:
        return 'ru'
    if share <= 0.1:
        return 'en'
    return 'mixed'


def norm_for_dup(text):
    """Нормализация для точного сравнения условий: регистр, ё, пробелы, знаки."""
    t = unicodedata.normalize('NFKC', text or '').lower().replace('ё', 'е')
    t = re.sub(r'[^\w\s]', ' ', t, flags=re.UNICODE)
    return _NORM_WS_RE.sub(' ', t).strip()


def load_ids(path):
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            head = line.split()[0] if line.split() else ''
            head = head.split(':')[0]
            if head.isdigit():
                out.add(int(head))
    return out


def load_digit_pids(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding='utf-8') as f:
        return {c['pid'] for c in json.load(f)}


def pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


class Command(BaseCommand):
    help = 'Разведка источника МатЭк: инвентаризация, сигналы, откат, пересечения. Только чтение.'

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, default=MATEK_SOURCE_ID)
        parser.add_argument('--seed', type=int, default=20260808)

    # ── вспомогательное ─────────────────────────────────────────────────

    def _first_source_map(self):
        """id задачи → (id источника, имя). Первая привязка, как в
        ile_source_readiness и в bank_report — иначе цифры не сойдутся."""
        out = {}
        for pid, sid, name in SourceReference.objects.values_list(
                'problem_id', 'source_id', 'source__name').order_by('problem_id', 'id'):
            out.setdefault(pid, (sid, name))
        return out

    def handle(self, *args, **opts):
        os.makedirs(REPORT_DIR, exist_ok=True)
        sid = opts['source_id']
        data = {'source_id': sid, 'seed': opts['seed']}

        self.stdout.write('Карта источников…')
        first_src = self._first_source_map()
        mine = {pid for pid, (s, _n) in first_src.items() if s == sid}
        data['name'] = next((n for (s, n) in first_src.values() if s == sid), '?')

        # задачи, где МатЭк вообще упомянут (не обязательно первым)
        any_ref = set(SourceReference.objects.filter(source_id=sid)
                      .values_list('problem_id', flat=True))
        data['refs_total'] = SourceReference.objects.filter(source_id=sid).count()
        data['problems_any_ref'] = len(any_ref)
        data['problems_first_ref'] = len(mine)
        data['shared_with_other_source'] = len(any_ref - mine)

        data.update(self._task1(sid, mine, any_ref))
        data.update(self._task2(mine))
        data.update(self._task3(sid, first_src))
        data.update(self._task4(sid, mine, any_ref, first_src))
        data.update(self._task6(mine))

        with open(OUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS('Данные → {}'.format(OUT_JSON)))

    # ── Задача 1: инвентаризация ────────────────────────────────────────

    def _task1(self, sid, mine, any_ref):
        self.stdout.write('Задача 1: инвентаризация…')
        out = {}
        qs = Problem.objects.filter(pk__in=mine)

        out['by_status'] = dict(Counter(qs.values_list('status', flat=True)))
        visible_ids = set(qs.filter(status='published', needs_quality_review=False)
                          .values_list('id', flat=True))
        out['visible'] = len(visible_ids)
        out['published'] = qs.filter(status='published').count()
        out['gated'] = qs.filter(status='published', needs_quality_review=True).count()
        out['solution_needs_review'] = qs.filter(solution_needs_review=True).count()
        out['visible_ids_count'] = len(visible_ids)
        self._visible_ids = visible_ids

        # темы (только по видимым — ревьюеру покажут именно их)
        topics = Counter()
        for name in Problem.objects.filter(pk__in=visible_ids).values_list(
                'topics__name', flat=True):
            topics[name or '(без темы)'] += 1
        out['topics'] = topics.most_common()

        out['difficulty'] = dict(Counter(
            Problem.objects.filter(pk__in=visible_ids)
            .values_list('difficulty', flat=True)))
        out['problem_type'] = Counter(
            Problem.objects.filter(pk__in=visible_ids)
            .values_list('problem_type', flat=True)).most_common(15)

        # наполнение полей + язык + длины
        lens, langs = [], Counter()
        with_sol = with_ans = with_parts = 0
        part_counts = Counter()
        sol_lens = []
        parts_by_problem = defaultdict(int)
        for pid, n in Counter(ProblemPart.objects.filter(problem_id__in=visible_ids)
                              .values_list('problem_id', flat=True)).items():
            parts_by_problem[pid] = n
        for p in (Problem.objects.filter(pk__in=visible_ids)
                  .only('id', 'statement', 'solution', 'answer')
                  .iterator(chunk_size=CHUNK)):
            st = p.statement or ''
            lens.append(len(st))
            langs[language_of(st)] += 1
            if (p.solution or '').strip():
                with_sol += 1
                sol_lens.append(len(p.solution))
            if (p.answer or '').strip():
                with_ans += 1
            n = parts_by_problem.get(p.pk, 0)
            if n:
                with_parts += 1
            part_counts[n] += 1
        lens.sort()
        out['statement_len'] = {
            'avg': round(sum(lens) / len(lens), 1) if lens else 0,
            'median': lens[len(lens) // 2] if lens else 0,
            'p10': lens[int(len(lens) * 0.10)] if lens else 0,
            'p90': lens[int(len(lens) * 0.90)] if lens else 0,
            'max': lens[-1] if lens else 0,
            'under_80': sum(1 for x in lens if x < 80),
        }
        out['solution_len_avg'] = round(sum(sol_lens) / len(sol_lens), 1) if sol_lens else 0
        out['with_solution'] = with_sol
        out['with_answer'] = with_ans
        out['with_parts'] = with_parts
        out['parts_total'] = sum(k * v for k, v in part_counts.items())
        out['lang'] = dict(langs)

        # происхождение: пути .tex в note
        notes = list(SourceReference.objects.filter(source_id=sid)
                     .values_list('problem_id', 'note'))
        roots = Counter()
        files = Counter()
        for pid, note in notes:
            note = (note or '').strip()
            if not note:
                roots['(пусто)'] += 1
                continue
            files[note] += 1
            roots[note.split('/')[0]] += 1
        out['note_roots'] = roots.most_common()
        out['note_files_total'] = len(files)
        out['note_files_top'] = files.most_common(10)
        out['refs_without_note'] = roots.get('(пусто)', 0)

        # мусор в поле «ответ»: у МатЭк ответов почти нет, и часть из тех, что
        # есть, — обломки табличной разметки, а не ответ
        junk_ans = []
        for pid, ans in (Problem.objects.filter(pk__in=visible_ids)
                         .exclude(answer='').values_list('id', 'answer')):
            if re.search(r'\\hline|\\\\|^\s*\|', ans or ''):
                junk_ans.append([pid, (ans or '')[:60]])
        out['junk_answers'] = junk_ans
        out['part_answers'] = ProblemPart.objects.filter(
            problem_id__in=visible_ids).exclude(answer='').count()

        # даты создания
        dates = Counter()
        for dt in Problem.objects.filter(pk__in=mine).values_list('created_at', flat=True):
            dates[dt.strftime('%Y-%m')] += 1
        out['created_months'] = sorted(dates.items())

        # есть ли исходники на диске
        out['tex_on_disk'] = self._check_sources(sorted(files))
        return out

    def _check_sources(self, note_paths):
        """Лежат ли у нас исходники, из которых собран источник.

        ⚠️ Проверять по ИМЕНИ файла нельзя: «КПВ.tex» есть в десятке чужих
        проектов, и поиск по basename даёт бодрое «нашлось», указывая на файл
        совсем другого архива. Поэтому путь ищется ВНУТРИ своего zip:
        note = «Корень/остаток.tex» → архив «Корень.zip» → член архива.
        """
        found, missing = 0, []
        roots_ok, roots_bad = set(), set()
        if not os.path.isdir(ZIP_DIR):
            return {'zip_dir': ZIP_DIR, 'zip_dir_exists': False}
        members = {}
        for fn in os.listdir(ZIP_DIR):
            if not fn.lower().endswith('.zip'):
                continue
            try:
                with zipfile.ZipFile(os.path.join(ZIP_DIR, fn)) as zf:
                    members[_nfc(fn[:-4])] = {_nfc(n) for n in zf.namelist()}
            except Exception:
                continue
        for raw in note_paths:
            path = _nfc(raw)
            root, _, rest = path.partition('/')
            pool = members.get(root)
            if pool and (rest in pool or any(m.endswith('/' + rest) for m in pool)):
                found += 1
                roots_ok.add(root)
            else:
                missing.append(path)
                roots_bad.add(root)
        return {
            'zip_dir': ZIP_DIR, 'zip_dir_exists': True,
            'archives': len(members),
            'paths_total': len(note_paths), 'paths_found': found,
            'paths_missing': len(missing),
            'missing_examples': missing[:10],
            'roots_ok': sorted(roots_ok), 'roots_missing': sorted(roots_bad),
        }

    # ── Задача 2: из чего складываются 9% ───────────────────────────────

    def _task2(self, mine):
        self.stdout.write('Задача 2: разложение сигналов…')
        visible = self._visible_ids
        batch2_all = load_ids(BATCH2_IDS)
        digit_pids = load_digit_pids(BATCH2_DIGIT_CANDIDATES)
        reimport = load_ids(BATCH2_REIMPORT)

        groups = defaultdict(set)      # имя группы → id задач
        sub = defaultdict(set)         # детализация этапа 3
        for p in (Problem.objects.filter(pk__in=visible)
                  .prefetch_related('parts').only('id', 'statement')
                  .iterator(chunk_size=CHUNK)):
            fields = [p.statement or '']
            fields.extend(part.statement or '' for part in p.parts.all())
            text = '\n'.join(fields)

            if any(glue_v2_candidate(f) for f in fields):
                groups['glue_v2'].add(p.pk)
            hit3 = False
            if any(unpaired_dollar(f) for f in fields):
                sub['unpaired_dollar'].add(p.pk)
                hit3 = True
            if any(detect_latex_junk(f) for f in fields):
                sub['latex_junk'].add(p.pk)
                hit3 = True
            if any(REPLACEMENT_RE.search(f) for f in fields):
                sub['replacement_char'].add(p.pk)
                hit3 = True
            if hit3:
                groups['stage3'].add(p.pk)
            if TIKZ_RE.search(text):
                groups['tikz'].add(p.pk)
            if any(pipe_table(f) for f in fields):
                groups['pipe_table'].add(p.pk)

        groups['batch2_digit'] = visible & digit_pids
        groups['reimport_queue'] = visible & reimport

        out = {
            'signal_groups': {k: sorted(v) for k, v in groups.items()},
            'signal_counts': {k: len(v) for k, v in groups.items()},
            'stage3_breakdown': {k: len(v) for k, v in sub.items()},
            'batch2_total_visible': len(visible & batch2_all),
            'batch2_digit_all_statuses': len(mine & digit_pids),
            'reimport_all_statuses': len(mine & reimport),
        }
        # пересечения
        keys = ['glue_v2', 'stage3', 'tikz', 'pipe_table', 'batch2_digit',
                'reimport_queue']
        pairs = {}
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                n = len(groups[a] & groups[b])
                if n:
                    pairs['{} × {}'.format(a, b)] = n
        union = set()
        for k in keys:
            union |= groups[k]
        multi = Counter()
        for pid in union:
            multi[sum(1 for k in keys if pid in groups[k])] += 1
        out['signal_pairs'] = pairs
        out['signal_union'] = len(union)
        out['signal_sum'] = sum(len(groups[k]) for k in keys)
        out['signal_multiplicity'] = dict(sorted(multi.items()))
        out['signal_union_ids'] = sorted(union)
        # сумма ровно по критерию исходного замера (без палочек и очереди)
        readiness_keys = ['glue_v2', 'stage3', 'tikz', 'batch2_digit']
        out['readiness_sum'] = sum(len(groups[k]) for k in readiness_keys)
        ru = set()
        for k in readiness_keys:
            ru |= groups[k]
        out['readiness_union'] = len(ru)
        return out

    # ── Задача 3: срез МатЭк из аудита применённых откатов ──────────────

    def _task3(self, sid, first_src):
        self.stdout.write('Задача 3: что сделал наш откат…')
        if not os.path.exists(REVERT_BACKUP):
            return {'revert': {'error': 'нет бэкапа отката ' + REVERT_BACKUP}}
        with open(REVERT_BACKUP, encoding='utf-8') as f:
            backup = json.load(f)
        stmt_old = {int(k): v for k, v in backup.get('statement', {}).items()}
        part_old = {int(k): v for k, v in backup.get('part', {}).items()}

        stmt_now = dict(Problem.objects.filter(id__in=stmt_old).values_list('id', 'statement'))
        parts_now = {p.pk: (p.statement, p.problem_id, p.label)
                     for p in ProblemPart.objects.filter(pk__in=part_old)}

        render = {}
        if os.path.exists(REVERT_RENDER):
            with open(REVERT_RENDER, encoding='utf-8') as f:
                for r in json.load(f):
                    render[(r['kind'], r['pid'], r['pk'])] = r

        items = []
        for pid, old in stmt_old.items():
            if pid not in stmt_now:
                continue
            items.append(('statement', pid, None, '', old, stmt_now[pid] or ''))
        for pk, old in part_old.items():
            if pk not in parts_now:
                continue
            text, pid, label = parts_now[pk]
            items.append(('part', pid, pk, label or '', old, text or ''))

        mine_items = [it for it in items if first_src.get(it[1], (0, ''))[0] == sid]
        by_flag = Counter()
        damaged, rendered, no_render = set(), 0, 0
        detail = []
        for kind, pid, pk, label, old, new in mine_items:
            flags = compare_field(old, new)
            r = render.get((kind, pid, pk))
            if r:
                rendered += 1
                if r['errors_new'] > r['errors_old']:
                    flags.append('katex_errors_up')
            else:
                no_render += 1
            if flags:
                damaged.add(pid)
                for fl in flags:
                    by_flag[fl] += 1
                detail.append({'kind': kind, 'pid': pid, 'pk': pk, 'label': label,
                               'flags': flags,
                               'katex': [r['errors_old'], r['errors_new']] if r else None})
        return {'revert': {
            'fields_total': len(mine_items),
            'fields_statement': sum(1 for it in mine_items if it[0] == 'statement'),
            'fields_part': sum(1 for it in mine_items if it[0] == 'part'),
            'problems_touched': len({it[1] for it in mine_items}),
            'fields_damaged': sum(1 for d in detail),
            'problems_damaged': len(damaged),
            'damaged_ids': sorted(damaged),
            'by_flag': dict(by_flag),
            'rendered': rendered, 'not_rendered': no_render,
            'detail': detail,
            'damaged_visible': len(damaged & self._visible_ids),
        }}

    # ── Задача 4: пересечения ───────────────────────────────────────────

    def _task4(self, sid, mine, any_ref, first_src):
        self.stdout.write('Задача 4: игра, ILE, АА, дубли…')
        out = {}
        try:
            from game.models import GameQuestion
        except Exception as exc:            # игра может быть не на этой ветке
            out['game'] = {'error': str(exc)}
        else:
            rows = GameQuestion.objects.filter(problem_id__in=mine)
            out['game'] = {
                'total': rows.count(),
                'by_type': dict(Counter(rows.values_list('question_type', flat=True))),
                'generated': rows.filter(is_generated=True).count(),
                'pool_total': GameQuestion.objects.count(),
                'pool_base': GameQuestion.objects.filter(is_generated=False).count(),
            }
            out['game']['by_type_lang'] = dict(Counter(
                '{}/{}'.format(t, l) for t, l in rows.values_list('question_type', 'lang')))

        reviewed = set(ReviewVerdict.objects.values_list('problem_id', flat=True))
        ile_ids = set(SourceReference.objects.filter(source_id=ILE_SOURCE_ID)
                      .values_list('problem_id', flat=True))
        aa_ids = set(SourceReference.objects.filter(source_id=AA_SOURCE_ID)
                     .values_list('problem_id', flat=True))
        out['overlap'] = {
            'reviewed_total': len(reviewed),
            'matek_reviewed': len(mine & reviewed),
            'matek_any_ref_reviewed': len(any_ref & reviewed),
            'matek_and_ile_ref': len(any_ref & ile_ids),
            'matek_and_aa_ref': len(any_ref & aa_ids),
        }
        # пакет АА: какие задачи в него вошли (первый источник = АА, видимые)
        aa_bundle = {pid for pid in aa_ids
                     if first_src.get(pid, (0, ''))[0] == AA_SOURCE_ID}
        out['overlap']['aa_bundle_size'] = len(aa_bundle)
        out['overlap']['matek_in_aa_bundle'] = len(mine & aa_bundle)

        # дубли внутри источника
        visible = self._visible_ids
        norm = defaultdict(list)
        for pid, st in Problem.objects.filter(pk__in=visible).values_list('id', 'statement'):
            key = norm_for_dup(st)
            if len(key) >= 30:
                norm[key].append(pid)
        exact = {k: v for k, v in norm.items() if len(v) > 1}
        out['dups'] = {
            'exact_groups': len(exact),
            'exact_problems': sum(len(v) for v in exact.values()),
            'exact_examples': [sorted(v) for v in list(exact.values())[:12]],
            'short_statements_skipped': sum(
                1 for _pid, st in Problem.objects.filter(pk__in=visible)
                .values_list('id', 'statement') if len(norm_for_dup(st)) < 30),
        }
        # Почти-дубли. Кэш `similar_problems` — это топ-K ближайших соседей,
        # а не «похожие сверх порога»: у КАЖДОЙ задачи там есть соседи, даже
        # если ближайший далёк. Голое число пар ничего не значит, поэтому
        # считаем реальный косинус по эмбеддингам и раскладываем по порогам.
        pairs = sorted({(min(a, b), max(a, b)) for a, b in
                        Problem.similar_problems.through.objects.filter(
                            from_problem_id__in=visible, to_problem_id__in=visible)
                        .values_list('from_problem_id', 'to_problem_id')})
        out['dups']['near_pairs_cached'] = len(pairs)
        out['dups'].update(self._score_pairs(pairs))
        return out

    def _score_pairs(self, pairs):
        """Косинус по эмбеддингам для пар кэша похожих, разложенный по порогам."""
        try:
            import numpy as np
        except ImportError:
            return {'cos_error': 'numpy недоступен'}
        need = {p for pair in pairs for p in pair}
        vecs = {}
        for pid, blob in (Problem.objects.filter(pk__in=need)
                          .values_list('id', 'embedding')):
            if not blob:
                continue
            v = np.frombuffer(bytes(blob), dtype=np.float32)
            n = np.linalg.norm(v)
            if n:
                vecs[pid] = v / n
        buckets = Counter()
        top = []
        for a, b in pairs:
            if a not in vecs or b not in vecs:
                buckets['без эмбеддинга'] += 1
                continue
            c = float(np.dot(vecs[a], vecs[b]))
            if c >= 0.98:
                buckets['>=0.98'] += 1
            elif c >= 0.95:
                buckets['0.95–0.98'] += 1
            elif c >= 0.90:
                buckets['0.90–0.95'] += 1
            else:
                buckets['<0.90'] += 1
            if c >= 0.95:
                top.append([a, b, round(c, 4)])
        top.sort(key=lambda r: -r[2])
        return {'cos_buckets': dict(buckets), 'cos_top': top[:15],
                'cos_pairs_scored': len(pairs)}

    # ── Задача 6: профиль детекторов против ILE ─────────────────────────

    def _task6(self, mine):
        self.stdout.write('Задача 6: профиль детекторов…')
        ile_ids = set(ReviewVerdict.objects.values_list('problem_id', flat=True))
        res = {}
        for tag, ids in (('matek', self._visible_ids), ('ile', ile_ids)):
            per_problem = Counter()
            n = 0
            for p in (Problem.objects.filter(pk__in=ids).prefetch_related('parts')
                      .only('id', 'statement', 'solution', 'answer')
                      .iterator(chunk_size=CHUNK)):
                n += 1
                sig = set()
                sig |= field_signals(p.statement, is_statement=True)
                for part in p.parts.all():
                    sig |= field_signals(part.statement)
                sig |= field_signals(p.solution, is_solution=True)
                sig |= field_signals(p.answer)
                for s in sig:
                    per_problem[s] += 1
            res[tag] = {'n': n, 'counts': dict(per_problem),
                        'shares': {k: round(pct(v, n), 2) for k, v in per_problem.items()}}
        return {'profile': res}
