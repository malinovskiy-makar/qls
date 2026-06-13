"""
fix_hyphen_breaks.py — сессия H, этап 3d.

Склейка дефисных переносов из PDF: «на-\\nселения» → «населения».
Улики: #6926 (src #6), #47557/#47590 (src #19); census: #6 — 995, #19 — 275,
#5 — 206 вхождений.

ТОЛЬКО русские PDF-источники (по умолчанию 5, 6, 19):
  - англоязычные источники (#7/#8/#18/#21/#22) пропущены: «short-\\nrun» —
    легитимный компаунд, склейка без дефиса исказила бы слово;
  - LaTeX-источники (#13/#14) пропущены: перенос там может быть честным
    переносом строки исходника внутри «кто-\\nнибудь».

Правило: ([а-яё])- ?\\n([а-яё]) → склейка БЕЗ дефиса, КРОМЕ случаев, когда
вторая часть — целое слово из списка компаундов (то, либо, нибудь, таки,
за, под): тогда дефис сохраняется, а перенос убирается («из-\\nза» → «из-за»).

Внутристрочный вариант («на- селения») НЕ реализован — отклонён по риску
(см. отчёт 03_autofixes.md).

Вне математических спанов. Идемпотентна.

Запуск:
    ./venv/bin/python manage.py fix_hyphen_breaks --dry-run --examples 10
    ./venv/bin/python manage.py fix_hyphen_breaks --all
    ./venv/bin/python manage.py fix_hyphen_breaks --all --source-id 19
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.management.commands.fix_text_punctuation import _mask, _unmask

REPORT_DIR = 'reports/sessionH'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_H.txt')

DEFAULT_SOURCES = [5, 6, 19]

# вторая часть строчная — перенос-артефакт PDF; Заглавная — имя собственное
# («Карабаса-\nБарабаса»): дефис сохраняем, убираем только перенос
HYPH_NL_RE = re.compile(r'([а-яё])- ?\n[ \t]*([а-яёА-ЯЁ][а-яё]*)')

# вторая часть — компаунд: дефис сохраняем, перенос убираем
COMPOUND_SECOND = {'то', 'либо', 'нибудь', 'таки', 'за', 'под'}


def _join(m):
    first, second = m.group(1), m.group(2)
    # имя собственное или компаунд: «из-\nза» → «из-за», «Кобба-\nДугласа»
    if second[0].isupper() or second.lower() in COMPOUND_SECOND:
        return f'{first}-{second}'
    return f'{first}{second}'


def fix_field(text):
    if not text or '-' not in text:
        return text
    masked, spans = _mask(text)
    fixed = HYPH_NL_RE.sub(_join, masked)
    if fixed == masked:
        return text
    return _unmask(fixed, spans)


def _append_ids(ids):
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE) as f:
            existing = {int(l.strip()) for l in f if l.strip().isdigit()}
    with open(CHANGED_IDS_FILE, 'w') as f:
        for i in sorted(existing | set(ids)):
            f.write(f'{i}\n')


class Command(BaseCommand):
    help = 'Склейка дефисных переносов PDF («на-\\nселения») в русских PDF-источниках'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False)
        parser.add_argument('--source-id', type=int, default=None,
                            help='Один источник вместо списка по умолчанию (5, 6, 19)')
        parser.add_argument('--examples', type=int, default=10)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        dry_run = options['dry_run'] or not options['all']
        sources = [options['source_id']] if options['source_id'] else DEFAULT_SOURCES

        qs = (Problem.objects
              .filter(source_references__source_id__in=sources)
              .distinct().order_by('id'))

        changed_ids = []
        n_joins = 0
        examples_left = options['examples']

        for p in qs.iterator(chunk_size=500):
            touched = False
            for field in ('statement', 'solution', 'answer'):
                old = getattr(p, field) or ''
                new = fix_field(old)
                if new != old:
                    touched = True
                    masked_old, _ = _mask(old)
                    hits = HYPH_NL_RE.findall(masked_old)
                    n_joins += len(hits)
                    if examples_left > 0:
                        examples_left -= 1
                        m = HYPH_NL_RE.search(masked_old)
                        i = m.start()
                        self.stdout.write(
                            f'--- #{p.id} [{field}], склеек {len(hits)}\n'
                            f'  ДО : {old[max(0, i - 40):i + 40]!r}')
                    if not dry_run:
                        setattr(p, field, new)
            part_changed = False
            for part in p.parts.all():
                for field in ('statement', 'answer'):
                    old = getattr(part, field) or ''
                    new = fix_field(old)
                    if new != old:
                        touched = True
                        part_changed = True
                        masked_old, _ = _mask(old)
                        n_joins += len(HYPH_NL_RE.findall(masked_old))
                        if not dry_run:
                            setattr(part, field, new)
                if part_changed and not dry_run:
                    part.save(update_fields=['statement', 'answer'])
                    part_changed = False
            if touched:
                changed_ids.append(p.id)
                if not dry_run:
                    p.save(update_fields=['statement', 'solution', 'answer'])

        mode = 'DRY-RUN' if dry_run else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: источники {sources}, задач затронуто {len(changed_ids)}, '
            f'склеек {n_joins}'))
        if not dry_run and changed_ids:
            _append_ids(changed_ids)
