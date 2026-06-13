"""
fix_title_authors.py — сессия H, этап 3c.

Чистка хвостов «% Имя Фамилия» в Problem.title (артефакт LaTeX-комментариев
авторства из МатЭк/Archive 3). Улика: #32464 «Монополия % Николаев Андрей
(задачи посложнее)».

Правило: режем от « %»/«%» до конца title, ТОЛЬКО если сразу после %
(и необязательных пробелов) идут >= 2 кириллических слова с заглавной буквы
(«Имя Фамилия»). Так защищены «%∆Q», «4 %», «100% слов» и т.п.

Дополнительно: если ПЕРВАЯ строка statement посимвольно совпадает со старым
title — она заменяется на очищенный title.

Guard: title после правки не короче 3 символов и % не в нулевой позиции.

Запуск:
    ./venv/bin/python manage.py fix_title_authors --dry-run            # полный список
    ./venv/bin/python manage.py fix_title_authors --all
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/sessionH'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_H.txt')
CANDIDATES_FILE = os.path.join(REPORT_DIR, '03c_title_candidates.txt')

TITLE_PCT_RE = re.compile(r'\s*%\s*(?=[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)')


def clean_title(title):
    """Возвращает очищенный title или исходный, если правка не нужна/опасна."""
    if not title or '%' not in title:
        return title
    m = TITLE_PCT_RE.search(title)
    if not m or m.start() == 0:
        return title
    new = title[:m.start()].rstrip()
    if len(new) < 3:
        return title
    return new


def _append_ids(ids):
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE) as f:
            existing = {int(l.strip()) for l in f if l.strip().isdigit()}
    with open(CHANGED_IDS_FILE, 'w') as f:
        for i in sorted(existing | set(ids)):
            f.write(f'{i}\n')


class Command(BaseCommand):
    help = 'Чистка «% Имя Фамилия» в заголовках (и дублирующей первой строке statement)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False)
        parser.add_argument('--source-id', type=int, default=None)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        dry_run = options['dry_run'] or not options['all']

        qs = Problem.objects.exclude(title='').order_by('id')
        if options['source_id']:
            qs = qs.filter(source_references__source_id=options['source_id'])

        changed_ids = []
        n_stmt = 0
        lines = []
        for p in qs.only('id', 'title', 'statement').iterator(chunk_size=1000):
            old_title = p.title
            new_title = clean_title(old_title)
            if new_title == old_title:
                continue
            stmt = p.statement or ''
            stmt_changed = False
            nl = stmt.find('\n')
            first = stmt[:nl] if nl != -1 else stmt
            if first.strip() == old_title.strip():
                stmt = new_title + stmt[len(first):]
                stmt_changed = True
                n_stmt += 1
            lines.append(f'#{p.id}: {old_title!r} -> {new_title!r}'
                         + (' [+1я строка statement]' if stmt_changed else ''))
            if not dry_run:
                p.title = new_title
                if stmt_changed:
                    p.statement = stmt
                p.save(update_fields=['title', 'statement'])
            changed_ids.append(p.id)

        with open(CANDIDATES_FILE, 'w') as f:
            f.write('\n'.join(lines) + ('\n' if lines else ''))
        for ln in lines[:20]:
            self.stdout.write(ln)
        if len(lines) > 20:
            self.stdout.write(f'... и ещё {len(lines) - 20} (полный список: {CANDIDATES_FILE})')

        mode = 'DRY-RUN' if dry_run else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: титулов {len(changed_ids)}, '
            f'из них с заменой первой строки statement {n_stmt}'))
        if not dry_run and changed_ids:
            _append_ids(changed_ids)
