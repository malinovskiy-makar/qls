# -*- coding: utf-8 -*-
"""
Сессия H4, этап 4 — детекторы G9 (ссылка на отсутствующий рисунок/диаграмму) и
G14 (вопрос без условия). НИЧЕГО не правят, только списки id для шлюза.

Оба детектора применяют 5%-предохранитель ПО ИСТОЧНИКАМ (как stub в quality_gate):
если кандидатов в источнике > 5% его published-задач — источник пропускается
(список → *_skipped_source_N.txt). Survivors → файл, который читает quality_gate.

G9 — `missing_figure_ids.txt`:
  statement/подпункт ССЫЛАЕТСЯ на данный визуал («graph below/above», «diagram
  above», «на рисунке», «рисунке справа», «на диаграмме», «… below shows» …) И
  у задачи НЕ прикреплено ни одного файла (Problem.files пуст). Глаголы построения
  («постройте», «draw») сами по себе НЕ триггерят (это не отсутствующий рисунок).

G14 — `no_premise_ids.txt`:
  statement короткий (<120 симв.), начинается с директивы (Определите/Найдите/
  Calculate/…), НЕ содержит ни цифры, ни «=», ни «$» (нет данных/формул), и у
  задачи нет подпунктов с данными → вопрос без вводных.

Запуск:
  ./venv/bin/python manage.py detect_missing_refs            # печать + файлы
  ./venv/bin/python manage.py detect_missing_refs --dry-run  # только печать
"""
import os
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from problems.models import Problem

QA = 'reports/quality_audit'
VALVE = 0.05

# G9: ссылки на ДАННЫЙ визуал (не «постройте»)
FIGURE_REF = [
    # английский — MCQ CollegeBoard/AP
    'graph above', 'graph below', 'diagram above', 'diagram below',
    'figure above', 'figure below', 'graph shows', 'diagram shows',
    'figure shows', 'shown above', 'shown below', 'in the figure above',
    'in the diagram above', 'the graph above', 'the graph below',
    # русский — однозначные ссылки на данный рисунок
    'на рисунке', 'из рисунка', 'по рисунку', 'рисунке справа',
    'рисунке выше', 'рисунке ниже', 'на диаграмме', 'см. рис',
    'представлен на рис', 'показан на рис', 'изображённом на рис',
    'на приведённом рис', 'на приведенном рис',
]
FIGURE_REF_RE = re.compile('|'.join(re.escape(s) for s in FIGURE_REF),
                           re.IGNORECASE)

# G14: директива в начале без данных
DIRECTIVE_RE = re.compile(
    r'^(определите|найдите|рассчитайте|вычислите|посчитайте|укажите|'
    r'calculate|determine|find|compute)\b', re.IGNORECASE)
HAS_DATA_RE = re.compile(r'[0-9=$]')
# слова, указывающие, что премис ВНУТРИ условия (список/перечисление/опции) —
# тогда это НЕ огрызок без условия (премис есть, просто без цифр)
LIST_WORDS_RE = re.compile(
    r'следующ|перечисл|приведённ|приведенн|ниже|списк|из них|данных|'
    r'высказывани|утвержден|вариант|following|listed|below', re.IGNORECASE)
NO_PREMISE_MAXLEN = 120


def _published_by_source():
    by = defaultdict(int)
    rows = Problem.objects.filter(status='published').values_list(
        'id', 'source_references__source_id')
    seen = set()
    for pid, sid in rows:
        if pid in seen:
            continue
        seen.add(pid)
        by[sid or 0] += 1
    return by


def _sid(p):
    ref = p.source_references.values_list('source_id', flat=True).first()
    return ref or 0


