"""
Выносит «утёкшие» решения и ответы из условий задач (statement) в правильные
поля (Problem.solution / Problem.answer, для подпунктов — ProblemPart.answer).

Маркеры ищутся ТОЛЬКО в начале строки:
  решение:  \\solution{...}  (вырезается brace-balanced, включая \\solution{}{...}),
            «Решение» (строка целиком), «Решение:», «Решение.»,
            «$$Решение$$», «\\textbf{Решение}» / «\\textbf{Решение:}»
  ответ:    «Ответ:» / «Ответы:» / «$$Ответ$$» — хвост < 300 символов
            (иначе считается решением)

Правила безопасности:
  - позиция маркера решения > 25% длины statement;
  - остаток statement после вырезания ≥ 40 символов;
  - непустые целевые поля НЕ перезаписываются: если совпадают с утёкшим куском
    (нормализация пробелов / префикс) — кусок просто вырезается; если НЕ
    совпадают — задача уходит в список ручного разбора, ничего не меняется;
  - content_hash не трогается;
  - английские источники (#7, #8, #18, #20, #21, #22) пропускаются.

Запуск:
    ./venv/bin/python manage.py extract_leaked_solutions --dry-run --all-sources
    ./venv/bin/python manage.py extract_leaked_solutions --source-id 13 --source-id 14
"""

import os
import random
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart, Source

REPORT_DIR = 'reports/formula_cleanup'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids.txt')
MANUAL_REVIEW_FILE = os.path.join(REPORT_DIR, '01_manual_review_ids.txt')
REPORT_FILE = os.path.join(REPORT_DIR, '01_leaked_solutions.md')

ENGLISH_SOURCES = {7, 8, 18, 20, 21, 22}

MIN_REMAINDER = 40          # минимальная длина statement после вырезания
MIN_MARKER_POS_FRAC = 0.25  # маркер решения должен стоять после 25% текста
MAX_ANSWER_TAIL = 300       # длиннее — считаем решением, а не ответом

# ── Маркеры (только в начале строки) ─────────────────────────────────────────

SOLUTION_LINE_RE = re.compile(
    r'^[ \t]*('
    r'\$\$\s*Решение\s*\$\$'
    r'|\\textbf\{\s*Решение[:.]?\s*\}'
    r'|\\textbf\{\s*Решение'
    r'|Решение\s*[:.]'
    r'|Решение[ \t]*\r?$'
    r')',
    re.MULTILINE,
)

SOLUTION_CMD_RE = re.compile(r'^[ \t]*\\solution\s*\{', re.MULTILINE)

# Сессия C: точная фраза «Решение и ответ» в ЛЮБОМ месте statement (артефакт
# сайта ILE — кнопка «Решение и ответ», после которой идёт полное решение).
# Одиночные «Решение»/«Ответ» посреди строки по-прежнему НЕ маркеры.
SOLUTION_MID_RE = re.compile(
    r'(?<![а-яА-ЯёЁ])Решение\s+и\s+[Оо]твет(?![а-яА-ЯёЁ])')
# Хвост короче этого после «Решение и ответ» — не решение, а мусор
# («Решение и ответ Помогите с решением») → вырезаем только сам маркер
MIN_MID_SOLUTION = 40

# Сессия D: для mid-маркера вместо относительных 25% — абсолютный порог
# длины условия. Относительный порог отсекал легитимные случаи: длинное
# решение в хвосте раздувает len(statement), и маркер на 1024-м символе
# оказывался «раньше 25%» (#3257/#1918). Реальные короткие условия — 250-300
# символов; маркер раньше 120 символов — подозрительно, пропускаем.
MIN_MID_PREFIX = 120

# Сессия D: при конфликте с непустым solution — если утёкший хвост длиннее
# 200 символов и существующее solution содержится в нём (префикс/фрагмент),
# хвост ПОЛНЕЕ → разрешена замена solution.
MIN_REPLACE_LEN = 200

# ── Английские маркеры (сессия D, источники #7,#8,#18,#20-22) ────────────────
EN_CORRECT_RE = re.compile(r'(?<![A-Za-z])Correct answer\s*:\s*', re.IGNORECASE)
EN_ANSWER_RE = re.compile(r'(?<![A-Za-z])Answer\s*:\s*')
EN_SOLUTION_RE = re.compile(r'(?<![A-Za-z])(?:Explanation|Solution)\s*:\s*')
MAX_EN_ANSWER = 30


