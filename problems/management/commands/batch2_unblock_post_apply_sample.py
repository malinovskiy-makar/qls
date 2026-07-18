# -*- coding: utf-8 -*-
"""
Пост-контроль ПРИМЕНЁННОЙ разблокировки группы Б: все реально изменённые
задачи ДО (JSON-бэкап применения) / ПОСЛЕ (текущее состояние базы), тем
же карточным форматом, что preview.html (problems.management.commands
.preview_batch2_unblock.diff_block/preview_head).

Запуск:
    ./venv/bin/python manage.py batch2_unblock_post_apply_sample \\
        --backup reports/batch2_unblock/backup_apply_20260719.json
"""
import html
import json
import os

from django.core.management.base import BaseCommand, CommandError

from problems.management.commands.glue_pdf_lines import _PREVIEW_TAIL, preview_head
from problems.management.commands.preview_batch2_unblock import diff_block
from problems.models import Problem

OUT_DIR = 'reports/batch2_unblock'
IDS_PATH = os.path.join(OUT_DIR, 'affected_problem_ids.txt')
DEFAULT_OUT = os.path.join(OUT_DIR, 'post_apply_sample.html')

CATEGORY_TITLES = [
    ('conflict_solution', 'Конфликт решения — применено'),
    ('unknown_label', 'Неизвестная метка подпункта — применено'),
]


def _load_ids(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [int(x.strip()) for x in f if x.strip()]


class Command(BaseCommand):
    help = ('Пост-контроль применённой разблокировки группы Б: все '
            'применённые задачи ДО (бэкап) / ПОСЛЕ (база).')

    def add_arguments(self, parser):
        parser.add_argument('--backup', required=True)
        parser.add_argument('--out', default=DEFAULT_OUT)

    def handle(self, *args, **opts):
        backup_path = opts['backup']
        if not os.path.exists(backup_path):
            raise CommandError('Бэкап не найден: {}'.format(backup_path))
        with open(backup_path, encoding='utf-8') as f:
            backup = json.load(f)

        affected_ids = set(_load_ids(IDS_PATH))
        if not affected_ids:
            raise CommandError('{} пуст или не найден.'.format(IDS_PATH))

        problems = {
            p.pk: p for p in
            Problem.objects.filter(pk__in=list(affected_ids)).prefetch_related('parts')
        }

        mismatches = []
        cards_by_cat = {'conflict_solution': [], 'unknown_label': []}
        seen = set()

        for key, fname in (('conflict_solution', 'to_apply_conflict_solution.txt'),
                           ('unknown_label', 'to_apply_unknown_label.txt')):
            ids = _load_ids(os.path.join(OUT_DIR, fname))
            number = 0
            for pid in ids:
                if pid not in affected_ids or pid in seen:
                    continue  # исключён фильтром палочек или уже показан
                seen.add(pid)
                number += 1
                problem = problems.get(pid)
                if problem is None:
                    mismatches.append('#{} not found in db'.format(pid))
                    continue
                cards_by_cat[key].append(
                    self._render_card(number, pid, problem, backup, mismatches))

        if mismatches:
            self.stdout.write(self.style.WARNING(
                '{} несоответствий: {}'.format(len(mismatches), mismatches[:10])))
        else:
            self.stdout.write('Все {} применённых задач найдены и отрисованы.'.format(
                len(affected_ids)))

        head = preview_head(
            'Разблокировка группы Б — пост-контроль (применено)',
            'Разблокировка группы Б — пост-контроль (применено)',
            'Слева — как текст хранился ДО применения (JSON-бэкап), справа — как он '
            'хранится в базе СЕЙЧАС. Изменения уже записаны в базу.')
        out = [head]
        for key, title in CATEGORY_TITLES:
            out.append('<h2 class="section">{} ({} шт.)</h2>'.format(
                html.escape(title), len(cards_by_cat[key])))
            out.append('\n'.join(cards_by_cat[key]) or '<p><em>Пусто.</em></p>')
        out.append(_PREVIEW_TAIL)

        out_path = opts['out']
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
        self.stdout.write('Пост-контроль → {} ({} задач)'.format(
            out_path, len(seen)))

    @staticmethod
    def _render_card(number, pid, problem, backup, mismatches):
        esc = html.escape
        title = esc(problem.title or '')
        rows = []

        old_stmt = backup['problems'].get(str(pid))
        if old_stmt is not None:
            new_stmt = problem.statement or ''
            if old_stmt == new_stmt:
                mismatches.append('#{} statement unchanged'.format(pid))
            rows.append(diff_block('Условие', old_stmt, new_stmt))

        by_pk = {p.pk: p for p in problem.parts.all()}
        for pk_str, old_text in backup['parts'].items():
            pk = int(pk_str)
            part = by_pk.get(pk)
            if part is None:
                continue
            if part.statement == old_text:
                mismatches.append('#{} part:{} unchanged'.format(pid, part.label))
            rows.append(diff_block(
                'Подп. [{}] (pk={})'.format(esc(part.label), pk),
                old_text, part.statement or ''))

        rows_html = '\n'.join(rows)
        return (
            '<div class="card">'
            '<div class="meta"><b>№{num}</b> <b>#{pid}</b> — {title} — '
            '<a href="http://127.0.0.1:8000/catalog/problem/{pid}/" target="_blank">'
            'открыть в каталоге</a></div>'
            '{rows}'
            '</div>'
        ).format(num=number, pid=pid, title=title, rows=rows_html)
