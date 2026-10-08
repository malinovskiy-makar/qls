#!/usr/bin/env python3
"""Сводка широкого прогона: python3 replay_sum.py ПАПКА  (в ней replay.jsonl)."""
import collections
import json
import sys
from pathlib import Path

rows = [json.loads(l) for l in (Path(sys.argv[1]) / 'replay.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
ok = [r for r in rows if 'stats' in r]
bad = [r for r in rows if 'stats' not in r]
print('задач', len(rows), '| файл построен', len(ok), '| сбоев', len(bad))
for r in bad[:12]:
    print('   СБОЙ', r['id'], (r.get('err') or r.get('actErr') or '')[:200])
print('состояние после выгрузки изменилось:', sum(1 for r in ok if not r['stateSame']),
      '| повторная сборка дала другой файл:', sum(1 for r in ok if not r['repeatSame']),
      '| ошибок страницы:', sum(1 for r in ok if r.get('pageErrors')))
tot = collections.Counter()
for r in ok:
    for k, v in r['stats'].items():
        tot[k] += v
order = ['panels', 'axisLines', 'gridLines', 'ticks', 'curvesFormula', 'curvesNumeric', 'numericExact', 'curvesPolyRec', 'curvesNoRecPoly', 'curvesNoRecSampled', 'curvesMismatch',
         'areasBounds', 'areasPoly', 'areasNumeric', 'areasNoRecSampled', 'areasMismatch', 'outlines', 'rects', 'segs', 'dots', 'texts', 'legendRows', 'pairs']
print('суммы:', ', '.join(k + ' ' + str(tot[k]) for k in order if k in tot))
warn = collections.Counter(w for r in ok for w in set(r.get('warn') or []))
for w, n in warn.most_common():
    print('   предупреждение (состояний %d): %s' % (n, w))
ms = sorted(r['ms'] for r in ok)
if ms:
    print('время сборки, мс: медиана', ms[len(ms) // 2], '| 95 %', ms[int(len(ms) * .95)], '| наибольшее', ms[-1])
print('разных файлов', len(set(r['sha'] for r in ok)), '| в режиме «Сначала сам»', sum(1 for r in ok if r.get('self')))
for name, key in (('запись кривой не сошлась', 'curvesMismatch'), ('запись области не сошлась', 'areasMismatch'), ('у панели не две оси (ноль за кадром или оси выключены)', None)):
    hit = [r for r in ok if (r['stats'].get(key) if key else r['stats']['axisLines'] != 2 * r['stats']['panels'])]
    if hit:
        print(name + ': состояний', len(hit))
        for r in hit[:15]:
            print('   ', r['id'], '|', (r.get('action') or '')[:90])
by = collections.defaultdict(collections.Counter)
for r in ok:
    for k in ('curvesNoRecPoly', 'curvesNoRecSampled', 'areasNoRecSampled', 'curvesMismatch', 'areasMismatch'):
        by[r['key']][k] = max(by[r['key']][k], r['stats'].get(k, 0))
print('наибольшее число дефектов на одно состояние, по моделям (ломаная без записи / отсчёты без записи / область без записи / не сошлось):')
for k in sorted(by):
    c = by[k]
    if any(c.values()):
        print('   %-14s %2d / %2d / %2d / %2d' % (k, c['curvesNoRecPoly'], c['curvesNoRecSampled'], c['areasNoRecSampled'], c['curvesMismatch'] + c['areasMismatch']))
