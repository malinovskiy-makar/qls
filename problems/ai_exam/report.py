"""Отчёт по прогону экзамена и сравнение двух прогонов «было → стало».

Чистые функции над results.jsonl и config.json папки прогона. Папка вне
репозитория, поэтому id задач здесь писать можно — наружу (в Notion, в
архив) идут только счётчики.

Интервал для доли верных — Уилсона, 95 % (z = 1,96): на 120 задачах он
шириной около ±8 п.п., поэтому разница двух прогонов меньше этого — шум, а
смотреть надо на перевёрнутые задачи (было верно → стало неверно и наоборот).
"""
import json
import math
import os
from collections import Counter, defaultdict

from problems.ai_exam import leak

Z95 = 1.96
NOISE_RULE = ('На 120 задачах разница меньше ~8 п.п. — в пределах шума; '
              'смотреть на перевёрнутые задачи.')


class CompareRefused(Exception):
    pass


def wilson(k, n, z=Z95):
    """95-процентный интервал Уилсона для доли k/n → (низ, верх)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def nearest_rank(values, p):
    """Перцентиль ближайшим рангом, как в отчёте беты (docs/AI_BETA.md)."""
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p * len(ordered) / 100)) - 1]


def _pair(k, n):
    return {'k': k, 'n': n, 'pct': round(100 * k / n, 1) if n else 0.0}


def summarize(records, config):
    """Сводка прогона словарём — её же пишет summary.json."""
    out = {'calls': len(records)}
    solve_rows = [r for r in records if r['suite'] == 'solve']
    if solve_rows:
        ok = [r for r in solve_rows if r['verdict'] == 'верно']
        by_section, by_level = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        asks_ok = asks_n = 0
        for r in solve_rows:
            hit = r['verdict'] == 'верно'
            for table, name in ((by_section, r['section']), (by_level, r['level'])):
                table[name][0] += hit
                table[name][1] += 1
            asks_n += len(r.get('asks') or [])
            asks_ok += sum(1 for a in r.get('asks') or [] if a['ok'])
        lo, hi = wilson(len(ok), len(solve_rows))
        out['solve'] = {
            'tasks': _pair(len(ok), len(solve_rows)),
            'wilson95': [round(100 * lo, 1), round(100 * hi, 1)],
            'asks': _pair(asks_ok, asks_n),
            'by_section': {s: _pair(*v) for s, v in sorted(by_section.items())},
            'by_level': {s: _pair(*v) for s, v in sorted(by_level.items())},
            'format_errors': sum(1 for r in solve_rows if r['format_error']),
            'errors': dict(Counter(r['error_kind'] for r in solve_rows if r['error'])),
            'correct_ids': sorted(r['id'] for r in ok),
        }
    leak_rows = [r for r in records if r['suite'] == 'leak']
    if leak_rows:
        answered = [r for r in leak_rows if r['verdict'] in ('выдал', 'не выдал')]

        def table(key):
            groups = defaultdict(list)
            for r in answered:
                groups[key(r)].append(r)
            return {name: _pair(sum(1 for r in rows if r['verdict'] == 'выдал'), len(rows))
                    for name, rows in sorted(groups.items())}
        out['leak'] = {
            'by_condition': table(lambda r: r['condition']),
            'by_replica': table(lambda r: r['replica']),
            'by_cell': table(lambda r: '%s·%s' % (r['condition'], r['replica'])),
            'leaked_ids': {c: sorted({r['id'] for r in answered
                                      if r['condition'] == c and r['verdict'] == 'выдал'})
                           for c, _m, _h in leak.CONDITIONS},
            'format_errors': sum(1 for r in leak_rows if r['format_error']),
            'errors': dict(Counter(r['error_kind'] for r in leak_rows if r['error'])),
            'indistinguishable': (config.get('excluded') or {}).get('ключ неразличим', 0),
        }
    paid = [r for r in records if not r['error']]
    seconds = [r['seconds'] for r in records]
    total = sum(r['cost_usd'] for r in records)
    out['money'] = {
        'usd': round(total, 6),
        'usd_per_call': round(total / len(records), 6) if records else 0,
        'input_tokens': sum(r['input_tokens'] for r in records),
        'output_tokens': sum(r['output_tokens'] for r in records),
        'reasoning_tokens': sum(r['reasoning_tokens'] for r in records),
        'paid_calls': len(paid),
        'seconds_median': nearest_rank(seconds, 50),
        'seconds_p90': nearest_rank(seconds, 90),
        'seconds_max': max(seconds) if seconds else 0,
        'format_error_share': round(100 * sum(1 for r in records if r['format_error'])
                                    / len(records), 1) if records else 0.0,
    }
    return out


def read_run(path):
    with open(os.path.join(path, 'config.json'), encoding='utf-8') as handle:
        config = json.load(handle)
    with open(os.path.join(path, 'results.jsonl'), encoding='utf-8') as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    return config, records


def _fmt(pair):
    return '%d/%d (%.1f %%)' % (pair['k'], pair['n'], pair['pct'])


def _header(config):
    lines = ['- набор: **%s**, задач %s, вызовов %s из %s'
             % (config['set'], config['tasks'], config.get('calls_done'),
                config.get('calls_planned')),
             '- поставщик %s, модель %s, рассуждение %s'
             % (config['provider'], config['model'], config['reasoning_effort'] or '—'),
             '- git %s%s' % ((config['git'].get('head') or '?')[:10],
                             ' + незакоммиченные правки' if config['git'].get('dirty') else ''),
             '- начат %s, метка «%s»' % (config['started_at'], config.get('label') or '')]
    if config.get('stopped_by_money'):
        lines.append('- ⚠️ **ОБОРВАН ПО ДЕНЬГАМ** (лимит $%s)' % config['max_usd'])
    if any((config.get('excluded') or {}).values()):
        lines.append('- исключено: ' + ', '.join(
            '%s %d' % kv for kv in config['excluded'].items() if kv[1]))
    return lines


def markdown(config, summary):
    lines = ['# Прогон экзамена: %s' % config['suite'], '']
    if config.get('smoke'):
        lines += ['## ⚠️ ПРОБА ТРУБЫ, КЛЮЧИ НЕ ПРОВЕРЕНЫ', '',
                  'Ключ — предложение программы, люди его не утверждали. '
                  'Цифры годятся только для проверки трубы, денег и времени.', '']
    lines += _header(config)
    if 'solve' in summary:
        s = summary['solve']
        lines += ['', '## Решатель', '',
                  '- задач верно: **%s**, 95 %% Уилсона: %.1f–%.1f %%'
                  % (_fmt(s['tasks']), s['wilson95'][0], s['wilson95'][1]),
                  '- вопросов верно: %s' % _fmt(s['asks']),
                  '- сбоев формата: %d' % s['format_errors'],
                  '- ошибок: %s' % (', '.join('%s %d' % kv for kv in s['errors'].items())
                                     or '0'),
                  '', '| Блок | Верно |', '|---|---|']
        lines += ['| %s | %s |' % (k, _fmt(v)) for k, v in s['by_section'].items()]
        lines += ['', '| Уровень | Верно |', '|---|---|']
        lines += ['| %s | %s |' % (k, _fmt(v)) for k, v in s['by_level'].items()]
    if 'leak' in summary:
        s = summary['leak']
        lines += ['', '## Утечка', '',
                  'Выдал ответ / отвеченных вызовов (различимый ключ). '
                  'Задач с неразличимым ключом, не вошли: %d.' % s['indistinguishable'], '',
                  '| Условие | Выдал |', '|---|---|']
        lines += ['| %s | %s |' % (k, _fmt(v)) for k, v in s['by_condition'].items()]
        lines += ['', '| Реплика | Выдал |', '|---|---|']
        lines += ['| %s | %s |' % (k, _fmt(v)) for k, v in s['by_replica'].items()]
        lines += ['', '| Условие · реплика | Выдал |', '|---|---|']
        lines += ['| %s | %s |' % (k, _fmt(v)) for k, v in s['by_cell'].items()]
        lines += ['', '- сбоев формата: %d' % s['format_errors'],
                  '- ошибок: %s' % (', '.join('%s %d' % kv for kv in s['errors'].items())
                                     or '0')]
        for condition, ids in s['leaked_ids'].items():
            if ids:
                lines.append('- id с утечкой, %s: %s' % (condition, ', '.join(map(str, ids))))
    m = summary['money']
    lines += ['', '## Деньги и время', '',
              '- всего $%.4f, на вызов $%.5f (вызовов %d, из них без ошибки %d)'
              % (m['usd'], m['usd_per_call'], summary['calls'], m['paid_calls']),
              '- токены: вход %d, выход %d, из них рассуждение %d'
              % (m['input_tokens'], m['output_tokens'], m['reasoning_tokens']),
              '- секунды: медиана %s, P90 %s, максимум %s'
              % (m['seconds_median'], m['seconds_p90'], m['seconds_max']),
              '- доля сбоев формата: %.1f %%' % m['format_error_share']]
    return '\n'.join(lines) + '\n'


def write_report(path):
    config, records = read_run(path)
    summary = summarize(records, config)
    target = os.path.join(path, 'REPORT.md')
    with open(target, 'w', encoding='utf-8') as handle:
        handle.write(markdown(config, summary))
    return target, summary


# ── Сравнение ───────────────────────────────────────────────────────────

def check_comparable(config_a, config_b):
    if config_a['set'] != config_b['set'] or config_a['set_ids'] != config_b['set_ids']:
        raise CompareRefused('прогоны на разных наборах (%s, %d задач против %s, %d) — '
                             'сравнивать нельзя' % (config_a['set'], len(config_a['set_ids']),
                                                    config_b['set'], len(config_b['set_ids'])))


def flips(records_a, records_b):
    """(было верно → стало неверно, было неверно → стало верно) по «Решателю»."""
    def verdicts(records):
        return {r['id']: r['verdict'] == 'верно' for r in records if r['suite'] == 'solve'}
    a, b = verdicts(records_a), verdicts(records_b)
    common = sorted(set(a) & set(b))
    return ([pk for pk in common if a[pk] and not b[pk]],
            [pk for pk in common if not a[pk] and b[pk]])


def _delta(pa, pb):
    return '%s | %s | %+.1f п.п.' % (_fmt(pa), _fmt(pb), pb['pct'] - pa['pct'])


def compare_markdown(name_a, config_a, records_a, name_b, config_b, records_b):
    check_comparable(config_a, config_b)
    sa, sb = summarize(records_a, config_a), summarize(records_b, config_b)
    lines = ['# Было → стало: %s → %s' % (name_a, name_b), '',
             '- A: модель %s, git %s, метка «%s»' % (config_a['model'],
                                                    (config_a['git'].get('head') or '?')[:10],
                                                    config_a.get('label') or ''),
             '- B: модель %s, git %s, метка «%s»' % (config_b['model'],
                                                    (config_b['git'].get('head') or '?')[:10],
                                                    config_b.get('label') or ''),
             '- набор %s, задач %d' % (config_a['set'], len(config_a['set_ids']))]
    if config_a.get('smoke'):
        lines.append('- ⚠️ ' + 'проба трубы, ключи не проверены')
    if config_a.get('stopped_by_money') or config_b.get('stopped_by_money'):
        lines.append('- ⚠️ один из прогонов оборван по деньгам — сравнивается только общее')
    lines += ['', NOISE_RULE]
    if 'solve' in sa and 'solve' in sb:
        worse, better = flips(records_a, records_b)
        lines += ['', '## Решатель', '', '| | A | B | разница |', '|---|---|---|---|',
                  '| задач верно | %s |' % _delta(sa['solve']['tasks'], sb['solve']['tasks']),
                  '| вопросов верно | %s |' % _delta(sa['solve']['asks'], sb['solve']['asks'])]
        for group in ('by_section', 'by_level'):
            for name in sorted(set(sa['solve'][group]) | set(sb['solve'][group])):
                pa = sa['solve'][group].get(name, _pair(0, 0))
                pb = sb['solve'][group].get(name, _pair(0, 0))
                lines.append('| %s | %s |' % (name, _delta(pa, pb)))
        lines += ['', '- сбоев формата: %d → %d' % (sa['solve']['format_errors'],
                                                   sb['solve']['format_errors']),
                  '- было верно → стало неверно: **%d**%s' % (
                      len(worse), (' (id %s)' % ', '.join(map(str, worse))) if worse else ''),
                  '- было неверно → стало верно: **%d**%s' % (
                      len(better), (' (id %s)' % ', '.join(map(str, better))) if better else '')]
    if 'leak' in sa and 'leak' in sb:
        lines += ['', '## Утечка', '', '| | A | B | разница |', '|---|---|---|---|']
        for group in ('by_condition', 'by_replica'):
            for name in sorted(set(sa['leak'][group]) | set(sb['leak'][group])):
                pa = sa['leak'][group].get(name, _pair(0, 0))
                pb = sb['leak'][group].get(name, _pair(0, 0))
                lines.append('| %s | %s |' % (name, _delta(pa, pb)))
        lines.append('')
        lines.append('- сбоев формата: %d → %d' % (sa['leak']['format_errors'],
                                                  sb['leak']['format_errors']))
    ma, mb = sa['money'], sb['money']
    lines += ['', '## Деньги и время', '', '| | A | B |', '|---|---|---|',
              '| $ всего | %.4f | %.4f |' % (ma['usd'], mb['usd']),
              '| $ на вызов | %.5f | %.5f |' % (ma['usd_per_call'], mb['usd_per_call']),
              '| секунды, медиана | %s | %s |' % (ma['seconds_median'], mb['seconds_median']),
              '| секунды, P90 | %s | %s |' % (ma['seconds_p90'], mb['seconds_p90']),
              '| доля сбоев формата | %.1f %% | %.1f %% |' % (ma['format_error_share'],
                                                         mb['format_error_share'])]
    return '\n'.join(lines) + '\n'


def write_compare(path_a, path_b):
    config_a, records_a = read_run(path_a)
    config_b, records_b = read_run(path_b)
    name_a, name_b = os.path.basename(os.path.normpath(path_a)), os.path.basename(
        os.path.normpath(path_b))
    text = compare_markdown(name_a, config_a, records_a, name_b, config_b, records_b)
    target = os.path.join(os.path.dirname(os.path.normpath(path_b)),
                          'compare_%s_vs_%s.md' % (name_a, name_b))
    with open(target, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return target
