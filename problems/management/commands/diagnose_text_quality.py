"""
Диагностика качества текстов задач по всем источникам (ничего не меняет).

Для каждого Source собирает по полям statement / solution / answer задач
и подпунктов (ProblemPart):
  - число задач;
  - доля задач, где математика уже размечена ($ или \\();
  - число «голых математических» строк (есть якорь =, ≤, √, ^, _, \\frac, греческие
    буквы — но нет $ и \\();
  - число задач с маркерами «утёкших» решений/ответов в statement
    (\\solution{, строка «Решение...», «Ответ:», англ. Solution/Answer:).

Отчёты: reports/formula_cleanup/00_diagnostics.md и 00_diagnostics.json.
Для ILE (#2) и Сборника тестов АА (#6) — расширенная секция с 15 примерами
«голых» строк.

Запуск:
    ./venv/bin/python manage.py diagnose_text_quality
"""

import json
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, Source

REPORT_DIR = 'reports/formula_cleanup'

EXTENDED_SOURCES = {2, 6}        # ILE, Сборник тестов АА — больше примеров
N_EXAMPLES = 5
N_EXAMPLES_EXTENDED = 15

# Якорь «похоже на математику»
ANCHOR_RE = re.compile(
    r'[=≤≥⩽⩾→√^_]|\\le\b|\\ge\b|\\frac\b'
    r'|[αβγδεζηθλµμνξπρστφχψωΓΔ∆ΘΛΠΣΦΩ]'
)

# Маркеры утёкшего решения (только в начале строки)
LEAK_SOLUTION_RE = re.compile(
    r'^\s*('
    r'\\solution\{'
    r'|\$\$\s*Решение\s*\$\$'
    r'|\\textbf\{\s*Решение'
    r'|Решение\s*[:.]?\s*$'
    r'|Решение\s*[:.]\s'
    r')',
    re.MULTILINE,
)

# Маркеры утёкшего ответа (только в начале строки)
LEAK_ANSWER_RE = re.compile(
    r'^\s*('
    r'Ответы?\s*:'
    r'|\$\$\s*Ответы?\s*\$\$'
    r')',
    re.MULTILINE,
)

# Английские маркеры (диагностика, в этой сессии не правим)
LEAK_EN_RE = re.compile(
    r'^\s*(Solution\b|Answer\s*:)',
    re.MULTILINE,
)


def has_marked_math(text: str) -> bool:
    return '$' in text or '\\(' in text


def naked_math_lines(text: str):
    """Строки с математическим якорем, но без $ и \\(."""
    out = []
    for ln in text.split('\n'):
        if '$' in ln or '\\(' in ln or '\\[' in ln:
            continue
        if ANCHOR_RE.search(ln):
            out.append(ln)
    return out


