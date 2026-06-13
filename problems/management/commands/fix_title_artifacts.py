"""
fix_title_artifacts.py — исправление A9, A10 и \footnote в заголовках.

A9:  title начинается с [N] или [NN] → убрать префикс и пробел.
     «[5] Задача о монополии» → «Задача о монополии»

A10: title начинается с YYYY) → убрать префикс.
     «2024) Задача о спросе» → «Задача о спросе»

FN:  title начинается с \\footnote{...} (brace-balanced) → убрать весь блок.
     «\\footnote{автор} Условие» → «Условие»

Инвариант: ни один title не должен стать пустым или короче 3 символов.
Если после правки title < 3 символов → пропустить задачу (только dry-run предупреждение).

Запуск:
    ./venv/bin/python manage.py fix_title_artifacts --dry-run --examples 15
    ./venv/bin/python manage.py fix_title_artifacts --all
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/quality_audit'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_F.txt')

# ── регулярки ────────────────────────────────────────────────────────────────

# A9: [N] или [NN] в начале title
A9_RE = re.compile(r'^\s*\[(\d{1,2})\]\s*')

# A10: YYYY) в начале title
A10_RE = re.compile(r'^\s*\d{4}\)\s*')


def _extract_footnote(text):
    """
    Если text начинается с \\footnote{...} (brace-balanced),
    возвращает (len_to_skip, inner_text).
    Иначе возвращает (0, '').
    """
    m = re.match(r'^\\footnote\{', text)
    if not m:
        return 0, ''
    depth = 1
    i = m.end()
    while i < len(text) and depth > 0:
        c = text[i]
        if c == '{' and (i == 0 or text[i-1] != '\\'):
            depth += 1
        elif c == '}' and (i == 0 or text[i-1] != '\\'):
            depth -= 1
        i += 1
    if depth != 0:
        return 0, ''   # несбалансировано — не трогаем
    inner = text[m.end():i-1].strip()
    skip  = i
    return skip, inner


def fix_title(title):
    """
    Применяет A9, A10 и FN-очистку к заголовку.
    Возвращает новый title или исходный если ничего не изменилось.
    """
    if not title:
        return title

    t = title.strip()

    # FN: \footnote{...} в начале
    skip, inner = _extract_footnote(t)
    if skip > 0:
        t = t[skip:].strip()

    # A9: [N] / [NN] в начале
    m = A9_RE.match(t)
    if m:
        t = t[m.end():].strip()

    # A10: YYYY) в начале
    m = A10_RE.match(t)
    if m:
        t = t[m.end():].strip()

    return t if t != title.strip() else title


# ── вспомогательные ──────────────────────────────────────────────────────────

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
    help = 'Исправление A9/A10/FN — артефакты в заголовках (только чтение без --all)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False,
                            help='Боевой прогон')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=15)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        dry_run   = options['dry_run']
        do_all    = options['all']
        source_id = options['source_id']
        n_ex      = options['examples']

        if not dry_run and not do_all and not source_id:
            self.stderr.write(
                'Укажи --all для боевого прогона или --dry-run для предпросмотра.'
            )
            return

        qs = (
            Problem.objects
            .filter(status='published', needs_quality_review=False)
            .only('id', 'title')
            .order_by('id')
        )
        if source_id:
            qs = qs.filter(
                source_references__source_id=source_id
            ).distinct()

        total       = 0
        changed_ids = []
        a9_count    = 0
        a10_count   = 0
        fn_count    = 0
        skip_short  = []   # задачи, у которых после правки title < 3 симв.
        examples    = []   # (id, before, after)

        for problem in qs.iterator(chunk_size=400):
            total += 1
            old_title = problem.title or ''
            if not old_title:
                continue

            # Проверяем что именно сработает
            a9_hit  = bool(A9_RE.match(old_title.strip()))
            a10_hit = bool(A10_RE.match(old_title.strip()))
            fn_skip, _ = _extract_footnote(old_title.strip())
            fn_hit  = fn_skip > 0

            new_title = fix_title(old_title)

            if new_title == old_title:
                continue

            # Инвариант: не делаем title пустым или коротким
            if len(new_title.strip()) < 3:
                skip_short.append((problem.id, old_title, new_title))
                continue

            if a9_hit:
                a9_count += 1
            if a10_hit:
                a10_count += 1
            if fn_hit:
                fn_count += 1

            changed_ids.append(problem.id)

            if len(examples) < n_ex:
                tag = ('A9' if a9_hit else '') + ('A10' if a10_hit else '') + ('FN' if fn_hit else '')
                examples.append((problem.id, tag, old_title[:100], new_title[:100]))

            if dry_run:
                continue

            # Боевое изменение
            problem.title = new_title
            problem.save(update_fields=['title'])

            if total % 5000 == 0:
                self.stdout.write(f'  ...{total} задач обработано')

        # ── dry-run вывод ────────────────────────────────────────────────────
        if dry_run:
            self.stdout.write('')
            self.stdout.write(
                f'=== DRY-RUN: A9={a9_count}, A10={a10_count}, FN={fn_count} ==='
            )
            self.stdout.write(f'Всего изменится: {len(changed_ids)} задач')
            self.stdout.write('')
            for pid, tag, before, after in examples:
                self.stdout.write(f'  #{pid} [{tag}]')
                self.stdout.write(f'    ДО:    {before}')
                self.stdout.write(f'    ПОСЛЕ: {after}')
            if skip_short:
                self.stdout.write('')
                self.stdout.write(f'ПРОПУЩЕНО (title < 3 после правки): {len(skip_short)}')
                for pid, old, new in skip_short[:5]:
                    self.stdout.write(f'  #{pid}: «{old[:80]}» → «{new}»')
            return

        # ── боевой: сохраняем id ─────────────────────────────────────────────
        _append_ids(changed_ids)
        if skip_short:
            self.stdout.write(
                self.style.WARNING(
                    f'Пропущено (title стал < 3 симв.): {len(skip_short)}'
                )
            )
        self.stdout.write(self.style.SUCCESS(
            f'Готово: A9={a9_count}, A10={a10_count}, FN={fn_count}, '
            f'изменено задач: {len(changed_ids)}'
        ))
