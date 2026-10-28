# -*- coding: utf-8 -*-
"""Проверка олимпиадных задач людьми и выборочная приёмка (Q3, 29.10.2026).

    olympiad_review queue                         # очереди → queues\\human_queue.jsonl + сводка
    olympiad_review pack --size 60 --reviewer "Андрей" [--olympiad vp] [--source p2_recheck] [--count 2]
    olympiad_review apply --decisions F [F …] [--include-auto] [--dry-run | --rehearsal | --apply --yes-…]
    olympiad_review apply --rollback <журнал> [--apply --yes-i-have-owner-approval]
    olympiad_review acceptance --olympiad vp --n 100 --seed 20261029 [--reviewers "Андрей,Анич"]
    olympiad_review acceptance-report [--decisions F …]

Папка волны — `--quality-dir` или `OLYMPIAD_QUALITY_DIR`, по умолчанию
`weconomics-data\\quality_20261029`. В базу пишет только `apply` с
`--apply --yes-i-have-owner-approval`; остальное только читает базу.
Подробно — docs/OLYMPIAD_AUDIT.md, раздел «Проверка людьми и приёмка».
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.olympiad_review import common

APPROVAL_FLAG = '--yes-i-have-owner-approval'


class Command(BaseCommand):
    help = 'Проверка олимпиадных задач людьми: очередь, пакеты, применение решений, приёмка.'

    def add_arguments(self, parser):
        parser.add_argument('step', choices=('queue', 'pack', 'apply', 'acceptance',
                                             'acceptance-report'))
        parser.add_argument('--quality-dir')
        # pack
        parser.add_argument('--size', type=int, default=60)
        parser.add_argument('--reviewer')
        parser.add_argument('--olympiad', action='append', default=[])
        parser.add_argument('--source', action='append', default=[])
        parser.add_argument('--count', type=int, default=1, help='сколько пакетов собрать')
        parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'))
        # apply
        parser.add_argument('--decisions', nargs='*', default=[])
        parser.add_argument('--include-auto', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--rehearsal', action='store_true',
                            help='запись на копии базы (REVIEW_DB_PATH) с проверкой повтора и отката')
        parser.add_argument('--rollback', metavar='JOURNAL')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(APPROVAL_FLAG, dest='approved', action='store_true')
        # acceptance
        parser.add_argument('--n', type=int, default=100)
        parser.add_argument('--seed', type=int, default=20261029)
        parser.add_argument('--reviewers', default='Андрей,Анич')

    def handle(self, *args, **o):
        self.o = o
        self.qdir = common.quality_dir(o['quality_dir'])
        step = o['step']
        if step == 'queue':
            return self._queue()
        if step == 'pack':
            return self._pack()
        if step == 'apply':
            return self._apply()
        if step == 'acceptance':
            return self._acceptance()
        return self._acceptance_report()

    # ── queue ───────────────────────────────────────────────────────────

    def _queue(self):
        from problems.olympiad_review import queue, sources
        qdir = self.qdir / 'queues'
        bank, refs = sources.Bank(), {}
        items = []
        p2_paths = sorted(str(p) for p in common.data_root().glob('**/digitized/v*.1/morning_v*.1.jsonl'))
        p2, missing = sources.load_p2(p2_paths, bank=bank, refs=refs)
        items += p2
        items += sources.load_p1(bank=bank, refs=refs)
        loaded = {'p2_recheck': len(p2), 'p1': len(items) - len(p2)}
        for name in ('q1_contour.jsonl', 'q2_vsosh_v2.jsonl', 'acceptance_defects.jsonl'):
            path = qdir / name
            if path.is_file():
                more = sources.load_common(path, bank=bank)
                loaded[name] = len(more)
                items += more
            else:
                loaded[name] = 'нет файла'
        ids = [it['item_id'] for it in items]
        if len(ids) != len(set(ids)):
            dup = [k for k in set(ids) if ids.count(k) > 1][:5]
            raise CommandError(f'Повтор item_id в позициях: {dup}')
        closed = queue.load_closed(qdir / 'closed.jsonl')
        cards, auto, summary = queue.build(items, closed=closed, is_visible=bank.is_visible)
        common.write_jsonl(qdir / 'human_queue.jsonl', cards)
        common.write_jsonl(qdir / 'auto_fixes.jsonl', auto)
        sources.write_missing(qdir / 'missing_tasks.jsonl', missing)
        summary['загружено'] = loaded
        summary['недостающих заданий (missing_tasks.jsonl)'] = len(missing)
        with open(qdir / 'human_queue_summary.json', 'w', encoding='utf-8') as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=1)
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=1))
        self.stdout.write(f'Карточки: {qdir / "human_queue.jsonl"}')

    # ── pack ────────────────────────────────────────────────────────────

    def _pack(self):
        from problems.olympiad_review import pack
        o = self.o
        if not o['reviewer']:
            raise CommandError('--reviewer обязателен ("Андрей" или "Анич").')
        queue_path = self.qdir / 'queues' / 'human_queue.jsonl'
        if not queue_path.is_file():
            raise CommandError(f'Нет очереди {queue_path}: сначала olympiad_review queue')
        cards = common.read_jsonl(queue_path)
        packs_dir = self.qdir / 'packs'
        index_path = packs_dir / 'packs_index.json'
        index = pack.load_index(index_path)
        for _n in range(o['count']):
            chosen = pack.select(cards, index, size=o['size'], olympiads=o['olympiad'],
                                 sources=o['source'])
            if not chosen:
                self.stdout.write('Карточек для нового пакета не осталось.')
                break
            pack_id = pack.next_pack_id(packs_dir, o['date'], o['reviewer'])
            result = pack.build(chosen, packs_dir / pack_id, reviewer=o['reviewer'], pack_id=pack_id)
            for card in chosen:
                index[card['item_id']] = {'pack': pack_id, 'reviewer': o['reviewer'],
                                          'items': card['items']}
            pack.save_index(index_path, index)
            self.stdout.write(f'Пакет {pack_id}: карточек {result["cards"]}, страниц {result["pages"]}, '
                              f'не найдено {len(result["missing"])} → {packs_dir / pack_id / "index.html"}')
            for miss in result['missing'][:10]:
                self.stdout.write(f'  ⚠ {miss}')
            self._selfcheck(packs_dir / pack_id)

    def _selfcheck(self, pack_dir):
        from problems.olympiad_review import pack
        check = pack.selfcheck(pack_dir, screenshot=str(pack_dir / 'selfcheck.png'))
        if check is None:
            self.stdout.write('  Самопроверка: Chrome не найден (PACK_CHECK_CHROME) — пропущена.')
            return
        with open(pack_dir / 'selfcheck.json', 'w', encoding='utf-8') as handle:
            json.dump(check, handle, ensure_ascii=False, indent=1)
        if 'error' in check:
            self.stdout.write(self.style.ERROR(f'  Самопроверка: {check["error"]}'))
            return
        self.stdout.write(f'  Самопроверка (headless Chrome, file://): карточек {check["cards"]}, '
                          f'картинок {check["images"]}, битых {len(check["broken"])}, '
                          f'ошибок KaTeX {len(check["katex_errors"])}')
        for err in check['katex_errors'][:5]:
            self.stdout.write(f'    KaTeX {err["item_id"]} ({err["view"]}): {err["tex"]}')

    # ── apply ───────────────────────────────────────────────────────────

    def _apply(self):
        from django.conf import settings

        from problems.olympiad_review import apply as ap
        from problems.olympiad_review import decisions as dc
        o = self.o
        if o['apply'] and not o['approved']:
            raise CommandError(f'--apply требует {APPROVAL_FLAG}. Ничего не записано.')
        db = str(settings.DATABASES['default']['NAME'])
        real_db = 'qls\\db.sqlite3' in db.replace('/', '\\') and 'weconomics-data' not in db
        if o['rehearsal'] and real_db:
            raise CommandError('--rehearsal только на копии базы (REVIEW_DB_PATH).')
        if o['rollback']:
            return self._apply_rollback(o['rollback'])
        try:
            files_data = dc.load_files(o['decisions'])
        except dc.DecisionError as exc:
            raise CommandError(f'Файлы решений с ошибками формата:\n{exc}') from exc
        files_data = [(p, d) for p, d in files_data if (d.get('mode') or 'review') == 'review']
        chosen, disputes = dc.merge(files_data)
        cards = ap.load_cards(self.qdir, sorted({k[0] for k in chosen}))
        pairs, lost = [], []
        for key, dec in sorted(chosen.items()):
            card = cards.get((key[0], key[1]))
            if card is None:
                lost.append(key)
                continue
            pairs.append((card, dec))
        if lost:
            raise CommandError(f'Решения без карточки в пакете: {lost[:5]}')
        if o['include_auto']:
            pairs += ap.auto_cards(self.qdir / 'queues' / 'auto_fixes.jsonl')
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_dir = self.qdir / 'apply'
        out_dir.mkdir(parents=True, exist_ok=True)
        redirect = out_dir / f'rehearsal_{stamp}_files' if o['rehearsal'] else None
        files = ap.Files(self.qdir, redirect=redirect)
        actions = ap.plan(pairs, files)
        from problems.olympiad_review.sources import Bank
        bank = Bank()
        visible_hidden = sum(1 for a in actions if a['kind'] == 'bank_hide'
                             and a['status_old'] == 'ok' and bank.is_visible(a['problem_id']))
        plan_info = ap.summary(actions)
        plan_info.update({'база': db, 'решений': len(chosen), 'споров': len(disputes),
                          'автоисправлений': sum(1 for _c, d in pairs if d['reviewer'] == ap.AUTO_REVIEWER),
                          'скрывается видимых': visible_hidden})
        w = self.stdout.write
        w(json.dumps(plan_info, ensure_ascii=False, indent=1))
        for a in [a for a in actions if a['kind'] == 'conflict'][:10]:
            w(f'  ⚠ конфликт {a["item_id"]}: {a["why"]}')
        for d in disputes[:10]:
            w(f'  ⚔ спор {d["item_id"]}: ' + ' / '.join(f'{v["reviewer"]}: {v["decision"]}'
                                                       for v in d['versions']))
        plan_path = out_dir / f'plan_{stamp}.json'
        with open(plan_path, 'w', encoding='utf-8') as handle:
            json.dump({'summary': plan_info, 'actions': actions, 'disputes': disputes}, handle,
                      ensure_ascii=False, indent=1, default=str)
        preview = self._preview(actions, out_dir / f'preview_{stamp}.html')
        w(f'План: {plan_path}\nПредпросмотр «было → стало»: {preview}')
        if not (o['rehearsal'] or o['apply']):
            w(self.style.WARNING('СУХОЙ ПРОГОН — в базе и файлах ничего не изменено.'))
            return
        touched = {a['problem_id'] for a in actions if a['kind'] in ('bank_fields', 'bank_hide')}
        before, digest_before = ap.counts(), ap.digest(touched)
        journal_path = out_dir / f'journal_{stamp}{"_rehearsal" if o["rehearsal"] else ""}.json'
        journal = ap.execute(actions, files, journal_path=journal_path)
        after = ap.counts()
        checks = ap.invariants(actions, before, after, visible_hidden)
        checks['скрыто = решений hide/not_a_task'] = (
            after['content_status≠ok'] - before['content_status≠ok']
            == sum(1 for a in actions if a['kind'] == 'bank_hide' and a['status_old'] == 'ok'))
        again = ap.plan(pairs, files)
        repeat = sum(1 for a in again if a['kind'] in ap.WRITE_KINDS)
        checks['повтор даёт 0'] = repeat == 0
        journal.update({'db': db, 'counts_before': before, 'counts_after': after, 'invariants': checks,
                        'plan': str(plan_path), 'decisions': [str(p) for p in o['decisions']],
                        'rehearsal': bool(o['rehearsal'])})
        disputes_n = 0 if o['rehearsal'] else ap.write_disputes(files, disputes, journal['at'])
        journal['disputes_written'] = disputes_n
        ap._save_json(journal_path, journal)
        w(f'Счётчики до:    {json.dumps(before, ensure_ascii=False)}')
        w(f'Счётчики после: {json.dumps(after, ensure_ascii=False)}')
        w(f'Инварианты: {json.dumps(checks, ensure_ascii=False)}')
        w(f'Журнал: {journal_path}')
        if o['rehearsal']:
            back = ap.rollback(journal)
            same = ap.digest(touched) == digest_before and ap.counts() == before
            w(f'Откат репетиции: {back}; снимки совпали: {same}')
            ok = all(checks.values()) and same
            w((self.style.SUCCESS if ok else self.style.ERROR)(
                f'РЕПЕТИЦИЯ {"ОК" if ok else "ПРОВАЛЕНА"} (файлы — в {redirect})'))
            if not ok:
                raise CommandError('Репетиция не прошла.')
            return
        if not all(checks.values()):
            raise CommandError(f'Нарушен инвариант после записи: {checks}. Откат: '
                               f'olympiad_review apply --rollback {journal_path} --apply {APPROVAL_FLAG}')
        w(self.style.SUCCESS(f'ЗАПИСАНО. Откат: olympiad_review apply --rollback {journal_path} '
                             f'--apply {APPROVAL_FLAG}'))

    def _apply_rollback(self, path):
        from problems.olympiad_review import apply as ap
        with open(path, encoding='utf-8') as handle:
            journal = json.load(handle)
        if journal.get('command') != 'olympiad_review apply' or not journal.get('applied'):
            raise CommandError('Это не журнал записи olympiad_review apply.')
        self.stdout.write(f'Откат: задач {len(journal["changes"])}, скрытий {len(journal["hides"])}, '
                          f'файлов {len(journal["files"])}')
        if not self.o['apply']:
            self.stdout.write(self.style.WARNING('СУХОЙ ПРОГОН отката — ничего не изменено.'))
            return
        self.stdout.write(json.dumps(ap.rollback(journal), ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS('Откат выполнен.'))

    def _preview(self, actions, path):
        """HTML «было → стало» по пишущим действиям (правило команд массовой правки)."""
        import html as h

        from problems.olympiad_review.pack import diff_html, parts_text
        rows = []
        for a in actions:
            if a['kind'] == 'bank_fields':
                body = ''.join(
                    f'<p><b>{name}</b></p><pre>' + diff_html(
                        parts_text(ch['old']) if name == 'parts' else ch['old'],
                        parts_text(ch['new']) if name == 'parts' else ch['new']) + '</pre>'
                    for name, ch in a['changes'].items())
            elif a['kind'] == 'bank_hide':
                body = f'<p>content_status: {a["status_old"]} → <b>{a["status_new"]}</b></p>'
            elif a['kind'] == 'override':
                body = '<pre>' + h.escape(json.dumps(a['line'], ensure_ascii=False, indent=1)) + '</pre>'
            elif a['kind'] == 'conflict':
                body = f'<p style="color:#b3261e">конфликт: {h.escape(a["why"])}</p>'
            else:
                continue
            rows.append(f'<section><h3>{h.escape(a["kind"])} · {h.escape(a["item_id"])} · '
                        f'{h.escape(a["decision"])} · {h.escape(a["reviewer"])}</h3>{body}</section>')
        page = ('<!doctype html><meta charset="utf-8"><title>Было → стало</title><style>'
                'body{font:16px system-ui;margin:20px;max-width:1100px} pre{white-space:pre-wrap;'
                'background:#f6f6f6;padding:8px} ins{background:#d8f5dc;text-decoration:none}'
                'del{background:#fde0dd} section{border-bottom:1px solid #ddd;padding:6px 0}</style>'
                f'<h1>Применение решений: {len(rows)} действий</h1>' + ''.join(rows))
        Path(path).write_text(page, encoding='utf-8')
        return path

    # ── acceptance ──────────────────────────────────────────────────────

    def _acceptance(self):
        from problems.olympiad_review import acceptance as acc
        from problems.olympiad_review import pack
        from problems.olympiad_review.sources import Bank
        o = self.o
        slugs = o['olympiad'] or []
        bad = [s for s in slugs if s not in common.ACCEPTANCE_SLUGS]
        if not slugs or bad:
            raise CommandError(f'--olympiad из {", ".join(common.ACCEPTANCE_SLUGS)} (ошибка: {bad})')
        reviewers = [r.strip() for r in o['reviewers'].split(',') if r.strip()]
        packs_dir = self.qdir / 'packs'
        index_path = packs_dir / 'acceptance_index.json'
        index = pack.load_index(index_path)
        bank, references = Bank(), {}
        from catalog.filters import base_queryset
        visible = set(base_queryset('catalog').values_list('id', flat=True))
        for slug in slugs:
            if slug in index:
                self.stdout.write(f'{slug}: выборка уже выдана ({index[slug]["packs"]}) — пропуск.')
                continue
            strata, refs = acc.strata_for(slug, visible)
            pids = acc.stratified_sample(strata, o['n'], o['seed'])
            cards = acc.cards_for(slug, pids, refs, bank, references)
            per_layer = {f'{k[0]} {k[1]}': sum(1 for c in cards if tuple(c['stratum']) == k) for k in strata}
            self.stdout.write(f'{slug}: видимых {sum(len(v) for v in strata.values())}, слоёв {len(strata)}, '
                              f'в выборке {len(cards)}')
            entry = {'seed': o['seed'], 'n': o['n'], 'sample': pids, 'packs': [], 'strata': per_layer}
            for k, reviewer in enumerate(reviewers):
                part = cards[k::len(reviewers)]
                if not part:
                    continue
                pack_id = pack.next_pack_id(packs_dir, o['date'], f'{reviewer}_приёмка-{slug}')
                result = pack.build(part, packs_dir / pack_id, reviewer=reviewer, pack_id=pack_id,
                                    mode='acceptance', note=f'приёмка {slug}, seed {o["seed"]}')
                entry['packs'].append(pack_id)
                self.stdout.write(f'  Пакет {pack_id}: задач {result["cards"]}, страниц {result["pages"]}, '
                                  f'не найдено {len(result["missing"])}')
                self._selfcheck(packs_dir / pack_id)
            index[slug] = entry
            pack.save_index(index_path, index)

    def _acceptance_report(self):
        from problems.olympiad_review import acceptance as acc
        from problems.olympiad_review import apply as ap
        from problems.olympiad_review import decisions as dc
        paths = self.o['decisions'] or sorted(str(p) for p in (self.qdir / 'decisions').glob('*.json'))
        try:
            files_data = dc.load_files(paths)
        except dc.DecisionError as exc:
            raise CommandError(f'Файлы решений с ошибками формата:\n{exc}') from exc
        files_data = [(p, d) for p, d in files_data if d.get('mode') == 'acceptance']
        chosen, _disputes = dc.merge(files_data)
        cards = ap.load_cards(self.qdir, sorted({k[0] for k in chosen}))
        rows = [(cards[(k[0], k[1])], dec) for k, dec in sorted(chosen.items())]
        summary, bad = acc.report(rows)
        items = acc.defect_items(bad)
        common.write_jsonl(self.qdir / 'queues' / 'acceptance_defects.jsonl', items)
        lines = ['# Выборочная приёмка — отчёт', '',
                 f'Файлов решений: {len(files_data)}. Порог: задач с дефектом < 3 на 100.', '',
                 '| Олимпиада | Просмотрено | С дефектом | На 100 | 95 % (Уилсон) | Вердикт |',
                 '|---|---|---|---|---|---|']
        for slug, s in sorted(summary.items()):
            lo, hi = s['интервал 95% (Уилсон), на 100']
            lines.append(f'| {slug} | {s["просмотрено"]} | {s["с дефектом"]} | {s["на 100"]} | '
                         f'{lo}–{hi} | {s["вердикт"]} |')
        lines += ['', 'Дефекты по видам:', '']
        for slug, s in sorted(summary.items()):
            names = ', '.join(f'{common.ACCEPTANCE_DEFECTS[k]} {v}' for k, v in s['дефекты'].items()) or '—'
            lines.append(f'- **{slug}**: {names}')
        lines += ['', f'Задачи с дефектами ({len(items)}) — в очередь людям: queues\\acceptance_defects.jsonl.']
        out = self.qdir / 'acceptance_report.md'
        out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write('\n'.join(lines))
        self.stdout.write(f'Отчёт: {out}')
