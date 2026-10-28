# -*- coding: utf-8 -*-
"""Прогон стандарта по всем карточкам: S4 пакетом, S10 по группам, отчёт."""
from __future__ import annotations

import collections
import json
import os

from problems.olympiad_contour import katex, standard

OLYMPIAD_ORDER = ('vp', 'vp-fingram', 'vp-ob', 'mosh', 'mosh-fingram', 'mosh-entrepreneurship', 'vseros')


def check_cards(cards, katex_check=katex.check_texts):
    """[карточка] → [результат] того же порядка: {fails, skipped}."""
    texts, owners = [], []
    for i, card in enumerate(cards):
        for field, text in standard.formula_texts(card):
            texts.append(text)
            owners.append((i, field))
    per_card = collections.defaultdict(list)
    for (i, field), res in zip(owners, katex_check(texts) if texts else []):
        per_card[i].append((field, res))
    dups = standard.s10_groups(cards)
    return [standard.check_card(card, standard.s4_from_results(per_card.get(i, [])), dups.get(i, []))
            for i, card in enumerate(cards)]


def result_row(card, res, scope=()):
    return {
        'level': card['level'], 'olympiad': card['olympiad'], 'ref_key': card.get('ref_key'),
        'problem_id': card.get('problem_id'), 'event_id': card.get('event_id'),
        'number': card.get('number'), 'visible': card.get('visible'),
        'scope': sorted(scope), 'passed': not res['fails'],
        'failed_checks': sorted({f['check'] for f in res['fails']},
                                key=lambda c: standard.CHECKS.index(c)),
        'fails': res['fails'], 'skipped': res['skipped'],
    }


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')


def read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _olymp_key(name):
    return OLYMPIAD_ORDER.index(name) if name in OLYMPIAD_ORDER else 99


def summary(rows):
    """{(уровень, олимпиада): {total, passed, by_check: {S: n}, by_code: {code: n}}}."""
    out = {}
    for row in rows:
        s = out.setdefault((row['level'], row['olympiad'] or '?'), {
            'total': 0, 'passed': 0, 'by_check': collections.Counter(),
            'by_code': collections.Counter(), 'skipped': collections.Counter()})
        s['total'] += 1
        s['passed'] += row['passed']
        for check in row['failed_checks']:
            s['by_check'][check] += 1
        for code in {(f['check'], f['code']) for f in row['fails']}:
            s['by_code'][code] += 1
        for check in row['skipped']:
            s['skipped'][check] += 1
    return out


def _pct(a, b):
    return '%.1f %%' % (100.0 * a / b) if b else '—'


def report_md(rows, title, extra_lines=(), examples_per_code=3):
    summ = summary(rows)
    lines = ['# %s' % title, '']
    lines.extend(extra_lines)
    for level, name in (('bank', 'Банк (задачи сайта)'), ('ref', 'Эталонные файлы')):
        keys = sorted((k for k in summ if k[0] == level), key=lambda k: _olymp_key(k[1]))
        if not keys:
            continue
        lines += ['', '## %s' % name, '',
                  '| олимпиада | всего | прошли | не прошли | ' + ' | '.join(standard.CHECKS) + ' |',
                  '|---|---|---|---|' + '---|' * len(standard.CHECKS)]
        tot = collections.Counter()
        for key in keys:
            s = summ[key]
            tot['total'] += s['total']
            tot['passed'] += s['passed']
            for c in standard.CHECKS:
                tot[c] += s['by_check'][c]
            lines.append('| %s | %d | %d (%s) | %d | %s |' % (
                key[1], s['total'], s['passed'], _pct(s['passed'], s['total']),
                s['total'] - s['passed'], ' | '.join(str(s['by_check'][c]) for c in standard.CHECKS)))
        lines.append('| **всего** | %d | %d (%s) | %d | %s |' % (
            tot['total'], tot['passed'], _pct(tot['passed'], tot['total']), tot['total'] - tot['passed'],
            ' | '.join(str(tot[c]) for c in standard.CHECKS)))
        skipped = collections.Counter()
        for key in keys:
            skipped.update(summ[key]['skipped'])
        if skipped.get('S3'):
            lines += ['', 'S3 пропущена (нет слоя PDF или скан): %d карточек.' % skipped['S3']]
    lines += ['', '## Причины (по числу карточек) с примерами', '']
    codes = collections.Counter()
    examples = collections.defaultdict(list)
    for row in rows:
        seen = set()
        for f in row['fails']:
            k = (f['check'], f['code'])
            if k in seen:
                continue
            seen.add(k)
            codes[(row['level'],) + k] += 1
            if len(examples[(row['level'],) + k]) < examples_per_code:
                who = ('#%s' % row['problem_id']) if row['level'] == 'bank' else row['ref_key']
                examples[(row['level'],) + k].append('%s — %s' % (who, f['details'][:140]))
    for (level, check, code), n in sorted(codes.items(), key=lambda kv: (kv[0][0], -kv[1])):
        lines.append('- **%s %s `%s`** (%s): %d — %s' % (
            'банк' if level == 'bank' else 'эталон', check, code, standard.CHECK_NAMES[check], n,
            '; '.join(examples[(level, check, code)]).replace('|', '¦')))
    return '\n'.join(lines) + '\n'
