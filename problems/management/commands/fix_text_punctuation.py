"""
fix_text_punctuation.py — исправление A5 и A6 вне математики.

A5: \\% вне мат-спанов → %
    Пример: «100\\%» → «100%», но «$100\\%$» → без изменений.

A6: -- вне мат-спанов → — (em-dash U+2014)
    Исключения: числовые диапазоны \\d--\\d, URL-контекст (// или www).
    Пример: «Задача 1 -- условие» → «Задача 1 — условие».

Запуск:
    ./venv/bin/python manage.py fix_text_punctuation --dry-run
    ./venv/bin/python manage.py fix_text_punctuation --all
    ./venv/bin/python manage.py fix_text_punctuation --source-id 14 --dry-run
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart

REPORT_DIR = 'reports/quality_audit'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_F.txt')

# ── мат-спаны ────────────────────────────────────────────────────────────────

MATH_SPAN_RE = re.compile(
    r'\\\[.+?\\\]'
    r'|\\\(.+?\\\)'
    r'|\$\$.+?\$\$'
    r'|\$[^$]+?\$',
    re.DOTALL,
)
_PH = '\x00M\x00'
_PH_RE = re.compile(re.escape(_PH))


def _mask(text):
    spans = []
    def _r(m):
        spans.append(m.group(0))
        return _PH
    t = text.replace('\\$', '\x00D\x00')
    t = MATH_SPAN_RE.sub(_r, t)
    return t, spans


def _unmask(text, spans):
    it = iter(spans)
    r = _PH_RE.sub(lambda _: next(it), text)
    return r.replace('\x00D\x00', '\\$')


# ── A5 ───────────────────────────────────────────────────────────────────────

BSLASH_PCT_RE = re.compile(r'\\%')


def fix_a5(text):
    if not text or '\\%' not in text:
        return text
    masked, spans = _mask(text)
    fixed = BSLASH_PCT_RE.sub('%', masked)
    return text if fixed == masked else _unmask(fixed, spans)


# ── A6 ───────────────────────────────────────────────────────────────────────
# Порядок важен: сначала --- (LaTeX em-dash), потом --
# Числовые диапазоны и URL-контекст не трогаем.

TRIPLE_DASH_RE = re.compile(r'(?<!\d)---(?!\d)')   # только не-числовые
DOUBLE_DASH_RE = re.compile(r'(?<!\d)--(?!\d)')
URL_CTX_RE     = re.compile(r'(?:://|www\.)')


def _replace_dashes(masked, dash_re):
    """Заменяет вхождения dash_re на — , пропуская URL-контекст."""
    result = []
    pos = 0
    for m in dash_re.finditer(masked):
        lo = max(0, m.start() - 60)
        hi = min(len(masked), m.end() + 60)
        if URL_CTX_RE.search(masked[lo:hi]):
            result.append(masked[pos:m.end()])     # URL — не трогаем
        else:
            result.append(masked[pos:m.start()])
            result.append('—')
        pos = m.end()
    result.append(masked[pos:])
    return ''.join(result)


def fix_a6(text):
    if not text or '--' not in text:
        return text
    masked, spans = _mask(text)
    if '--' not in masked:
        return text
    # Сначала --- → —, потом -- → —
    fixed = _replace_dashes(masked, TRIPLE_DASH_RE)
    fixed = _replace_dashes(fixed,  DOUBLE_DASH_RE)
    return text if fixed == masked else _unmask(fixed, spans)


# ── применение ───────────────────────────────────────────────────────────────

FIELDS = ('statement', 'solution', 'answer')


def _fix_obj(obj, do_a5, do_a6):
    """Изменяет поля объекта на месте. Возвращает список изменённых полей."""
    changed = []
    for f in FIELDS:
        old = getattr(obj, f) or ''
        v = old
        if do_a5:
            v = fix_a5(v)
        if do_a6:
            v = fix_a6(v)
        if v != old:
            setattr(obj, f, v)
            changed.append(f)
    return changed


# ── вспомогательные утилиты ──────────────────────────────────────────────────

def _append_ids(ids):
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE) as f:
            existing = {int(l.strip()) for l in f if l.strip().isdigit()}
    with open(CHANGED_IDS_FILE, 'w') as f:
        for i in sorted(existing | set(ids)):
            f.write(f'{i}\n')


# ── команда ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Исправление A5 (\\%) и A6 (--) вне математики'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False,
                            help='Боевой прогон по всей базе')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=20,
                            help='Число примеров в dry-run')
        parser.add_argument('--only-a5', action='store_true', default=False)
        parser.add_argument('--only-a6', action='store_true', default=False)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        dry_run   = options['dry_run']
        do_all    = options['all']
        source_id = options['source_id']
        n_ex      = options['examples']
        do_a5     = not options['only_a6']
        do_a6     = not options['only_a5']

        if not dry_run and not do_all and not source_id:
            self.stderr.write(
                'Укажи --all для боевого прогона или --dry-run для предпросмотра.'
            )
            return

        qs = (
            Problem.objects
            .filter(status='published', needs_quality_review=False)
            .prefetch_related('parts', 'source_references')
            .order_by('id')
        )
        if source_id:
            qs = qs.filter(
                source_references__source_id=source_id
            ).distinct()

        total       = 0
        changed_ids = []
        a5_hits     = 0
        a6_hits     = 0
        ex_a5       = []   # (id, field, before, after)
        ex_a6       = []

        for problem in qs.iterator(chunk_size=400):
            total += 1
            parts = list(problem.parts.all())

            problem_a5 = False
            problem_a6 = False
            problem_changed = []

            # Собираем примеры
            for f in FIELDS:
                old = getattr(problem, f) or ''
                if do_a5 and len(ex_a5) < n_ex:
                    nv = fix_a5(old)
                    if nv != old:
                        ex_a5.append((problem.id, f, old[:120].replace('\n', ' '),
                                      nv[:120].replace('\n', ' ')))
                if do_a6 and len(ex_a6) < n_ex:
                    nv = fix_a6(old)
                    if nv != old:
                        ex_a6.append((problem.id, f, old[:120].replace('\n', ' '),
                                      nv[:120].replace('\n', ' ')))
            for part in parts:
                for f in FIELDS:
                    old = getattr(part, f) or ''
                    if do_a5 and len(ex_a5) < n_ex:
                        nv = fix_a5(old)
                        if nv != old:
                            ex_a5.append((problem.id, f'part.{f}',
                                          old[:120].replace('\n', ' '),
                                          nv[:120].replace('\n', ' ')))
                    if do_a6 and len(ex_a6) < n_ex:
                        nv = fix_a6(old)
                        if nv != old:
                            ex_a6.append((problem.id, f'part.{f}',
                                          old[:120].replace('\n', ' '),
                                          nv[:120].replace('\n', ' ')))

            # Проверяем, будут ли изменения
            for f in FIELDS:
                old = getattr(problem, f) or ''
                if do_a5 and fix_a5(old) != old:
                    problem_a5 = True
                if do_a6 and fix_a6(old) != old:
                    problem_a6 = True
            for part in parts:
                for f in FIELDS:
                    old = getattr(part, f) or ''
                    if do_a5 and fix_a5(old) != old:
                        problem_a5 = True
                    if do_a6 and fix_a6(old) != old:
                        problem_a6 = True

            if problem_a5:
                a5_hits += 1
            if problem_a6:
                a6_hits += 1
            if problem_a5 or problem_a6:
                changed_ids.append(problem.id)

            if dry_run:
                continue

            # ── боевое исправление ──────────────────────────────────────────
            problem_changed = _fix_obj(problem, do_a5, do_a6)
            if problem_changed:
                problem.save(update_fields=problem_changed)

            for part in parts:
                part_changed = _fix_obj(part, do_a5, do_a6)
                if part_changed:
                    part.save(update_fields=part_changed)

            if total % 5000 == 0:
                self.stdout.write(f'  ...{total} задач обработано')

        # ── dry-run: вывод примеров ──────────────────────────────────────────
        if dry_run:
            self.stdout.write('')
            self.stdout.write(
                f'=== DRY-RUN A5 (\\% → %): затронет {a5_hits} задач ==='
            )
            for pid, f, before, after in ex_a5:
                self.stdout.write(f'  #{pid} [{f}]')
                self.stdout.write(f'    ДО:    {before}')
                self.stdout.write(f'    ПОСЛЕ: {after}')
            self.stdout.write('')
            self.stdout.write(
                f'=== DRY-RUN A6 (-- → —): затронет {a6_hits} задач ==='
            )
            for pid, f, before, after in ex_a6:
                self.stdout.write(f'  #{pid} [{f}]')
                self.stdout.write(f'    ДО:    {before}')
                self.stdout.write(f'    ПОСЛЕ: {after}')
            self.stdout.write('')
            self.stdout.write(
                f'Итого: A5={a5_hits}, A6={a6_hits}, '
                f'уникальных задач: {len(changed_ids)}'
            )
            return

        # ── боевой: сохраняем id ─────────────────────────────────────────────
        _append_ids(changed_ids)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: A5={a5_hits}, A6={a6_hits}, '
            f'уникальных задач: {len(changed_ids)}'
        ))
