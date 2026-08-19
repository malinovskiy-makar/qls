"""
Сессия C, этап 1a — расследование «степень vs индекс» по источнику.

Для каждой задачи источника собирает вхождения «буква+цифра» (голые и уже
размеченные X_2/X^2 внутри $...$), классифицирует буквы контекстным
классификатором (classify_letters из fix_ile_formulas) и считает:
  - задач по классам (индексы / степени / смешанные / неясно / без паттерна);
  - сколько задач прошлый прогон разметил НЕВЕРНО (стоит _N, а по правилам ^N,
    и наоборот) — только в полях, где $-спаны создали мы (в бэкапе
    db_backup_before_ile.sqlite3 поле было без $);
  - сколько задач НЕ ТРОНУТО (голые V<цифра> вне $ остались).

Отчёт: reports/quality_audit/ile_investigation.md (30 примеров с обоснованием).

Запуск:
    ./venv/bin/python manage.py investigate_ile --source-id 2
"""

import os
import random
import re
import sqlite3

from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.management.commands.fix_ile_formulas import (
    classify_letters, problem_full_text, _analysis_text, _VD_TOKEN_RE,
)

REPORT = 'reports/quality_audit/ile_investigation.md'
BACKUP = 'backups/db_backup_before_ile.sqlite3'

# строго, как в фиксере: ^{1/2} (дробная степень) — НЕ одиночная цифра
_SUB_TOKEN_RE = re.compile(r'([A-Za-z])_(?:\{(\d)\}|(\d)(?![0-9]))')
_POW_TOKEN_RE = re.compile(r'([A-Za-z])\^(?:\{(\d)\}|(\d)(?![0-9]))')
_NAKED_RE = re.compile(r'(?<![A-Za-z])([A-Za-z])(\d)(?![0-9])')
_SPAN_RE = re.compile(r'\$([^$]+)\$')


def _our_fields(pid, backup_rows):
    """Имена полей задачи, где $ создали мы (в бэкапе поле было без $)."""
    row = backup_rows.get(pid)
    if row is None:
        return set()
    out = set()
    for name, text in zip(('statement', 'solution', 'answer'), row):
        if '$' not in (text or ''):
            out.add(name)
    return out


