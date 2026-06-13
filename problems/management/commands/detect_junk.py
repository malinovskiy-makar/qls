"""
Сессия C, этап 4 — три детектора мусора/нечитаемости. Только ФЛАГУЮТ
(needs_quality_review) или составляют списки — ничего не правят.

1. Мусор импорта (служебные страницы буклетов AP): ≥2 маркеров типа
   «DO NOT OPEN», «answer sheet», «AP Coordinator» в задаче = мусор.
   Предохранитель 5% НЕ применяется (это не настоящие задачи). → junk_ids.txt
2. Формулы, рассыпанные построчно: ≥6 подряд строк короче 12 символов
   с математическими токенами (числа, =, Σ, одиночные буквы).
   Предохранитель 5% применяется. → broken_formula_ids.txt
3. Расплющенные таблицы: после «таблиц»/«table» в пределах 200 символов
   цепочка ≥8 чисел через пробел. НЕ флагуются — только список
   → flattened_table_ids.txt (решение примет преподаватель).

Файлы детекторов 1–2 читает quality_gate --apply (флаги аддитивны и
переживают пересчёт шлюза).

Запуск:
    ./venv/bin/python manage.py detect_junk --dry-run
    ./venv/bin/python manage.py detect_junk --apply
"""

import os
import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, Source
from problems.management.commands.fix_ile_formulas import problem_full_text

REPORT_DIR = 'reports/quality_audit'
JUNK_FILE = f'{REPORT_DIR}/junk_ids.txt'
BROKEN_FILE = f'{REPORT_DIR}/broken_formula_ids.txt'
BROKEN_SOL_FILE = f'{REPORT_DIR}/broken_formula_solution_ids.txt'
FLAT_FILE = f'{REPORT_DIR}/flattened_table_ids.txt'
VALVE = 0.05

JUNK_MARKERS = [
    'do not open', 'answer sheet', 'ap coordinator', 'incident report',
    'seating chart', 'you are now dismissed', 'raise your hand',
    'exam booklet', 'front cover of', 'are you wearing',
    'when you have completed', 'multiple-choice booklet',
    'do not begin', 'breaking the seal',
]

_MATH_TOKEN_RE = re.compile(r'[0-9=Σ∑]|^[A-Za-zα-ωΑ-Ω][_^]?\{?\w?\}?$')
_NUM_CHAIN_RE = re.compile(r'(?:\d+(?:[.,]\d+)?[ \t]+){7,}\d+(?:[.,]\d+)?')
_TABLE_WORD_RE = re.compile(r'таблиц|table', re.IGNORECASE)


def junk_markers_found(text: str):
    low = text.lower()
    return [m for m in JUNK_MARKERS if m in low]


def has_broken_formula_run(text: str, min_run: int = 6) -> bool:
    run = 0
    for ln in text.split('\n'):
        s = ln.strip()
        if s and len(s) < 12 and _MATH_TOKEN_RE.search(s):
            run += 1
            if run >= min_run:
                return True
        else:
            run = 0
    return False


def has_flattened_table(text: str) -> bool:
    for m in _TABLE_WORD_RE.finditer(text):
        window = text[m.start():m.start() + 200]
        if _NUM_CHAIN_RE.search(window.replace('\n', ' ')):
            return True
    return False


