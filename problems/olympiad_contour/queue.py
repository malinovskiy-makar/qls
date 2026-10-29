# -*- coding: utf-8 -*-
"""Очередь дефектов контура (общий формат Q1–Q3) и сводка качества.

Строка очереди — одна проверка одной карточки:

    {"item_id": "q1_contour:<олимпиада>:<ref_key или id>:<проверка>[:auto]",
     "source": "q1_contour", "olympiad", "ref_key", "problem_id",
     "check": "S1..S10 | R* | B*", "details", "page_images": [png страниц PDF],
     "current": {statement, parts, solution, answer, options, key},
     "proposed": {…} или null, "confidence": число или null,
     "auto": bool, "severity": blocker | major | minor, "level": bank | ref,
     "visible": bool | null}

`auto: true` — безопасное автоисправление (`autofix`), `confidence: 1.0`;
людям его не показывают, применяет его сессия проверки одной командой.
Последние четыре поля — сверх общего формата, для порядка разбора.
"""
from __future__ import annotations

import collections
import os
import time

from problems.olympiad_contour import autofix, bank, reference, render, run, standard

BLOCKER = {
    ('S1', 'empty_statement'), ('S4', 'katex_error'), ('S5', 'figure_missing'), ('S5', 'figure_empty'),
    ('S5', 'figure_broken'), ('S5', 'marker_without_figure'), ('S7', 'not_playable'), ('S7', 'no_key'),
    ('S7', 'key_not_in_options'), ('S7', 'few_options'), ('S8', 'criteria_other_task'),
    ('S8', 'solution_in_statement'), ('S6', 'table_lost'),
}
MINOR_CHECKS = {'S9', 'B4'}
RENDER_BLOCKER_CHECKS = {'R1', 'R2', 'R3', 'R4', 'R6', 'B0', 'B2', 'B3'}


def severity(check, codes):
    if check in MINOR_CHECKS:
        return 'minor'
    if check in RENDER_BLOCKER_CHECKS or any((check, c) in BLOCKER for c in codes):
        return 'blocker'
    return 'major'


def current_of(card):
    test = card.get('test') or {}
    return {
        'statement': card.get('statement') or '',
        'parts': [{k: p.get(k) for k in ('pk', 'label', 'text', 'answer') if k in p}
                  for p in card.get('parts') or []],
        'solution': card.get('solution') or '',
        'answer': card.get('answer') or '',
        'criteria': card.get('criteria') or '',
        'options': [{k: o.get(k) for k in ('pk', 'label', 'text', 'correct') if k in o}
                    for o in test.get('options') or []],
        'key': test.get('key') if test else None,
    }


def _key(card):
    return card['ref_key'] if card['level'] == 'ref' else str(card['problem_id'])


def make_item(card, check, details, *, proposed=None, auto=False, codes=()):
    return {
        'item_id': 'q1_contour:%s:%s:%s%s' % (card['olympiad'], _key(card), check, ':auto' if auto else ''),
        'source': 'q1_contour',
        'olympiad': card['olympiad'],
        'ref_key': card.get('ref_key') or card.get('linked_ref_key'),
        'problem_id': card.get('problem_id'),
        'check': check,
        'details': details[:1000],
        'page_images': list(card.get('page_images') or []),
        'current': current_of(card),
        'proposed': proposed,
        'confidence': 1.0 if auto else None,
        'auto': auto,
        'severity': 'minor' if auto else severity(check, codes),
        'level': card['level'],
        'visible': card.get('visible'),
    }


def _join(fails):
    return '; '.join('%s: %s' % (f['code'], f['details']) for f in fails)


#: вид автоисправления → проверка очереди
AUTO_CHECK = {'currency': 'S4', 'left_right': 'S4', 'number_space': 'R3', 'html_entity': 'R3'}


