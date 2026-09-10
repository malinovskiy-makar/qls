# -*- coding: utf-8 -*-
"""Сведение разметки двух судей и согласие с ручной разметкой владельца.

Итог по паре: оба «годится» → годится; оба «не годится» → не годится;
иначе «спорно» с флагом разногласия. Пара, которую разметил только один
судья, получает его метку с флагом `single_judge` — решение владельца
10.09.2026 на случай остановки счётчиком.

⚠️ РУЧНАЯ РАЗМЕТКА ВЛАДЕЛЬЦА — ИСТИНА. Там, где она есть, машинная метка
в итог не идёт вовсе, а только сверяется. Иначе стоп-гейт 2 проверял бы
судей по ним же самим.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/run_labels.py
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import judging  # noqa: E402

POOL = os.path.join(HERE, 'pool.jsonl')
MANUAL = 'reports/formula_choice/razmetka_336.json'
SCALE = {'good': 2, 'unsure': 1, 'bad': 0}


def read_labels(name):
    path = os.path.join(HERE, name)
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            out[(row['query_id'], row['problem_id'])] = row['label']
    return out


def main():
    pool = [json.loads(line) for line in open(POOL, encoding='utf-8')]
    sol = read_labels('labels_sol.jsonl')
    deep = read_labels('labels_deepseek.jsonl')

    with open(MANUAL, encoding='utf-8') as handle:
        raw = json.load(handle)
    manual = {}
    for row in raw:
        manual.setdefault(row['query_id'], {})[row['problem_id']] = \
            SCALE[row['verdict']]

    final, stats = [], collections.Counter()
    for row in pool:
        qid, mid = row['query_id'], row['manual_id']
        for pid in row['pool']:
            a, b = sol.get((qid, pid)), deep.get((qid, pid))
            stats['пар всего'] += 1
            if a is None and b is None:
                stats['без единой метки'] += 1
                continue
            if a is None or b is None:
                label = a if b is None else b
                single = True
                disagreement = False
                stats['single_judge'] += 1
            else:
                merged = judging.merge({pid: a}, {pid: b})[pid]
                label, disagreement, single = (merged['label'],
                                               merged['disagreement'], False)
                stats['две метки'] += 1
                if disagreement:
                    stats['разногласий'] += 1
            entry = {'query_id': qid, 'problem_id': pid, 'label': label,
                     'disagreement': disagreement, 'single_judge': single,
                     'source': 'машина'}
            if mid and pid in manual.get(mid, {}):
                entry['label'] = manual[mid][pid]
                entry['source'] = 'владелец'
                entry['machine_label'] = label
                stats['перекрыто ручной разметкой'] += 1
            final.append(entry)
            stats['меток в итоге'] += 1

    judging.dump(final, os.path.join(HERE, 'labels_final.jsonl'))

    # ── согласие с ручной разметкой ────────────────────────────────────
    lines = ['# Согласие судей с ручной разметкой владельца', '']
    report = {}
    for name, machine in (('GPT-5.6 Sol', sol), ('DeepSeek V4 Pro', deep),
                          ('итог двух судей', None)):
        pairs_machine, pairs_manual = {}, {}
        for row in pool:
            mid = row['manual_id']
            if not mid:
                continue
            for pid in row['pool']:
                if pid not in manual.get(mid, {}):
                    continue
                if machine is None:
                    a, b = sol.get((row['query_id'], pid)), deep.get(
                        (row['query_id'], pid))
                    if a is None and b is None:
                        continue
                    value = (judging.merge({pid: a}, {pid: b})[pid]['label']
                             if a is not None and b is not None
                             else (a if b is None else b))
                else:
                    value = machine.get((row['query_id'], pid))
                    if value is None:
                        continue
                pairs_machine[pid] = value
                pairs_manual[pid] = manual[mid][pid]
        report[name] = judging.agreement(pairs_machine, pairs_manual)

    lines.append('| Судья | общих пар | точное совпадение | пар без «спорно» '
                 '| годится / не годится |')
    lines.append('|---|---|---|---|---|')
    for name, row in report.items():
        if not row.get('общих пар'):
            lines.append('| %s | 0 | — | — | — |' % name)
            continue
        lines.append('| %s | %d | %.0f %% | %d | %s |' % (
            name, row['общих пар'], 100 * row['точное совпадение'],
            row['пар без «спорно»'],
            ('%.0f %%' % (100 * row['годится / не годится']))
            if row['годится / не годится'] is not None else '—'))

    lines += ['', '## Сведение пула', '']
    for key, value in stats.most_common():
        lines.append('- %s: %d' % (key, value))

    with open(os.path.join(HERE, 'agreement.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    json.dump(report, open(os.path.join(HERE, 'agreement.json'), 'w',
                           encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n'.join(lines[:12]))
    print()
    for key, value in stats.most_common():
        print('   %-28s %d' % (key, value))


if __name__ == '__main__':
    main()