def find_leaks_en(statement: str):
    """Английские утечки: Correct answer:/Answer: → answer (коротко),
    Explanation:/Solution: → solution. Возвращает ops как find_leaks."""
    if not statement:
        return []
    ops = []
    m_ca = EN_CORRECT_RE.search(statement)
    m_an = EN_ANSWER_RE.search(statement)
    # «Answer:» внутри «Correct Answer:» — не самостоятельный маркер
    if m_ca and m_an and m_ca.start() <= m_an.start() < m_ca.end():
        m_an = EN_ANSWER_RE.search(statement, m_ca.end())
    m_sol = EN_SOLUTION_RE.search(statement)

    ans = min((m for m in (m_ca, m_an) if m), key=lambda m: m.start(),
              default=None)
    if ans:
        seg_end = m_sol.start() if m_sol and m_sol.start() > ans.end() \
            else len(statement)
        tail = statement[ans.end():seg_end].strip()
        if tail and len(tail) <= MAX_EN_ANSWER:
            ops.append((ans.start(), seg_end, 'answer', tail))
        elif tail and len(tail) > MAX_EN_ANSWER and ans is m_an and not m_sol:
            # длинный хвост после голого Answer: — это решение
            ops.append((ans.start(), len(statement), 'solution_mid', tail))
            return sorted(ops)
    if m_sol:
        text = statement[m_sol.end():].strip()
        if len(text) >= MIN_MID_SOLUTION:
            ops.append((m_sol.start(), len(statement), 'solution_mid', text))
        else:
            ops.append((m_sol.start(), m_sol.end(), 'empty', ''))
    return sorted(ops)

ANSWER_LINE_RE = re.compile(
    r'^[ \t]*('
    r'\$\$\s*Ответы?\s*\$\$'
    r'|Ответы?\s*:'
    r')',
    re.MULTILINE,
)