def autofix_items(cards):
    """Предложения автоисправлений по всем текстам карточек (пакетом)."""
    slots = []
    for ci, card in enumerate(cards):
        for field in ('statement', 'solution', 'answer', 'criteria'):
            if (card.get(field) or '').strip():
                slots.append((ci, (field,), card[field]))
        for pi, p in enumerate(card.get('parts') or []):
            for f in ('text', 'answer'):
                if (p.get(f) or '').strip():
                    slots.append((ci, ('parts', pi, f), p[f]))
        for oi, o in enumerate((card.get('test') or {}).get('options') or []):
            if (o.get('text') or '').strip():
                slots.append((ci, ('options', oi, 'text'), o['text']))
    fixes = autofix.propose([s[2] for s in slots])
    per_card = collections.defaultdict(list)
    for (ci, path, _old), (new, kinds) in zip(slots, fixes):
        if new is not None:
            per_card[ci].append((path, new, kinds))
    items = []
    for ci, changes in per_card.items():
        card = cards[ci]
        by_check = collections.defaultdict(list)
        for path, new, kinds in changes:
            for check in sorted({AUTO_CHECK[k] for k in kinds}):
                by_check[check].append((path, new, kinds))
        for check, changes_c in by_check.items():
            cur = current_of(card)
            proposed, kinds_all = {}, set()
            for path, new, kinds in changes_c:
                kinds_all.update(kinds)
                if len(path) == 1:
                    proposed[path[0]] = new
                else:
                    name, idx, f = path
                    lst = proposed.setdefault(name, [dict(x) for x in cur[name]])
                    lst[idx][f] = new
            items.append(make_item(card, check, 'автоисправление: %s (полей %d)' % (
                ', '.join(sorted(kinds_all)), len(changes_c)), proposed=proposed, auto=True))
    return items


def load_cards(out_dir, data_root=None):
    """Карточки банка и эталонов заново (тексты для `current`) в порядке результатов."""
    sets, ref_cards = reference.load_all(data_root or reference.DATA_ROOT)
    by_key = {c['ref_key']: c for c in ref_cards}
    rejected = {}
    for refset in sets.values():
        rejected.update(refset.rejected)
    rows = run.read_jsonl(os.path.join(out_dir, 'standard_results.jsonl'))
    ids = [r['problem_id'] for r in rows if r['level'] == 'bank']
    _ids, visible, _scope = bank.scope_ids(())
    bank_cards = bank.load_cards(ids, visible, by_key, rejected, reference.load_suspect())
    return bank_cards, ref_cards, rows


