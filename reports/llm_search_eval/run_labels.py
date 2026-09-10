# -*- coding: utf-8 -*-
"""Сведение разметки двух судей и согласие с ручной разметкой владельца.

Считаются ТРИ правила слияния (решение владельца 10.09.2026): «согласие»,
«мягкое», «строгое». Основным становится то, у которого согласие с
владельцем по шкале «годится / не годится» выше; два других уходят в
metrics.md строками чувствительности.

Пара, размеченная только одним судьёй, получает его метку с флагом
`single_judge`. Доля таких пар — в отчёт отдельной строкой.

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


def load_manual():
    with open(MANUAL, encoding='utf-8') as handle:
        raw = json.load(handle)
    manual = {}
    for row in raw:
        manual.setdefault(row['query_id'], {})[row['problem_id']] = \
            SCALE[row['verdict']]
    return manual


def main():
    pool = [json.loads(line) for line in open(POOL, encoding='utf-8')]
    sol = read_labels('labels_sol.jsonl')
    deep = read_labels('labels_deepseek.jsonl')
    manual = load_manual()

    # ── согласие по каждому правилу и по каждому судье ─────────────────
    report = {}
    for name in ('GPT-5.6 Sol', 'DeepSeek V4 Pro'):
        source = sol if name.startswith('GPT') else deep
        machine, human = {}, {}
        for row in pool:
            mid = row['manual_id']
            if not mid:
                continue
            for pid in row['pool']:
                if pid not in manual.get(mid, {}):
                    continue
                value = source.get((row['query_id'], pid))
                if value is None:
                    continue
                machine[pid], human[pid] = value, manual[mid][pid]
        report[name] = judging.agreement(machine, human)

    for rule in judging.MERGE_RULES:
        machine, human = {}, {}
        for row in pool:
            mid = row['manual_id']
            if not mid:
                continue
            for pid in row['pool']:
                if pid not in manual.get(mid, {}):
                    continue
                a = sol.get((row['query_id'], pid))
                b = deep.get((row['query_id'], pid))
                if a is None and b is None:
                    continue
                merged = judging.merge({pid: a}, {pid: b}, rule=rule)[pid]
                machine[pid], human[pid] = merged['label'], manual[mid][pid]
        report['правило «%s»' % rule] = judging.agreement(machine, human)

    ranked = sorted(
        (name for name in report if name.startswith('правило')),
        key=lambda name: report[name]['годится / не годится'] or 0,
        reverse=True)
    primary = ranked[0].split('«')[1].rstrip('»')

    # ── итоговые метки по всем трём правилам ───────────────────────────
    stats = collections.Counter()
    changed = collections.Counter()
    final = []
    for row in pool:
        qid, mid = row['query_id'], row['manual_id']
        for pid in row['pool']:
            a, b = sol.get((qid, pid)), deep.get((qid, pid))
            stats['пар всего'] += 1
            if a is None and b is None:
                stats['без единой метки'] += 1
                continue
            labels = {rule: judging.merge({pid: a}, {pid: b}, rule=rule)[pid]
                      for rule in judging.MERGE_RULES}
            single = a is None or b is None
            stats['single_judge' if single else 'две метки'] += 1
            if not single and labels[primary]['disagreement']:
                stats['разногласий'] += 1
            for rule in judging.MERGE_RULES:
                if labels[rule]['label'] != labels[primary]['label']:
                    changed[rule] += 1
            entry = {'query_id': qid, 'problem_id': pid,
                     'label': labels[primary]['label'],
                     'labels': {r: labels[r]['label']
                                for r in judging.MERGE_RULES},
                     'disagreement': labels[primary]['disagreement'],
                     'single_judge': single, 'source': 'машина'}
            if mid and pid in manual.get(mid, {}):
                entry['machine_label'] = entry['label']
                entry['label'] = manual[mid][pid]
                entry['source'] = 'владелец'
                stats['перекрыто ручной разметкой'] += 1
            final.append(entry)
            stats['меток в итоге'] += 1

    judging.dump(final, os.path.join(HERE, 'labels_final.jsonl'))

    lines = ['# Согласие судей с ручной разметкой владельца', '',
             'Общие пары — те, что есть и в ручной разметке, и в пуле.', '',
             '| Разметка | общих пар | точное совпадение | пар без «спорно» '
             '| годится / не годится |', '|---|---|---|---|---|']
    for name, row in report.items():
        if not row.get('общих пар'):
            lines.append('| %s | 0 | — | — | — |' % name)
            continue
        lines.append('| %s | %d | %.0f %% | %d | %s |' % (
            name, row['общих пар'], 100 * row['точное совпадение'],
            row['пар без «спорно»'],
            ('%.0f %%' % (100 * row['годится / не годится']))
            if row['годится / не годится'] is not None else '—'))

    lines += ['', 'Основное правило: **%s** — у него согласие по границе '
                  'годности выше остальных.' % primary, '',
              '## Сколько пар меняет метку от смены правила', '']
    total = max(stats['меток в итоге'], 1)
    for rule in judging.MERGE_RULES:
        lines.append('- «%s»: %d пар из %d (%.1f %%)'
                     % (rule, changed[rule], total,
                        100.0 * changed[rule] / total))

    lines += ['', '## Сведение пула', '']
    for key, value in stats.most_common():
        lines.append('- %s: %d' % (key, value))

    with open(os.path.join(HERE, 'agreement.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    json.dump({'report': report, 'primary': primary,
               'changed_by_rule': dict(changed), 'stats': dict(stats)},
              open(os.path.join(HERE, 'agreement.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('\n'.join(lines))


if __name__ == '__main__':
    main()
