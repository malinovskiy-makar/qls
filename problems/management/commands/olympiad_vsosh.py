# -*- coding: utf-8 -*-
"""ВсОШ по экономике: сбор, подготовка и оцифровка (ночь P3, 28.10.2026).

В базу НЕ пишет ничего (банк только читается подкомандой `bank`). Все
файлы — в `weconomics-data\\olympiads\\vsosh_20261028\\` (`--root`).

Подкоманды по порядку конвейера:
  manifest   — work\\jobs_*/results_* → manifest.jsonl + coverage.md (архивы раскрываются);
  convert    — список .doc/.docx/.rtf → PDF для Word (p3_tools\\word2pdf.ps1);
  render     — страницы главных копий → digitized\\v1\\pages\\<sha16>\\p<N>.png/.txt;
  events     — пары «задания ↔ решения» → digitized\\v1\\events_files.jsonl, events_meta.jsonl;
  plan       — страницы и деньги по группам → digitized\\v1\\PLAN.md.
Оцифровка, сборка, проверки и сверка с банком — подкоманды `transcribe`,
`assemble`, `check`, `review`, `bank` (модуль vsosh_digitize).
"""
from __future__ import annotations

import json
import os
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from problems.olympiad_audit import digitize, vsosh_coverage, vsosh_manifest, vsosh_prepare

DEFAULT_ROOT = r'C:\Users\shipu\weconomics-data\olympiads\vsosh_20261028'
RUNS = ('cpm', 'ile', 'olimpiada', 'olimpiada_fix', 'edsoo', 'rosolymp', 'regions')


