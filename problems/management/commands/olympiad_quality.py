# -*- coding: utf-8 -*-
"""Контур качества олимпиадных задач ВП, МОШ, ВсОШ (только чтение).

    olympiad_quality check  --out DIR   стандарт S1–S10: банк + эталонные файлы
                                        → standard_results.jsonl, standard_report.md
    olympiad_quality render --out DIR   проверка отображения (HTML страницы задачи
                                        + браузер) → render_results.jsonl, render_report.md
    olympiad_quality queue  --out DIR   очередь дефектов queues/q1_contour.jsonl
                                        и сводка quality_summary.md

В базу не пишет ничего; запускать с `--settings=config.settings_quality_ro`
(база `mode=ro`). Устройство — `problems/olympiad_contour/`, docs/OLYMPIAD_AUDIT.md,
раздел «Контур качества».
"""
from __future__ import annotations

import os
import time

from django.core.management.base import BaseCommand, CommandError

DEFAULT_OUT = r'C:\Users\shipu\weconomics-data\quality_20261029'


class Command(BaseCommand):
    help = 'Контур качества олимпиадных задач: стандарт, отображение, очередь (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('step', choices=('check', 'render', 'queue'))
        parser.add_argument('--out', default=DEFAULT_OUT)
        parser.add_argument('--data-root', default=None, help='папка olympiads (эталоны)')
        parser.add_argument('--next-ids', default=None, help='next_api_run_ids.txt')
        parser.add_argument('--only', default='', help='bank | ref — только один уровень')
        parser.add_argument('--limit', type=int, default=0, help='первые N задач банка (отладка)')
        parser.add_argument('--ids', default='', help='id задач банка через запятую (отладка)')
        parser.add_argument('--browser', action='store_true', help='render: ещё и Chromium (Playwright)')
        parser.add_argument('--base-url', default='http://127.0.0.1:8765',
                            help='render --browser: адрес runserver с settings_quality_ro')
        parser.add_argument('--contact', type=int, default=200, help='render: задач в контактном листе')

    def handle(self, *args, **opts):
        out = opts['out']
        os.makedirs(out, exist_ok=True)
        started = time.time()
        if opts['step'] == 'check':
            self.run_check(opts)
        elif opts['step'] == 'render':
            from problems.olympiad_contour import render
            render.run(opts, self.stdout)
        else:
            from problems.olympiad_contour import queue
            queue.run(opts, self.stdout)
        self.stdout.write('готово за %.0f с' % (time.time() - started))

    # ── check ──────────────────────────────────────────────────────────
    def run_check(self, opts):
        from problems.olympiad_contour import bank, reference, run

        out = opts['out']
        data_root = opts['data_root'] or reference.DATA_ROOT
        self.stdout.write('эталоны: чтение наборов…')
        sets, ref_cards = reference.load_all(data_root)
        by_key = {c['ref_key']: c for c in ref_cards}
        rejected = {}
        for refset in sets.values():
            rejected.update(refset.rejected)
        suspect = reference.load_suspect()
        rows, extra = [], []
        if opts['only'] != 'ref':
            next_ids = bank.read_ids(opts['next_ids'] or bank.NEXT_API_IDS)
            ids, visible, scope = bank.scope_ids(next_ids)
            if opts['ids']:
                ids = [int(x) for x in opts['ids'].split(',') if x.strip()]
            if opts['limit']:
                ids = ids[:opts['limit']]
            self.stdout.write('банк: %d задач (видимых олимпиадных %d, next_api %d)'
                              % (len(ids), sum('visible' in scope.get(i, ()) for i in ids),
                                 sum('next_api' in scope.get(i, ()) for i in ids)))
            bank_cards = bank.load_cards(ids, visible, by_key, rejected, suspect)
            missing = sorted(set(ids) - {c['problem_id'] for c in bank_cards})
            if missing:
                raise CommandError('задач нет в базе: %s' % missing[:10])
            for card, res in zip(bank_cards, run.check_cards(bank_cards)):
                rows.append(run.result_row(card, res, scope.get(card['problem_id'], ())))
            both = sum(1 for i in ids if scope.get(i) == {'visible', 'next_api'})
            extra += ['Охват банка: видимые задачи с привязкой к ВП/МОШ/ВсОШ (%s) + next_api_run_ids '
                      '(%d id, скрытые тоже); пересечение %d; итого %d задач.'
                      % (', '.join(bank.OLYMPIAD_SLUGS), len(next_ids), both, len(ids))]
        if opts['only'] != 'bank':
            for card, res in zip(ref_cards, run.check_cards(ref_cards)):
                rows.append(run.result_row(card, res))
            extra += ['Эталоны: %s.' % '; '.join('%s %s — %d строк' % (s, r.version, len(r.rows))
                                                 for s, r in sets.items())]
        run.write_jsonl(os.path.join(out, 'standard_results.jsonl'), rows)
        md = run.report_md(rows, 'Стандарт эталонной задачи — отчёт (Q1, %s)' % time.strftime('%d.%m.%Y %H:%M'),
                           extra_lines=extra)
        with open(os.path.join(out, 'standard_report.md'), 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(md)
        self.stdout.write('карточек %d, прошли %d' % (len(rows), sum(r['passed'] for r in rows)))