class Command(BaseCommand):
    help = 'Детекторы мусора импорта / рассыпанных формул / расплющенных таблиц'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        apply_flags = options['apply'] and not options['dry_run']
        os.makedirs(REPORT_DIR, exist_ok=True)
        src_names = {s.id: s.name for s in Source.objects.all()}
        src_names[0] = '(без источника)'

        junk = []                          # (pid, sid, markers)
        broken = defaultdict(list)         # sid -> [pid] — рассыпано в УСЛОВИИ
        broken_sol = []                    # [pid] — рассыпано только в решении
        flat = defaultdict(list)           # sid -> [pid]
        src_total = defaultdict(int)

        qs = (Problem.objects.all().order_by('id')
              .prefetch_related('parts', 'source_references'))
        for p in qs.iterator(chunk_size=300):
            refs = list(p.source_references.all())
            sid = refs[0].source_id if refs else 0
            src_total[sid] += 1
            parts = list(p.parts.all())
            full = problem_full_text(p, parts)

            mk = junk_markers_found(full)
            if len(mk) >= 2:
                junk.append((p.id, sid, mk))
            else:
                # политика сессии D: задачу скрывает только рассыпанное УСЛОВИЕ;
                # рассыпанное решение — лишь прячет кнопку «Показать решение»
                stmt_text = '\n'.join([p.statement or '']
                                      + [pt.statement or '' for pt in parts])
                if has_broken_formula_run(stmt_text):
                    broken[sid].append(p.id)
                elif p.solution and has_broken_formula_run(p.solution):
                    broken_sol.append(p.id)
            if has_flattened_table(full):
                flat[sid].append(p.id)

        # ── детектор 2: предохранитель 5% ──
        broken_flag, broken_skipped = [], []
        for sid, pids in sorted(broken.items()):
            share = len(pids) / src_total[sid]
            if share > VALVE:
                broken_skipped.append((sid, pids, share))
            else:
                broken_flag += pids

        junk_ids = [pid for pid, _, _ in junk]
        self.stdout.write(f'1) Мусор буклетов: {len(junk_ids)} задач '
                          f'(без предохранителя)')
        for pid, sid, mk in junk[:10]:
            self.stdout.write(f'   #{pid} (ист.{sid}): {", ".join(mk[:4])}')
        self.stdout.write(f'2) Рассыпанные формулы в УСЛОВИИ: к флагу '
                          f'{len(broken_flag)}; пропущено предохранителем: '
                          f'{sum(len(p) for _, p, _ in broken_skipped)}; '
                          f'только в решении (кнопка): {len(broken_sol)}')
        for sid, pids, share in broken_skipped:
            self.stdout.write(f'   #{sid} {src_names.get(sid, "")[:35]}: '
                              f'{len(pids)}/{src_total[sid]} ({share:.1%}) > 5%')
        self.stdout.write('3) Расплющенные таблицы (НЕ флагуются), по источникам:')
        for sid, pids in sorted(flat.items()):
            self.stdout.write(f'   #{sid} {src_names.get(sid, "")[:35]}: {len(pids)}')

        # ── файлы ──
        with open(JUNK_FILE, 'w', encoding='utf-8') as f:
            f.write('# id\tисточник\tмаркеры\n')
            for pid, sid, mk in junk:
                f.write(f'{pid}\t#{sid}\t{", ".join(mk)}\n')
        with open(BROKEN_FILE, 'w', encoding='utf-8') as f:
            f.write('# id\tисточник (только зафлагованные; пропущенные '
                    'предохранителем — в комментариях ниже)\n')
            for sid, pids in sorted(broken.items()):
                flagged = share = None
                share = len(pids) / src_total[sid]
                flagged = share <= VALVE
                for pid in pids:
                    prefix = '' if flagged else '# (предохранитель) '
                    f.write(f'{prefix}{pid}\t#{sid}\n')
        with open(BROKEN_SOL_FILE, 'w', encoding='utf-8') as f:
            f.write('# id — рассыпанные формулы ТОЛЬКО в решении: задача видна, '
                    'кнопка «Показать решение» скрыта (solution_needs_review)\n')
            for pid in broken_sol:
                f.write(f'{pid}\n')
        with open(FLAT_FILE, 'w', encoding='utf-8') as f:
            f.write('# Расплющенные таблицы — НЕ флагованы, решение за '
                    'преподавателем\n')
            for sid, pids in sorted(flat.items()):
                f.write(f'# источник #{sid} {src_names.get(sid, "")}: '
                        f'{len(pids)} задач\n')
                for pid in pids:
                    f.write(f'{pid}\t#{sid}\n')

        if apply_flags:
            with transaction.atomic():
                n = Problem.objects.filter(
                    id__in=junk_ids + broken_flag).update(
                    needs_quality_review=True)
            self.stdout.write(self.style.SUCCESS(
                f'\nФлагов поставлено: {n} '
                f'(мусор {len(junk_ids)} + формулы {len(broken_flag)}). '
                f'Файлы: {JUNK_FILE}, {BROKEN_FILE}, {FLAT_FILE}'))
        else:
            self.stdout.write(self.style.WARNING(
                '\nDRY-RUN/без --apply: флаги не ставились, файлы записаны.'))