def main(opts, stdout):
    out_dir = opts['out']
    stdout.write('очередь: карточки заново…')
    bank_cards, ref_cards, std_rows = load_cards(out_dir, opts.get('data_root'))
    render_rows = {r['problem_id']: r for r in run.read_jsonl(os.path.join(out_dir, 'render_results.jsonl'))}
    cards_by = {('bank', c['problem_id']): c for c in bank_cards}
    cards_by.update({('ref', c['ref_key']): c for c in ref_cards})
    items = []
    for row in std_rows:
        card = cards_by[(row['level'], row['problem_id'] if row['level'] == 'bank' else row['ref_key'])]
        by_check = collections.defaultdict(list)
        for f in row['fails']:
            by_check[f['check']].append(f)
        if row['level'] == 'bank':
            for f in (render_rows.get(row['problem_id']) or {}).get('fails') or []:
                by_check[f['check']].append(f)
        for check, fails in by_check.items():
            items.append(make_item(card, check, _join(fails), codes=[f['code'] for f in fails]))
    stdout.write('автоисправления…')
    auto = autofix_items(bank_cards + ref_cards)
    items += auto
    qdir = os.path.join(out_dir, 'queues')
    os.makedirs(qdir, exist_ok=True)
    order = {'blocker': 0, 'major': 1, 'minor': 2}
    olymp = {o: i for i, o in enumerate(run.OLYMPIAD_ORDER)}
    items.sort(key=lambda it: (it['level'] != 'bank', not it.get('visible'), order[it['severity']],
                               olymp.get(it['olympiad'], 99), str(it['problem_id'] or it['ref_key']),
                               it['check']))
    run.write_jsonl(os.path.join(qdir, 'q1_contour.jsonl'), items)
    summary = summary_md(std_rows, list(render_rows.values()), items)
    with open(os.path.join(out_dir, 'quality_summary.md'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(summary)
    stdout.write('очередь: %d строк (авто %d)' % (len(items), len(auto)))


# ── Сводка ───────────────────────────────────────────────────────────────

def _shame_free(std_row, render_row):
    """«Не стыдно показать»: нет провалов, кроме S9 (метаданные/заголовок) и B4
    (таблица листается вбок на телефоне)."""
    s_bad = [c for c in std_row['failed_checks'] if c != 'S9']
    r_bad = [c for c in (render_row or {}).get('failed_checks') or [] if c != 'B4']
    return not s_bad and not r_bad


def summary_md(std_rows, render_rows, items):
    rr = {r['problem_id']: r for r in render_rows}
    lines = ['# Контур качества ВП, МОШ, ВсОШ — сводка (Q1, %s)' % time.strftime('%d.%m.%Y %H:%M'), '',
             '«Не стыдно показать» = задача проходит стандарт S1–S8, S10 и проверку отображения '
             '(R1–R6, B0–B3). Не считаются: S9 (метаданные и заголовок: заглушки ждут обогащения, '
             'ссылки не на официальный PDF) и B4 (таблица листается вбок на телефоне).', '',
             '## Банк — задачи сайта', '',
             '| олимпиада | всего | видимых | стандарт целиком | стандарт без S9 | отображение | '
             'отображение без B4 | **не стыдно** | в очереди | из них только авто |',
             '|---|---|---|---|---|---|---|---|---|---|']
    q_by_card = collections.defaultdict(list)
    for it in items:
        q_by_card[(it['level'], it['problem_id'] if it['level'] == 'bank' else it['ref_key'])].append(it)
    by = collections.defaultdict(list)
    for row in std_rows:
        by[(row['level'], row['olympiad'])].append(row)
    tot = collections.Counter()
    invariant_ok = True
    for (level, name) in sorted(by, key=lambda k: (k[0] != 'bank', run._olymp_key(k[1]))):
        if level != 'bank':
            continue
        rows = by[(level, name)]
        c = collections.Counter()
        for row in rows:
            r = rr.get(row['problem_id'])
            c['total'] += 1
            c['visible'] += bool(row['visible'])
            c['std'] += row['passed']
            c['std9'] += not [x for x in row['failed_checks'] if x != 'S9']
            c['ren'] += bool(r and r['passed'])
            c['ren4'] += bool(r and not [x for x in r['failed_checks'] if x != 'B4'])
            c['ok'] += _shame_free(row, r)
            q = q_by_card.get(('bank', row['problem_id']), [])
            c['queued'] += bool(q)
            c['auto_only'] += bool(q) and all(it['auto'] for it in q)
            c['passed_all'] += row['passed'] and bool(r and r['passed']) and not q
        invariant_ok &= c['passed_all'] + c['queued'] == c['total']
        tot.update(c)
        lines.append('| %s | %d | %d | %d (%s) | %d (%s) | %d (%s) | %d (%s) | **%d (%s)** | %d | %d |' % (
            name, c['total'], c['visible'], c['std'], run._pct(c['std'], c['total']), c['std9'],
            run._pct(c['std9'], c['total']), c['ren'], run._pct(c['ren'], c['total']), c['ren4'],
            run._pct(c['ren4'], c['total']), c['ok'], run._pct(c['ok'], c['total']), c['queued'],
            c['auto_only']))
    lines.append('| **всего** | %d | %d | %d (%s) | %d (%s) | %d (%s) | %d (%s) | **%d (%s)** | %d | %d |' % (
        tot['total'], tot['visible'], tot['std'], run._pct(tot['std'], tot['total']), tot['std9'],
        run._pct(tot['std9'], tot['total']), tot['ren'], run._pct(tot['ren'], tot['total']), tot['ren4'],
        run._pct(tot['ren4'], tot['total']), tot['ok'], run._pct(tot['ok'], tot['total']), tot['queued'],
        tot['auto_only']))
    lines += ['', 'Инвариант «прошли всё + в очереди = всего» по каждой олимпиаде банка: %s.'
              % ('сошёлся' if invariant_ok else 'НЕ СОШЁЛСЯ')]
    # только видимые — то, что ученик видит сейчас
    vis = [row for row in std_rows if row['level'] == 'bank' and row['visible']]
    ok_vis = sum(_shame_free(row, rr.get(row['problem_id'])) for row in vis)
    lines += ['', 'Из **видимых сейчас** олимпиадных задач «не стыдно показать»: **%d из %d (%s)**.'
              % (ok_vis, len(vis), run._pct(ok_vis, len(vis)))]
    lines += ['', '## Эталонные файлы', '',
              '| олимпиада | строк | стандарт целиком | без S9 | в очереди | из них только авто |',
              '|---|---|---|---|---|---|']
    for (level, name) in sorted(by, key=lambda k: run._olymp_key(k[1])):
        if level != 'ref':
            continue
        rows = by[(level, name)]
        std = sum(r['passed'] for r in rows)
        std9 = sum(not [x for x in r['failed_checks'] if x != 'S9'] for r in rows)
        queued = sum(bool(q_by_card.get(('ref', r['ref_key']))) for r in rows)
        auto_only = sum(bool(q_by_card.get(('ref', r['ref_key']))) and all(
            it['auto'] for it in q_by_card[('ref', r['ref_key'])]) for r in rows)
        lines.append('| %s | %d | %d (%s) | %d (%s) | %d | %d |' % (
            name, len(rows), std, run._pct(std, len(rows)), std9, run._pct(std9, len(rows)), queued, auto_only))
    lines += ['', '## Очередь по проверкам', '',
              '| проверка | что | банк: строк | банк видимые | эталон: строк | авто (банк / эталон) |',
              '|---|---|---|---|---|---|']
    qc = collections.Counter()
    for it in items:
        qc[(it['check'], it['level'], bool(it['visible']), it['auto'])] += 1
    names = dict(standard.CHECK_NAMES, **render.RENDER_NAMES)
    for check in list(standard.CHECKS) + list(render.RENDER_CHECKS):
        bank_n = qc[(check, 'bank', True, False)] + qc[(check, 'bank', False, False)]
        if not (bank_n or qc[(check, 'ref', False, False)] or qc[(check, 'bank', True, True)]
                or qc[(check, 'bank', False, True)] or qc[(check, 'ref', False, True)]):
            continue
        lines.append('| %s | %s | %d | %d | %d | %d / %d |' % (
            check, names[check], bank_n, qc[(check, 'bank', True, False)], qc[(check, 'ref', False, False)],
            qc[(check, 'bank', True, True)] + qc[(check, 'bank', False, True)], qc[(check, 'ref', False, True)]))
    sev = collections.Counter((it['level'], it['severity']) for it in items if not it['auto'])
    lines += ['', 'Строк очереди всего %d: автоисправлений %d; людям — банк: blocker %d, major %d, minor %d; '
              'эталон: blocker %d, major %d, minor %d.' % (
                  len(items), sum(it['auto'] for it in items), sev[('bank', 'blocker')], sev[('bank', 'major')],
                  sev[('bank', 'minor')], sev[('ref', 'blocker')], sev[('ref', 'major')], sev[('ref', 'minor')])]
    return '\n'.join(lines) + '\n'
