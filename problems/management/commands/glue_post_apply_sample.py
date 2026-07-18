# -*- coding: utf-8 -*-
"""
Пост-контроль ПРИМЕНЁННОЙ склейки построчной нарезки (v1): N случайных
задач из числа реально изменённых, ДО (из JSON-бэкапа применения) / ПОСЛЕ
(текущее состояние базы) — тот же HTML-формат карточек, что и dry-run
предпросмотр (glue_pdf_lines --preview), общая шапка/CSS — preview_head().

Заодно проверяет целостность: пересчитывает glue_field(ДО) для каждого
показанного поля и сверяет с ПОСЛЕ из базы — расхождение означает, что
база изменилась после бэкапа (или это не тот бэкап), и попадает в
предупреждение в консоли.

Запуск:
    ./venv/bin/python manage.py glue_post_apply_sample \\
        --backup reports/glue_lines/backup_apply_20260719.json
"""
import json
import os
import random

from django.core.management.base import BaseCommand, CommandError

from problems.management.commands.glue_pdf_lines import (
    REPORT_DIR, glue_field, preview_head, _PREVIEW_TAIL, _preview_card,
)
from problems.models import Problem, Source

IDS_PATH = os.path.join(REPORT_DIR, 'changed_ids.txt')
DEFAULT_OUT = os.path.join(REPORT_DIR, 'post_apply_sample.html')
DEFAULT_SAMPLE = 20


class Command(BaseCommand):
    help = ('Пост-контроль применённой склейки: N случайных задач ДО '
            '(бэкап) / ПОСЛЕ (база) в HTML того же формата, что preview.html.')

    def add_arguments(self, parser):
        parser.add_argument('--backup', required=True,
                            help='Путь к JSON-бэкапу применения '
                                 '(reports/glue_lines/backup_apply_*.json).')
        parser.add_argument('--sample', type=int, default=DEFAULT_SAMPLE,
                            help='Сколько случайных задач показать.')
        parser.add_argument('--seed', type=int, default=2026)
        parser.add_argument('--ids-file', default=IDS_PATH,
                            help='Список id изменённых задач (по умолчанию '
                                 'changed_ids.txt, который пишет --confirm).')
        parser.add_argument('--out', default=DEFAULT_OUT)

    def handle(self, *args, **opts):
        backup_path = opts['backup']
        if not os.path.exists(backup_path):
            raise CommandError('Бэкап не найден: {}'.format(backup_path))
        with open(backup_path, encoding='utf-8') as f:
            backup = json.load(f)

        ids_path = opts['ids_file']
        if not os.path.exists(ids_path):
            raise CommandError('Список изменённых id не найден: {}'.format(ids_path))
        with open(ids_path, encoding='utf-8') as f:
            all_ids = [int(x) for x in f.read().split()]

        rng = random.Random(opts['seed'])
        sample_ids = rng.sample(all_ids, min(opts['sample'], len(all_ids)))

        qs = (Problem.objects.filter(id__in=sample_ids)
              .prefetch_related('parts', 'source_references').order_by('id'))
        source_names = dict(Source.objects.values_list('id', 'name'))

        mismatches = []
        records = []
        for p in qs:
            fields = []
            old_stmt = backup['problems'].get(str(p.id))
            if old_stmt is not None:
                r = glue_field(old_stmt)
                if r.new_text != p.statement:
                    mismatches.append('#{} statement'.format(p.id))
                fields.append(('statement', old_stmt, p.statement, r, None))
            for part in p.parts.all():
                old_part = backup['parts'].get(str(part.id))
                if old_part is None:
                    continue
                r = glue_field(old_part)
                if r.new_text != part.statement:
                    mismatches.append('#{} part:{}'.format(p.id, part.label))
                fields.append(('part:{}'.format(part.label), old_part,
                               part.statement, r, part.id))
            if not fields:
                continue
            ref_sids = [ref.source_id for ref in p.source_references.all()]
            records.append({
                'id': p.id,
                'sid': ref_sids[0] if ref_sids else None,
                'title': p.title or '',
                'fields': fields,
                'glues': sum(rr.changes for _, _, _, rr, _ in fields),
                'borderline': None,
            })

        if mismatches:
            self.stdout.write(self.style.WARNING(
                'ВНИМАНИЕ: {} полей ДО(glue_field)≠ПОСЛЕ(база): {}'.format(
                    len(mismatches), ', '.join(mismatches[:10]))))
        else:
            self.stdout.write('Целостность подтверждена: glue_field(ДО) == '
                              'ПОСЛЕ(база) на всех показанных полях.')

        html = [preview_head(
            'Склейка нарезки — пост-контроль (применено)',
            'Склейка построчной нарезки — пост-контроль (v1 ПРИМЕНЕНА)',
            'Слева — как текст хранился ДО применения (JSON-бэкап), справа — '
            'как он хранится в базе СЕЙЧАС. Изменения уже записаны в базу.')]
        html.append('<h2 class="section">{} случайных применённых задач '
                    '(из {} изменённых)</h2>'.format(len(records), len(all_ids)))
        for rec in records:
            html.append(_preview_card(rec, source_names))
        html.append(_PREVIEW_TAIL)

        with open(opts['out'], 'w', encoding='utf-8') as f:
            f.write('\n'.join(html))
        self.stdout.write('Пост-контроль → {} ({} задач)'.format(
            opts['out'], len(records)))