def _apply_valve(cands_by_src, pub_by_src, name, stdout):
    """cands_by_src: sid -> [ids]. Возвращает (flagged_ids, skipped)."""
    flagged = []
    skipped = {}
    for sid, ids in sorted(cands_by_src.items()):
        total = pub_by_src.get(sid, 0) or len(ids)
        share = len(ids) / max(total, 1)
        if share > VALVE:
            skipped[sid] = (len(ids), total, share)
            stdout.write(f'  [{name}] src#{sid}: {len(ids)}/{total} '
                         f'({share:.1%}) > 5% — ПРОПУЩЕН')
        else:
            flagged.extend(ids)
            stdout.write(f'  [{name}] src#{sid}: {len(ids)}/{total} '
                         f'({share:.1%}) — зафлагуется')
    return flagged, skipped


class Command(BaseCommand):
    help = 'H4 этап 4: детекторы G9 (рисунки) и G14 (без условия) → шлюз'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)

    def handle(self, *args, **o):
        os.makedirs(QA, exist_ok=True)
        pub_by_src = _published_by_source()

        g9_by_src = defaultdict(list)
        g14_by_src = defaultdict(list)
        g9_ex, g14_ex = [], []

        qs = Problem.objects.filter(status='published',
                                    needs_quality_review=False) \
            .prefetch_related('parts', 'files', 'source_references')
        for p in qs.iterator(chunk_size=500):
            sid = _sid(p)
            stmt = p.statement or ''
            # ── G9 ──
            ref_texts = [stmt] + [pt.statement or '' for pt in p.parts.all()]
            if any(FIGURE_REF_RE.search(t) for t in ref_texts):
                if not p.files.exists():
                    g9_by_src[sid].append(p.id)
                    if len(g9_ex) < 12:
                        m = FIGURE_REF_RE.search(' '.join(ref_texts))
                        g9_ex.append((p.id, sid, m.group(0)))
            # ── G14 ── огрызок без условия: директива, коротко, нет данных,
            # нет подпунктов (если есть parts — премис/опции там), нет
            # список-слов (премис мог бы быть качественным перечислением)
            st = stmt.strip()
            if (st and len(st) < NO_PREMISE_MAXLEN and DIRECTIVE_RE.match(st)
                    and not HAS_DATA_RE.search(st)
                    and not LIST_WORDS_RE.search(st)
                    and not p.parts.exists()):
                g14_by_src[sid].append(p.id)
                if len(g14_ex) < 12:
                    g14_ex.append((p.id, sid, st[:90]))

        self.stdout.write(f'=== G9 (рисунки) кандидатов: '
                          f'{sum(len(v) for v in g9_by_src.values())} ===')
        for pid, sid, frag in g9_ex:
            self.stdout.write(f'  #{pid} src{sid}: …{frag!r}…')
        self.stdout.write(f'=== G14 (без условия) кандидатов: '
                          f'{sum(len(v) for v in g14_by_src.values())} ===')
        for pid, sid, frag in g14_ex:
            self.stdout.write(f'  #{pid} src{sid}: {frag!r}')

        self.stdout.write('\n=== предохранитель G9 ===')
        g9_flag, g9_skip = _apply_valve(g9_by_src, pub_by_src, 'G9', self.stdout)
        self.stdout.write('=== предохранитель G14 ===')
        g14_flag, g14_skip = _apply_valve(g14_by_src, pub_by_src, 'G14', self.stdout)

        self.stdout.write(self.style.SUCCESS(
            f'\nG9 зафлагуется: {len(g9_flag)} (пропущено источников '
            f'{len(g9_skip)}); G14 зафлагуется: {len(g14_flag)} '
            f'(пропущено источников {len(g14_skip)}).'))

        if o['dry_run']:
            self.stdout.write('DRY-RUN: файлы не записаны.')
            return

        for fname, ids, skip in (
                ('missing_figure_ids.txt', g9_flag, g9_skip),
                ('no_premise_ids.txt', g14_flag, g14_skip)):
            with open(os.path.join(QA, fname), 'w', encoding='utf-8') as f:
                f.write(f'# H4 этап 4: {fname} (через 5%-предохранитель). '
                        f'{len(ids)} id. Пропущено источников: '
                        f'{sorted(skip)}\n')
                f.write('\n'.join(map(str, sorted(ids))) + ('\n' if ids else ''))
            self.stdout.write(f'{QA}/{fname}: {len(ids)} id')