class Command(BaseCommand):
    help = 'Диагностика качества текстов по всем источникам (только отчёт)'

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        report = {}          # source_id -> stats dict
        for source in Source.objects.order_by('id'):
            problems = (
                Problem.objects
                .filter(source_references__source=source)
                .distinct()
                .prefetch_related('parts')
                .order_by('id')
            )
            n_problems = problems.count()
            if not n_problems:
                continue

            extended = source.id in EXTENDED_SOURCES
            max_ex = N_EXAMPLES_EXTENDED if extended else N_EXAMPLES

            stats = {
                'source_id': source.id,
                'source_name': source.name,
                'problems': n_problems,
                'with_marked_math': 0,          # задач, где есть $ или \(
                'naked_math_lines': 0,          # «голых» строк суммарно
                'problems_with_naked_math': 0,
                'leak_solution': 0,             # задач с маркером решения в statement
                'leak_answer': 0,
                'leak_english': 0,
                'examples_naked': [],           # (problem_id, field, line)
                'examples_leak_solution': [],
                'examples_leak_answer': [],
                'examples_leak_english': [],
            }

            for problem in problems.iterator(chunk_size=500):
                texts = [('statement', problem.statement or ''),
                         ('solution', problem.solution or ''),
                         ('answer', problem.answer or '')]
                for part in problem.parts.all():
                    texts.append((f'part({part.label}).statement', part.statement or ''))
                    texts.append((f'part({part.label}).answer', part.answer or ''))

                if any(has_marked_math(t) for _, t in texts if t):
                    stats['with_marked_math'] += 1

                problem_naked = 0
                for field, t in texts:
                    if not t:
                        continue
                    lines = naked_math_lines(t)
                    problem_naked += len(lines)
                    for ln in lines:
                        if len(stats['examples_naked']) < max_ex:
                            stats['examples_naked'].append(
                                (problem.id, field, ln.strip()[:200]))
                stats['naked_math_lines'] += problem_naked
                if problem_naked:
                    stats['problems_with_naked_math'] += 1

                st = problem.statement or ''
                m = LEAK_SOLUTION_RE.search(st)
                if m:
                    stats['leak_solution'] += 1
                    if len(stats['examples_leak_solution']) < max_ex:
                        frag = st[m.start():m.start() + 200].strip()
                        stats['examples_leak_solution'].append((problem.id, frag))
                m = LEAK_ANSWER_RE.search(st)
                if m:
                    stats['leak_answer'] += 1
                    if len(stats['examples_leak_answer']) < max_ex:
                        frag = st[m.start():m.start() + 200].strip()
                        stats['examples_leak_answer'].append((problem.id, frag))
                m = LEAK_EN_RE.search(st)
                if m:
                    stats['leak_english'] += 1
                    if len(stats['examples_leak_english']) < max_ex:
                        frag = st[m.start():m.start() + 200].strip()
                        stats['examples_leak_english'].append((problem.id, frag))

            report[source.id] = stats
            self.stdout.write(
                f"#{source.id:>2} {source.name[:45]:<45} "
                f"задач={n_problems:>6} мат.размечено={stats['with_marked_math']:>6} "
                f"голых строк={stats['naked_math_lines']:>6} "
                f"утечка реш.={stats['leak_solution']:>5} отв.={stats['leak_answer']:>5} "
                f"англ.={stats['leak_english']:>5}"
            )

        # ── JSON ──
        with open(os.path.join(REPORT_DIR, '00_diagnostics.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)

        # ── Markdown ──
        lines = [
            '# Диагностика качества текстов по источникам',
            '',
            '| # | Источник | Задач | С разметкой $ | Голых мат. строк | Задач с голой мат. | Утечка «Решение» | Утечка «Ответ» | Англ. маркеры |',
            '|---|----------|-------|---------------|------------------|--------------------|------------------|----------------|---------------|',
        ]
        for sid, s in report.items():
            pct = 100.0 * s['with_marked_math'] / s['problems']
            lines.append(
                f"| {sid} | {s['source_name']} | {s['problems']} "
                f"| {s['with_marked_math']} ({pct:.0f}%) "
                f"| {s['naked_math_lines']} | {s['problems_with_naked_math']} "
                f"| {s['leak_solution']} | {s['leak_answer']} | {s['leak_english']} |"
            )

        for sid, s in report.items():
            has_examples = (s['examples_naked'] or s['examples_leak_solution']
                            or s['examples_leak_answer'] or s['examples_leak_english'])
            if not has_examples:
                continue
            lines.append('')
            lines.append(f"## #{sid} — {s['source_name']}")
            if s['examples_naked']:
                lines.append('')
                lines.append('### Голые математические строки')
                for pid, field, frag in s['examples_naked']:
                    lines.append(f"- `#{pid}` [{field}]: `{frag}`")
            if s['examples_leak_solution']:
                lines.append('')
                lines.append('### Маркеры утёкших решений в statement')
                for pid, frag in s['examples_leak_solution']:
                    frag = frag.replace('\n', ' ⏎ ')
                    lines.append(f"- `#{pid}`: `{frag}`")
            if s['examples_leak_answer']:
                lines.append('')
                lines.append('### Маркеры утёкших ответов в statement')
                for pid, frag in s['examples_leak_answer']:
                    frag = frag.replace('\n', ' ⏎ ')
                    lines.append(f"- `#{pid}`: `{frag}`")
            if s['examples_leak_english']:
                lines.append('')
                lines.append('### Английские маркеры (Solution/Answer:) — не правим')
                for pid, frag in s['examples_leak_english']:
                    frag = frag.replace('\n', ' ⏎ ')
                    lines.append(f"- `#{pid}`: `{frag}`")

        with open(os.path.join(REPORT_DIR, '00_diagnostics.md'), 'w',
                  encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        self.stdout.write(self.style.SUCCESS(
            f'\nОтчёты записаны: {REPORT_DIR}/00_diagnostics.md, 00_diagnostics.json'))