class Command(BaseCommand):
    help = 'Расследование степень/индекс по источнику (отчёт, ничего не меняет)'

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, default=2)

    def handle(self, *args, **options):
        sid = options['source_id']
        con = sqlite3.connect(BACKUP)
        backup_rows = {r[0]: r[1:] for r in con.execute(
            'SELECT p.id, p.statement, p.solution, p.answer '
            'FROM problems_problem p '
            'JOIN problems_sourcereference sr ON sr.problem_id = p.id '
            # int() явно, а не «argparse же обещал type=int»: гарантия
            # должна быть видна на месте подстановки, как в fix_ile_formulas.
            f'WHERE sr.source_id = {int(sid)}')}  # nosec B608
        con.close()

        problems = (Problem.objects
                    .filter(source_references__source_id=sid).distinct()
                    .prefetch_related('parts').order_by('id'))

        stats = {'index': 0, 'power': 0, 'mixed': 0, 'ambiguous': 0, 'none': 0}
        wrong_problems = []        # прошлый прогон разметил не по правилам
        untouched_problems = []    # голые V<цифра> вне $ остались
        examples = []              # (id, классы, обоснования, фрагмент)

        for p in problems:
            parts = list(p.parts.all())
            full = problem_full_text(p, parts)
            cmap, ev = classify_letters(full)
            if not cmap:
                stats['none'] += 1
                continue
            classes = set(cmap.values())
            if 'ambiguous' in classes:
                stats['ambiguous'] += 1
                cls = 'НЕЯСНО'
            elif classes == {'index'}:
                stats['index'] += 1
                cls = 'ИНДЕКСЫ'
            elif classes == {'power'}:
                stats['power'] += 1
                cls = 'СТЕПЕНИ'
            else:
                stats['mixed'] += 1
                cls = 'СМЕШАННАЯ'

            ours = _our_fields(p.id, backup_rows)
            wrong_here = []
            for fname in ('statement', 'solution', 'answer'):
                if fname not in ours:
                    continue
                text = getattr(p, fname) or ''
                for span in _SPAN_RE.findall(text):
                    for v, d1, d2 in _SUB_TOKEN_RE.findall(span):
                        d = d1 or d2
                        if cmap.get(v) == 'power':
                            wrong_here.append(f'{v}_{d}→^{d}')
                    for v, d1, d2 in _POW_TOKEN_RE.findall(span):
                        d = d1 or d2
                        if cmap.get(v) == 'index':
                            wrong_here.append(f'{v}^{d}→_{d}')
            if wrong_here:
                wrong_problems.append((p.id, wrong_here[:6]))

            naked_here, naked_ours = [], False
            for fname in ('statement', 'solution', 'answer'):
                text = getattr(p, fname) or ''
                outside = _SPAN_RE.sub(' ', text)
                outside_t = _analysis_text(outside)
                for v, d in _NAKED_RE.findall(outside_t):
                    if v in cmap and cmap[v] != 'ambiguous':
                        naked_here.append(f'{v}{d}')
                        if fname in ours:
                            naked_ours = True
            if naked_here:
                untouched_problems.append((p.id, naked_here[:6], naked_ours))

            frag = ''
            m = _VD_TOKEN_RE.search(_analysis_text(full))
            if m:
                s = max(0, m.start() - 60)
                frag = _analysis_text(full)[s:m.start() + 80].replace('\n', ' ⏎ ')
            examples.append((p.id, cls, dict(ev), frag))

        # ── отчёт ──
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
        rng = random.Random(42)
        sample = rng.sample(examples, min(30, len(examples)))
        lines = [
            f'# Расследование «степень vs индекс» — источник #{sid}',
            '',
            f'Задач с паттерном «буква+цифра»: {len(examples)} '
            f'(всего в источнике: {problems.count()}).',
            '',
            f'- только ИНДЕКСЫ: **{stats["index"]}**',
            f'- только СТЕПЕНИ: **{stats["power"]}**',
            f'- смешанные (разные буквы — разные классы): **{stats["mixed"]}**',
            f'- НЕЯСНО (конфликт правил): **{stats["ambiguous"]}**',
            f'- без паттерна: {stats["none"]}',
            '',
            f'**Прошлый прогон разметил НЕВЕРНО: {len(wrong_problems)} задач** '
            f'(в наших $-спанах стоит _N, а по правилам ^N, или наоборот).',
            f'**Не тронуто (голые V-цифра вне $): {len(untouched_problems)} задач**, '
            f'из них в НАШИХ полях (доступны фиксеру): '
            f'{sum(1 for _, _, o in untouched_problems if o)}; остальные — '
            f'в полях с оригинальной TeX-разметкой сайта (не трогаем по дизайну).',
            '',
            '## 30 примеров с классификацией',
            '',
        ]
        for pid, cls, ev, frag in sorted(sample, key=lambda x: x[0]):
            ev_str = '; '.join(f'{v}: {e}' for v, e in ev.items())
            lines.append(f'- `#{pid}` **{cls}** — {ev_str}')
            if frag:
                lines.append(f'  - `{frag}`')
        lines += ['', '## Неверно размеченные (первые 40)', '']
        for pid, fixes in wrong_problems[:40]:
            lines.append(f'- `#{pid}`: {", ".join(fixes)}')
        lines += ['', '## Нетронутые голые (первые 40)', '']
        for pid, toks, ours_flag in untouched_problems[:40]:
            tag = ' **(наше поле)**' if ours_flag else ' (оригинальная TeX-разметка)'
            lines.append(f'- `#{pid}`: {", ".join(toks)}{tag}')

        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        self.stdout.write(
            f"классы: индексы={stats['index']} степени={stats['power']} "
            f"смешанные={stats['mixed']} неясно={stats['ambiguous']} "
            f"без паттерна={stats['none']}")
        self.stdout.write(self.style.SUCCESS(
            f'НЕВЕРНО размечено: {len(wrong_problems)}; '
            f'НЕ тронуто: {len(untouched_problems)}. Отчёт: {REPORT}'))