class Command(BaseCommand):
    help = 'ВсОШ по экономике: манифест, подготовка и оцифровка (в базу не пишет).'

    def add_arguments(self, parser):
        parser.add_argument('step', choices=['manifest', 'convert', 'render', 'events', 'plan',
                                             'transcribe', 'batches', 'claude', 'assemble',
                                             'ile', 'check', 'review', 'bank', 'q2'])
        parser.add_argument('--action', default='collect',
                            help='claude: submit/collect; q2: шаг сессии Q2 (vsosh_q2)')
        parser.add_argument('--models', default=None, help='q2: модели через запятую')
        parser.add_argument('--round', default='1', help='q2 keys: 1 — основной проход, 2 — все страницы файлов ответов')
        parser.add_argument('--root', default=DEFAULT_ROOT)
        parser.add_argument('--groups', default='1,2,3,4,5', help='группы плана (transcribe)')
        parser.add_argument('--max-usd', type=float, default=None)
        parser.add_argument('--yes', action='store_true', help='разрешить платные вызовы')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--workers', type=int, default=12)
        parser.add_argument('--pages-file', default=None, help='только эти страницы (sha16/pN)')
        parser.add_argument('--thinking-off', action='store_true',
                            help='batches: Claude без рассуждения (Sonnet — between_tools, Haiku — disabled)')

    # ── пути ────────────────────────────────────────────────────────────
    def _paths(self, root):
        self.root = root
        self.work = os.path.join(root, 'work')
        self.digitized = os.path.join(root, 'digitized', 'v1')
        os.makedirs(self.digitized, exist_ok=True)

    def _say(self, text):
        self.stdout.write(text)

    def handle(self, *args, **opts):
        self._paths(opts['root'])
        step = opts['step']
        if step == 'q2':
            from problems.olympiad_audit import vsosh_q2
            vsosh_q2.run(self, opts)
            return None
        if step in ('transcribe', 'batches', 'claude', 'assemble', 'ile', 'check', 'review',
                    'bank'):
            from problems.olympiad_audit import vsosh_digitize
            return vsosh_digitize.run_step(self, step, opts)
        getattr(self, '_' + step)(opts)

    def _manifest_rows(self):
        path = os.path.join(self.root, 'manifest.jsonl')
        if not os.path.isfile(path):
            raise CommandError('Нет manifest.jsonl — сначала `manifest`.')
        return digitize.read_jsonl(path)

    # ── manifest ────────────────────────────────────────────────────────
    def _manifest(self, opts):
        rows = vsosh_manifest.build(self.root, self.work, RUNS, log=self._say)
        digitize.write_jsonl(os.path.join(self.root, 'manifest.jsonl'), rows)
        inv = vsosh_manifest.invariants(rows)
        with open(os.path.join(self.root, 'coverage.md'), 'w', encoding='utf-8') as fh:
            fh.write(vsosh_coverage.markdown(rows))
        with open(os.path.join(self.root, 'manifest_invariants.json'), 'w', encoding='utf-8') as fh:
            json.dump({'invariants': inv, 'coverage': vsosh_coverage.summary(rows),
                       'by_source': dict(Counter(r['source'].split(':')[0] for r in rows
                                                 if not r.get('from_archive')))},
                      fh, ensure_ascii=False, indent=1)
        self._say(json.dumps(inv, ensure_ascii=False))
        if not inv['balanced']:
            raise CommandError('Инвариант манифеста не сошёлся: ссылки ≠ скачано + не скачалось.')

    # ── convert ─────────────────────────────────────────────────────────
    def _convert(self, opts):
        targets, _ex = vsosh_prepare.digitize_targets(self._manifest_rows())
        pairs = vsosh_prepare.conversion_list(self.root, targets)
        path = os.path.join(self.work, 'word2pdf.tsv')
        with open(path, 'w', encoding='utf-8') as fh:
            for src, dst in pairs:
                fh.write(f'{src}\t{dst}\n')
        self._say(f'к конвертации Word: {len(pairs)} → {path}')

    # ── render ──────────────────────────────────────────────────────────
    def _render(self, opts):
        targets, excluded = vsosh_prepare.digitize_targets(self._manifest_rows())
        counts = vsosh_prepare.render_all(self.root, targets, self.digitized, log=self._say)
        # Персональные данные (протоколы, списки) — из целей вон, до модели.
        personal = []
        for r in targets:
            text = vsosh_prepare.first_page_text(
                os.path.join(self.digitized, digitize.page_dir_for(r['sha256'])))
            if digitize.personal_data_hit(r.get('path', ''), text):
                personal.append(r['sha256'])
        rows = []
        for r in targets:
            rows.append({'sha256': r['sha256'], 'path': r['path'], 'url': r['url'],
                         'pages': counts.get(r['sha256'], 0),
                         'page_dir': digitize.page_dir_for(r['sha256']),
                         'pdf': os.path.relpath(vsosh_prepare.pdf_path_for(self.root, r),
                                                self.root).replace('\\', '/'),
                         'personal': r['sha256'] in personal,
                         'not_rendered': counts.get(r['sha256'], 0) == 0})
        digitize.write_jsonl(os.path.join(self.digitized, 'render_index.jsonl'), rows)
        self._say(f'целей {len(targets)}, исключено {len(excluded)}; страниц '
                  f'{sum(counts.values())}; не отрисовано файлов '
                  f'{sum(1 for r in rows if r["not_rendered"])}; персональные {len(personal)}')
        digitize.write_jsonl(os.path.join(self.digitized, 'excluded.jsonl'), excluded)

    # ── events ──────────────────────────────────────────────────────────
    def _events(self, opts):
        index = {r['sha256']: r for r in digitize.read_jsonl(
            os.path.join(self.digitized, 'render_index.jsonl'))}
        targets, _ex = vsosh_prepare.digitize_targets(self._manifest_rows())
        targets = [t for t in targets if t['sha256'] in index
                   and not index[t['sha256']]['personal'] and index[t['sha256']]['pages']]
        events, orphans = vsosh_prepare.build_events(targets)
        files_rows, meta_rows = [], []
        for eid, ev in sorted(events.items()):
            def entry(f):
                ix = index[f['sha256']]
                return {'file': ix['pdf'], 'orig': f['path'], 'url': f['url'],
                        'sha256': f['sha256'], 'kind': vsosh_prepare.role_of(f['kind']),
                        'source_kind': f['kind'], 'source': f['source'],
                        'page_dir': ix['page_dir'], 'pages': ix['pages'],
                        'text_layer': bool(f.get('text_layer')), 'grades': f.get('grades', ''),
                        'tour': f.get('tour', '')}
            files_rows.append({'event_id': eid, 'new': True,
                               'task_files': [entry(f) for f in ev['task_files']],
                               'solution_files': [entry(f) for f in ev['solution_files']],
                               'criteria_files': [entry(f) for f in ev['criteria_files']]})
            meta = {k: v for k, v in ev.items()
                    if k not in ('task_files', 'solution_files', 'criteria_files')}
            meta['group'] = vsosh_prepare.group_of(
                {'subject': ev['task_files'][0].get('subject', 'econ'), 'stage': ev['stage'],
                 'region_code': ev['region_code']})
            meta_rows.append(meta)
        digitize.write_jsonl(os.path.join(self.digitized, 'events_files.jsonl'), files_rows)
        digitize.write_jsonl(os.path.join(self.digitized, 'events_meta.jsonl'), meta_rows)
        digitize.write_jsonl(os.path.join(self.digitized, 'orphan_solutions.jsonl'), orphans)
        flags = Counter(f for m in meta_rows for f in m['flags'])
        self._say(f'комплектов {len(events)}; решений без пары {len(orphans)}; флаги {dict(flags)}')

    # ── plan ────────────────────────────────────────────────────────────
    def _plan(self, opts):
        index = {r['sha256']: r['pages'] for r in digitize.read_jsonl(
            os.path.join(self.digitized, 'render_index.jsonl'))}
        files = {e['event_id']: e for e in digitize.read_jsonl(
            os.path.join(self.digitized, 'events_files.jsonl'))}
        meta = digitize.read_jsonl(os.path.join(self.digitized, 'events_meta.jsonl'))
        events = {}
        for m in meta:
            f = files[m['event_id']]
            events[m['event_id']] = dict(m, task_files=f['task_files'],
                                         solution_files=f['solution_files'],
                                         criteria_files=f['criteria_files'])
        from problems.olympiad_audit.vsosh_digitize import CLAUDE_PAGE_USD
        res = vsosh_prepare.plan(events, index, sonnet_usd=CLAUDE_PAGE_USD['claude-sonnet-5-5'],
                                 haiku_usd=CLAUDE_PAGE_USD['claude-haiku-5-5'])
        lines = ['# План оцифровки ВсОШ v1', '',
                 '| группа | комплектов | файлов | страниц | Flash, $ | Sonnet Batches, $ | Haiku Batches, $ |',
                 '|---|---|---|---|---|---|---|']
        for g, r in res.items():
            lines.append(f"| {g}. {r['name']} | {r.get('events', 0)} | {r.get('files', 0)} | "
                         f"{r.get('pages', 0)} | {r['flash_usd']} | {r.get('sonnet_batch_usd', '')} | "
                         f"{r.get('haiku_batch_usd', '')} |")
        total = sum(r.get('pages', 0) for r in res.values())
        lines += ['', f'Всего страниц в плане: {total} (уникальных файлов: '
                  f'{sum(r.get("files", 0) for r in res.values())}).', '']
        with open(os.path.join(self.digitized, 'PLAN.md'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
        with open(os.path.join(self.digitized, 'plan.json'), 'w', encoding='utf-8') as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        self._say('\n'.join(lines))
