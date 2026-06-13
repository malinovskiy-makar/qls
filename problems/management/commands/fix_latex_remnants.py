"""
fix_latex_remnants.py — сессия H, этапы 3a и 3b.

3a: удаление LaTeX-остатков вне математических спанов:
    \\end{document}, \\end {document}, \\begin{document},
    \\documentclass[...]{...}, \\maketitle, \\newpage, \\pagebreak.
    Улика: #4220 — «...отменило квоту.\\n\\n\\end {document}».

3b: \\mbox{X} → X вне мат-спанов (brace-balanced разбор содержимого).
    Улика: #4015 — «\\mbox{и майонез ($y$).}» литералом в тексте.

Поля: Problem.statement/solution/answer, ProblemPart.statement/answer.
Guard: поле не может опустеть после правки (иначе пропуск).
Идемпотентна: повторный прогон не находит кандидатов.

Запуск:
    ./venv/bin/python manage.py fix_latex_remnants --dry-run --examples 10
    ./venv/bin/python manage.py fix_latex_remnants --all
    ./venv/bin/python manage.py fix_latex_remnants --source-id 3 --dry-run
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart
from problems.management.commands.fix_text_punctuation import _mask, _unmask

REPORT_DIR = 'reports/sessionH'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_H.txt')

# ── 3a: LaTeX-остатки ────────────────────────────────────────────────────────

REMNANT_RE = re.compile(
    r'\\documentclass\s*(\[[^\]]*\])?\s*\{[^}]*\}'
    r'|\\(?:begin|end)\s*\{document\}'
    r'|\\maketitle\b'
    r'|\\newpage\b'
    r'|\\pagebreak\b'
)

MBOX_START_RE = re.compile(r'\\mbox\s*\{')

# 3+ пустых строки после вырезания → 2
MULTI_NL_RE = re.compile(r'\n{3,}')


def _unwrap_mbox(text):
    """Заменяет каждый \\mbox{...} на его содержимое (brace-balanced)."""
    out = text
    while True:
        m = MBOX_START_RE.search(out)
        if not m:
            return out
        depth = 1
        i = m.end()
        while i < len(out) and depth > 0:
            c = out[i]
            if c == '{' and out[i - 1] != '\\':
                depth += 1
            elif c == '}' and out[i - 1] != '\\':
                depth -= 1
            i += 1
        if depth != 0:
            # несбалансировано — не трогаем поле дальше
            return out
        inner = out[m.end():i - 1]
        out = out[:m.start()] + inner + out[i:]


def fix_field(text):
    """Возвращает (новый_текст, set_классов) или (text, set()) если без правок."""
    if not text:
        return text, set()
    masked, spans = _mask(text)
    fixed = masked
    classes = set()

    if REMNANT_RE.search(fixed):
        fixed = REMNANT_RE.sub('', fixed)
        classes.add('remnant')

    if MBOX_START_RE.search(fixed):
        new = _unwrap_mbox(fixed)
        if new != fixed:
            fixed = new
            classes.add('mbox')

    if not classes:
        return text, set()

    fixed = MULTI_NL_RE.sub('\n\n', fixed).rstrip()
    result = _unmask(fixed, spans)
    if not result.strip():
        return text, set()        # guard: поле опустело — откат
    return result, classes


def _append_ids(ids):
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE) as f:
            existing = {int(l.strip()) for l in f if l.strip().isdigit()}
    with open(CHANGED_IDS_FILE, 'w') as f:
        for i in sorted(existing | set(ids)):
            f.write(f'{i}\n')


class Command(BaseCommand):
    help = 'Удаление LaTeX-остатков (\\end{document} и др.) и разворачивание \\mbox{}'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False)
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=10)
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        dry_run = options['dry_run'] or not options['all']

        problems = Problem.objects.all().order_by('id')
        if options['source_id']:
            problems = problems.filter(source_references__source_id=options['source_id'])
        if options['limit']:
            problems = problems[:options['limit']]

        changed_ids = []
        examples_left = options['examples']
        n_fields = 0
        class_counter = {}

        for p in problems.iterator(chunk_size=500):
            touched = False
            for field in ('statement', 'solution', 'answer'):
                old = getattr(p, field) or ''
                new, classes = fix_field(old)
                if classes:
                    n_fields += 1
                    touched = True
                    for c in classes:
                        class_counter[c] = class_counter.get(c, 0) + 1
                    if examples_left > 0:
                        examples_left -= 1
                        self.stdout.write(
                            f'--- #{p.id} [{field}] {sorted(classes)}\n'
                            f'  ДО : {old[-160:]!r}\n'
                            f'  ПОС: {new[-160:]!r}')
                    if not dry_run:
                        setattr(p, field, new)
            if touched and not dry_run:
                p.save(update_fields=['statement', 'solution', 'answer'])
            part_touched = False
            for part in p.parts.all():
                for field in ('statement', 'answer'):
                    old = getattr(part, field) or ''
                    new, classes = fix_field(old)
                    if classes:
                        n_fields += 1
                        touched = True
                        part_touched = True
                        for c in classes:
                            class_counter[c] = class_counter.get(c, 0) + 1
                        if examples_left > 0:
                            examples_left -= 1
                            self.stdout.write(
                                f'--- #{p.id} part({part.label}) [{field}] {sorted(classes)}\n'
                                f'  ДО : {old[-160:]!r}\n'
                                f'  ПОС: {new[-160:]!r}')
                        if not dry_run:
                            setattr(part, field, new)
                if not dry_run and part_touched:
                    part.save(update_fields=['statement', 'answer'])
                    part_touched = False
            if touched:
                changed_ids.append(p.id)

        mode = 'DRY-RUN' if dry_run else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: задач затронуто {len(changed_ids)}, полей {n_fields}, '
            f'классы: {class_counter}'))
        if not dry_run and changed_ids:
            _append_ids(changed_ids)
            self.stdout.write(f'ids дописаны в {CHANGED_IDS_FILE}')