def _find_brace_end(text: str, start: int) -> int:
    """Индекс закрывающей } для { в позиции start. -1 если нет (как в import_matek)."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def texts_match(extracted: str, existing: str) -> bool:
    """Совпадение после нормализации пробелов; «совпадает» = равно или префикс."""
    a, b = _norm(extracted), _norm(existing)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def cleanup_statement(s: str) -> str:
    """Убирает $$$$, висячие пустые строки и хвостовые пробелы."""
    s = s.replace('$$$$', '')
    s = re.sub(r'[ \t]+$', '', s, flags=re.MULTILINE)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def _parse_solution_cmd(text: str, m):
    """
    Разбирает \\solution{...} (и \\solution{}{...}) от позиции маркера.
    Возвращает (cut_end, solution_text) или (None, None) при неудаче.
    """
    brace_pos = text.index('{', m.start())
    end1 = _find_brace_end(text, brace_pos)
    if end1 == -1:
        # обрезанный блок — вырезаем до конца текста
        raw = text[brace_pos + 1:].strip()
        raw = raw.strip('{}').strip()
        return len(text), raw
    arg1 = text[brace_pos + 1:end1]
    cut_end = end1 + 1
    # второй аргумент {…}?
    j = cut_end
    while j < len(text) and text[j] in ' \t\n\r':
        j += 1
    arg2 = None
    if j < len(text) and text[j] == '{':
        end2 = _find_brace_end(text, j)
        if end2 == -1:
            arg2 = text[j + 1:].strip().rstrip('}').strip()
            cut_end = len(text)
        else:
            arg2 = text[j + 1:end2]
            cut_end = end2 + 1
    parts = [p.strip() for p in (arg1, arg2) if p and p.strip()]
    return cut_end, '\n\n'.join(parts)


def find_leaks(statement: str):
    """
    Ищет утёкшие куски в statement.
    Возвращает список операций [(cut_start, cut_end, kind, text)], где
    kind ∈ {'solution', 'answer'}; text — что переносить в целевое поле.
    Условия (25% позиции, 40 символов остатка) проверяются вызывающим кодом.
    """
    if not statement:
        return []

    sol_line = SOLUTION_LINE_RE.search(statement)
    sol_cmd = SOLUTION_CMD_RE.search(statement)
    sol_mid = SOLUTION_MID_RE.search(statement)
    ans = ANSWER_LINE_RE.search(statement)

    candidates = [m for m in (sol_line, sol_cmd, sol_mid) if m]
    sol = min(candidates, key=lambda m: m.start()) if candidates else None

    ops = []

    if ans and (sol is None or ans.start() < sol.start()):
        seg_end = sol.start() if sol else len(statement)
        tail = statement[ans.end():seg_end].strip()
        if len(tail) < MAX_ANSWER_TAIL:
            if tail:
                ops.append((ans.start(), seg_end, 'answer', tail))
            # маркер решения дальше обрабатываем как обычно (ниже)
        else:
            # длинный хвост → это решение; забираем всё до конца
            text = statement[ans.end():].strip()
            if text:
                ops.append((ans.start(), len(statement), 'solution', text))
            return ops  # маркер решения (если был) уже внутри вырезанного

    if sol:
        if sol is sol_cmd:
            cut_end, text = _parse_solution_cmd(statement, sol)
            if text:
                ops.append((sol.start(), cut_end, 'solution', text))
            else:
                # пустой \solution{} — просто вырезать блок, переносить нечего
                ops.append((sol.start(), cut_end, 'empty', ''))
        elif sol is sol_mid:
            text = statement[sol.end():].strip()
            if len(text) >= MIN_MID_SOLUTION:
                # отдельный kind: позиция проверяется абсолютным порогом
                ops.append((sol.start(), len(statement), 'solution_mid', text))
            else:
                # короткий хвост — не решение; вырезаем только маркер-артефакт
                ops.append((sol.start(), sol.end(), 'empty', ''))
        else:
            text = statement[sol.end():].strip()
            if text:
                ops.append((sol.start(), len(statement), 'solution', text))
            else:
                # голый маркер в самом конце — вырезаем его
                ops.append((sol.start(), len(statement), 'empty', ''))

    return sorted(ops)


class Command(BaseCommand):
    help = 'Выносит утёкшие решения/ответы из statement в solution/answer'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--source-id', type=int, action='append', default=[])
        parser.add_argument('--all-sources', action='store_true')
        parser.add_argument('--english', action='store_true',
                            help='Английские маркеры (Correct answer:/Answer:/'
                                 'Solution:/Explanation:) по источникам '
                                 '#7,#8,#18,#20-22')
        parser.add_argument('--examples', type=int, default=20)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_examples = options['examples']
        self.english_mode = options['english']

        if self.english_mode:
            source_ids = sorted(ENGLISH_SOURCES)
        elif options['all_sources']:
            source_ids = [s.id for s in Source.objects.order_by('id')
                          if s.id not in ENGLISH_SOURCES]
        elif options['source_id']:
            source_ids = [sid for sid in options['source_id']
                          if sid not in ENGLISH_SOURCES]
        else:
            self.stderr.write('Укажите --source-id N, --all-sources или --english')
            return

        os.makedirs(REPORT_DIR, exist_ok=True)
        if dry_run:
            self.stdout.write(self.style.WARNING('── DRY-RUN: изменения не сохраняются ──'))

        per_source = {}      # sid -> stats
        all_examples = []    # (sid, pid, field, kind, cut_frag, target_before)
        manual_ids = set()
        changed_ids = set()

        for sid in source_ids:
            try:
                source = Source.objects.get(pk=sid)
            except Source.DoesNotExist:
                continue
            stats = {'name': source.name, 'solutions': 0, 'answers': 0,
                     'dup_cut': 0, 'empty_cut': 0, 'manual': 0,
                     'problems_changed': 0, 'parts_changed': 0}

            problems = (
                Problem.objects
                .filter(source_references__source=source)
                .distinct()
                .prefetch_related('parts')
                .order_by('id')
            )

            with transaction.atomic():
                for problem in problems.iterator(chunk_size=500):
                    changed = self._process_problem(
                        problem, stats, manual_ids, all_examples, sid, dry_run)
                    if changed:
                        changed_ids.add(problem.id)
                        stats['problems_changed'] += 1

                    for part in problem.parts.all():
                        pchanged = self._process_part(
                            problem, part, stats, manual_ids, all_examples,
                            sid, dry_run)
                        if pchanged:
                            changed_ids.add(problem.id)
                            stats['parts_changed'] += 1

            if any(stats[k] for k in ('solutions', 'answers', 'dup_cut',
                                      'empty_cut', 'manual')):
                per_source[sid] = stats
                self.stdout.write(
                    f"#{sid:>2} {source.name[:42]:<42} "
                    f"решений={stats['solutions']:>4} ответов={stats['answers']:>4} "
                    f"дубль-вырезано={stats['dup_cut']:>4} пустых={stats['empty_cut']:>3} "
                    f"ручной разбор={stats['manual']:>4}"
                )

        # ── примеры ──
        rng = random.Random(42)
        sample = (rng.sample(all_examples, max_examples)
                  if len(all_examples) > max_examples else all_examples)
        self.stdout.write(f'\nПримеры ({len(sample)} из {len(all_examples)}):')
        for sid, pid, field, kind, frag, target_before in sample:
            self.stdout.write(f'\n#{pid} (источник {sid}) [{field}] → {kind}')
            self.stdout.write(f'  вырезано: {frag[:180]}')
            if target_before:
                self.stdout.write(f'  целевое поле было: {target_before[:100]}')

        # ── файлы ──
        if not dry_run:
            self._append_ids(CHANGED_IDS_FILE, changed_ids)
            self._append_ids(MANUAL_REVIEW_FILE, manual_ids)
            self._write_report(per_source, all_examples)

        total_changed = len(changed_ids)
        self.stdout.write(f'\nИтого: задач затронуто {total_changed}, '
                          f'ручной разбор: {len(manual_ids)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: ничего не сохранено.'))

    # ──────────────────────────────────────────────────────────────────────
    def _try_extract(self, statement, get_target, kind_to_field):
        """
        Общая логика для problem/part. Итеративно вырезает ВСЕ маркеры
        (в statement бывает несколько \\solution{}-блоков). Возвращает
        (new_statement, updates: {field: value}, results: [(kind, frag, status)])
        либо (None, None, results) если менять нечего.
        status ∈ {'moved', 'dup_cut', 'empty_cut', 'manual', 'skipped'}
        """
        results = []
        updates = {}
        current = statement
        any_change = False
        seen_manual = set()   # позиции/тексты, уже отправленные в manual

        for _ in range(20):   # защита от зацикливания
            ops = (find_leaks_en(current) if getattr(self, 'english_mode', False)
                   else find_leaks(current))
            if not ops:
                break

            cuts = []
            for cut_start, cut_end, kind, text in ops:
                # позиция маркера решения: построчные — > 25% длины,
                # mid-маркер — абсолютный порог (см. MIN_MID_PREFIX)
                if (kind == 'solution'
                        and cut_start < MIN_MARKER_POS_FRAC * len(current)):
                    key = ('skip', kind, text[:80])
                    if key not in seen_manual:
                        seen_manual.add(key)
                        results.append((kind, current[cut_start:cut_end], 'skipped'))
                    continue
                if kind == 'solution_mid' and cut_start < MIN_MID_PREFIX:
                    key = ('skip', kind, text[:80])
                    if key not in seen_manual:
                        seen_manual.add(key)
                        results.append((kind, current[cut_start:cut_end], 'skipped'))
                    continue
                if kind == 'empty':
                    cuts.append((cut_start, cut_end))
                    results.append((kind, current[cut_start:cut_end], 'empty_cut'))
                    continue
                # ответ с LaTeX-окружением внутри (\begin{tcolorbox} и т.п.) —
                # вероятно, захватили служебный блок → ручной разбор
                if kind == 'answer' and '\\begin{' in text:
                    key = ('man', kind, text[:80])
                    if key not in seen_manual:
                        seen_manual.add(key)
                        results.append((kind, text, 'manual'))
                    continue
                field = kind_to_field[kind]
                existing = updates.get(field) or get_target(field)
                if existing:
                    existing_n, text_n = _norm(existing), _norm(text)
                    if (kind in ('solution', 'solution_mid')
                            and field == 'solution'
                            and len(text) > MIN_REPLACE_LEN
                            and len(text_n) > len(existing_n)
                            and existing_n in text_n):
                        # утёкший хвост ПОЛНЕЕ существующего решения
                        # (префикс/фрагмент) → разрешённая замена (сессия D)
                        cuts.append((cut_start, cut_end))
                        updates[field] = text
                        results.append((kind, text, 'replaced'))
                    elif texts_match(text, existing):
                        cuts.append((cut_start, cut_end))
                        results.append((kind, text, 'dup_cut'))
                    else:
                        key = ('man', kind, text[:80])
                        if key not in seen_manual:
                            seen_manual.add(key)
                            results.append((kind, text, 'manual'))
                else:
                    cuts.append((cut_start, cut_end))
                    updates[field] = text
                    results.append((kind, text, 'moved'))

            if not cuts:
                break

            pieces = []
            prev = 0
            for s, e in sorted(cuts):
                pieces.append(current[prev:s])
                prev = e
            pieces.append(current[prev:])
            candidate = cleanup_statement(''.join(pieces))

            if len(candidate) < MIN_REMAINDER:
                # остаток слишком короткий — откатываем ЭТУ итерацию и стоп
                for s, e in sorted(cuts):
                    kind_txt = current[s:e]
                    results.append(('rollback', kind_txt, 'manual'))
                # отменяем перенесённые на этой итерации поля
                for cut_start, cut_end, kind, text in ops:
                    field = kind_to_field.get(kind)
                    if field and updates.get(field) == text:
                        del updates[field]
                break

            current = candidate
            any_change = True

        if not any_change:
            return None, None, results
        return current, updates, results

    def _process_problem(self, problem, stats, manual_ids, all_examples,
                         sid, dry_run):
        statement = problem.statement or ''
        new_statement, updates, results = self._try_extract(
            statement,
            lambda f: getattr(problem, f) or '',
            {'solution': 'solution', 'solution_mid': 'solution',
             'answer': 'answer'},
        )
        self._account(results, stats, manual_ids, all_examples, sid,
                      problem.id, 'statement',
                      lambda f: getattr(problem, f) or '')
        if new_statement is None:
            return False
        if not dry_run:
            fields = dict(updates or {})
            fields['statement'] = new_statement
            Problem.objects.filter(pk=problem.pk).update(**fields)
        return True

    def _process_part(self, problem, part, stats, manual_ids, all_examples,
                      sid, dry_run):
        statement = part.statement or ''
        new_statement, updates, results = self._try_extract(
            statement,
            lambda f: getattr(part, f) or '',
            # у подпункта целевое — answer
            {'solution': 'answer', 'solution_mid': 'answer', 'answer': 'answer'},
        )
        self._account(results, stats, manual_ids, all_examples, sid,
                      problem.id, f'part({part.label})',
                      lambda f: getattr(part, f) or '')
        if new_statement is None:
            return False
        if not dry_run:
            fields = dict(updates or {})
            fields['statement'] = new_statement
            ProblemPart.objects.filter(pk=part.pk).update(**fields)
        return True

    def _account(self, results, stats, manual_ids, all_examples, sid, pid,
                 field_label, get_target):
        for kind, text, status in results:
            is_sol = kind in ('solution', 'solution_mid')
            if status == 'moved':
                stats['solutions' if is_sol else 'answers'] += 1
                all_examples.append((sid, pid, field_label, f'{kind} (перенос)',
                                     text, ''))
            elif status == 'replaced':
                stats['replaced'] = stats.get('replaced', 0) + 1
                all_examples.append((sid, pid, field_label,
                                     f'{kind} (замена более полным)', text, ''))
            elif status == 'dup_cut':
                stats['dup_cut'] += 1
                all_examples.append((sid, pid, field_label, f'{kind} (дубль, вырезан)',
                                     text, get_target(
                                         'solution' if is_sol else 'answer')))
            elif status == 'empty_cut':
                stats['empty_cut'] += 1
            elif status == 'manual':
                stats['manual'] += 1
                manual_ids.add(pid)

    def _append_ids(self, path, ids):
        existing = set()
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                existing = {ln.strip() for ln in f if ln.strip()}
        new = sorted({str(i) for i in ids} - existing, key=int)
        if new:
            with open(path, 'a', encoding='utf-8') as f:
                f.write('\n'.join(new) + '\n')

    def _write_report(self, per_source, all_examples):
        lines = ['# Этап 2 — вынос утёкших решений и ответов', '',
                 '| # | Источник | Решений перенесено | Ответов перенесено '
                 '| Дублей вырезано | Пустых маркеров | Ручной разбор '
                 '| Задач изменено | Подпунктов |',
                 '|---|----------|--------------------|--------------------'
                 '|-----------------|-----------------|---------------'
                 '|----------------|------------|']
        for sid, s in sorted(per_source.items()):
            lines.append(
                f"| {sid} | {s['name']} | {s['solutions']} | {s['answers']} "
                f"| {s['dup_cut']} | {s['empty_cut']} | {s['manual']} "
                f"| {s['problems_changed']} | {s['parts_changed']} |")

        rng = random.Random(7)
        moved = [e for e in all_examples if 'перенос' in e[3]]
        sample = rng.sample(moved, 10) if len(moved) > 10 else moved
        lines += ['', '## Примеры «было → стало»', '']
        for sid, pid, field, kind, frag, _ in sample:
            frag1 = frag.replace('\n', ' ⏎ ')[:300]
            lines.append(f'### Задача #{pid} (источник {sid}, {field}, {kind})')
            lines.append(f'Вырезано из statement и перенесено: `{frag1}`')
            lines.append('')

        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
