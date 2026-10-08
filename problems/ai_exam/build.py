"""Сборка экзамена: сейф, приём разметки, рабочий набор. Чистые функции.

На вход — строки candidates.jsonl, выгрузки людей (`ai_exam_review/2`) и
свежие хеши условий из банка; на выход — строки exam.jsonl / safe.jsonl /
exam_draft.jsonl и текст BUILD.md. К базе модуль не обращается — это
делает команда `ai_exam_build`, она же пишет файлы.

⚠️ СЕЙФ ПОМЕЧАЕТСЯ ЗАРАНЕЕ, до любых прогонов (`mark_safe`): 40 кандидатов
из пачек 1–3. В сейф идут первые 30 годных из них по порядку хеша, а годные
сверх тридцати в рабочий набор НЕ переходят — по ним мог пройти черновой
прогон, и сейф перестал бы быть нетронутым.

Правила приёма (docs/AI_EXAM.md, «Сборка и сейф»):
* плохая строка — жалоба в BUILD.md, соседние годные остаются;
* повторная выгрузка того же проверяющего и той же пачки заменяет прежнюю:
  читается файл с самым поздним `exported_at`, остальные «устарели»;
* задачу проверили двое: годится, только если оба «ok» и ключи совпали;
  иначе КОНФЛИКТ — задача исключена, решает владелец правкой файлов
  («последний победил» нет намеренно);
* условие в банке поменялось после проверки (`statement_hash`) — задача
  исключена: утверждённый ключ мог устареть.
"""
import hashlib
import json
from collections import Counter, defaultdict

from problems.ai_exam.numbers import parse_tol, to_number
from problems.ai_exam.review import validate_review

SAFE_CANDIDATES = 40
SAFE_SIZE = 30
WORK_SIZE = 120

#: Категории задачи после приёма; в сумме — все кандидаты.
GOOD, CONFLICT, HASH_CHANGED, BAD, SKIP, UNREVIEWED = (
    'годна', 'конфликт', 'хеш поменялся', 'bad', 'skip', 'не проверена')
CATEGORIES = (GOOD, CONFLICT, HASH_CHANGED, BAD, SKIP, UNREVIEWED)


def reserve_chunk(candidates):
    """Последняя пачка — резерв (docs/AI_EXAM.md, «Отбор и пачки»)."""
    return max(c['chunk'] for c in candidates)


def safe_hash(seed, pk):
    return hashlib.sha256(('%s:safe:%s' % (seed, pk)).encode('utf-8')).hexdigest()


def largest_remainder(sizes, total):
    """Раздать `total` мест пропорционально `sizes` (имя → размер) методом
    наибольшего остатка. При равных остатках — больший блок, затем имя."""
    whole = sum(sizes.values())
    if not whole:
        return {name: 0 for name in sizes}
    shares = {name: total * size / whole for name, size in sizes.items()}
    out = {name: int(share) for name, share in shares.items()}
    left = total - sum(out.values())
    order = sorted(sizes, key=lambda n: (-(shares[n] - out[n]), -sizes[n], n))
    for name in order[:left]:
        out[name] += 1
    return out


def mark_safe(candidates, seed, today, count=SAFE_CANDIDATES):
    """Кандидаты в сейф: `count` id из пачек кроме резервной, по блокам
    пропорционально, внутри блока — по sha256(f'{seed}:safe:{id}')."""
    reserve = reserve_chunk(candidates)
    pool = [c for c in candidates if c['chunk'] != reserve]
    by_section = defaultdict(list)
    for c in pool:
        by_section[c['section']].append(c['id'])
    quota = largest_remainder({s: len(ids) for s, ids in by_section.items()},
                              min(count, len(pool)))
    picked = []
    for section, ids in by_section.items():
        ids = sorted(ids, key=lambda pk: safe_hash(seed, pk))
        picked += ids[:quota[section]]
    picked.sort(key=lambda pk: safe_hash(seed, pk))
    return {'seed': seed, 'date': today, 'count': len(picked), 'ids': picked,
            'chunks': sorted({c['chunk'] for c in pool}),
            'by_section': {s: quota[s] for s in sorted(quota)}}


# ── Приём выгрузок ──────────────────────────────────────────────────────

def reviewer_key(name):
    """Один и тот же человек: без учёта регистра и пробелов."""
    return ''.join(str(name or '').split()).casefold()


def pick_latest(files):
    """files: [{'name', 'payload'}] годных по формату → (свежие, устаревшие).

    Ключ — (проверяющий, пачка); из нескольких файлов берётся самый поздний
    `exported_at` (ISO-строки сравниваются как строки), при равенстве — имя.
    """
    groups = defaultdict(list)
    for f in files:
        p = f['payload']
        groups[(reviewer_key(p.get('reviewer')), p.get('chunk'))].append(f)
    fresh, stale = [], []
    for group in groups.values():
        group.sort(key=lambda f: (str(f['payload'].get('exported_at') or ''), f['name']))
        fresh.append(group[-1])
        stale.extend(group[:-1])
    fresh.sort(key=lambda f: f['name'])
    stale.sort(key=lambda f: f['name'])
    return fresh, stale


def _ask_key(ask):
    """Ключ вопроса для сравнения двух проверяющих: skip или числа
    (по to_number), проценты и допуск. Подписи не сравниваются."""
    if ask.get('skip'):
        return (str(ask.get('part_id')), True, ())
    values = sorted((to_number(v.get('value')), bool(v.get('percent')),
                     parse_tol(v.get('tol')) or 0)
                    for v in ask.get('values') or [] if isinstance(v, dict))
    return (str(ask.get('part_id')), False, tuple(values))


def key_of(row):
    return tuple(sorted(_ask_key(a) for a in row.get('asks') or []))


def exam_row(candidate, row, reviewers):
    """Строка экзамена: вопросы в порядке кандидата, ключ — из разметки."""
    by_part = {str(a.get('part_id')): a for a in row.get('asks') or []}
    asks = []
    for ask in candidate['asks']:
        marked = by_part[str(ask['part_id'])]
        skip = bool(marked.get('skip'))
        values = [] if skip else [
            {'label': str(v.get('label') or '').strip(),
             'value': str(v.get('value') or '').strip(),
             'unit': str(v.get('unit') or '').strip(),
             'percent': bool(v.get('percent')),
             'tol': str(v.get('tol') or '').strip()}
            for v in marked.get('values') or [] if isinstance(v, dict)]
        asks.append({'part_id': ask['part_id'], 'label': ask['label'],
                     'skip': skip, 'values': values})
    return {'id': candidate['id'], 'section': candidate['section'],
            'topic': candidate['topic'], 'level': candidate['level'],
            'difficulty': candidate['difficulty'],
            'statement_hash': candidate['statement_hash'],
            'chunk': candidate['chunk'], 'n': candidate['n'],
            'reviewers': reviewers, 'asks': asks}


def classify(candidate, rows, fresh_hash):
    """rows: [(проверяющий, строка)] годных строк по задаче → (категория, деталь).

    Конфликт — когда хоть один сказал «ok», но не все «ok» с одним ключом.
    Никто не сказал «ok»: есть «bad» — bad, иначе skip.
    """
    if not rows:
        return UNREVIEWED, None
    verdicts = {row['verdict'] for _who, row in rows}
    if 'ok' in verdicts:
        keys = {key_of(row) for _who, row in rows}
        if verdicts != {'ok'} or len(keys) != 1:
            return CONFLICT, [(who, row['verdict'], row.get('reason') or '')
                              for who, row in rows]
        if fresh_hash != candidate['statement_hash']:
            return HASH_CHANGED, 'нет в банке' if fresh_hash is None else 'условие правили'
        reviewers = sorted({who for who, _row in rows}, key=reviewer_key)
        return GOOD, exam_row(candidate, rows[0][1], reviewers)
    if 'bad' in verdicts:
        return BAD, sorted({row.get('reason') or '' for _who, row in rows})
    return SKIP, None


def accept(candidates, files, fresh_hashes):
    """Приём всех выгрузок. files: [{'name', 'payload'} | {'name', 'error'}].

    → словарь: файлы (прочитаны / устарели / не разметка), жалобы, счётчики
    строк, категория каждой задачи и годные строки экзамена.
    """
    by_id = {c['id']: c for c in candidates}
    readable, not_review = [], []
    for f in files:
        if 'error' in f:
            not_review.append((f['name'], f['error']))
            continue
        try:
            validate_review(f['payload'], by_id)
        except ValueError as exc:
            not_review.append((f['name'], str(exc)))
            continue
        readable.append(f)
    fresh, stale = pick_latest(readable)

    complaints, row_counts, reasons = [], Counter(), Counter()
    rows_by_id = defaultdict(dict)
    for f in fresh:
        good, bad = validate_review(f['payload'], by_id)
        complaints += [dict(c, file=f['name']) for c in bad]
        who = str(f['payload'].get('reviewer') or '').strip()
        for row in good:
            row_counts[row['verdict']] += 1
            if row['verdict'] == 'bad':
                reasons[row.get('reason')] += 1
            # Повтор id в одном файле — берётся последняя строка.
            rows_by_id[row['id']][reviewer_key(who)] = (who, row)

    status, detail, good_rows = {}, {}, {}
    for c in candidates:
        rows = sorted(rows_by_id.get(c['id'], {}).values(), key=lambda r: reviewer_key(r[0]))
        category, extra = classify(c, rows, fresh_hashes.get(c['id']))
        status[c['id']] = category
        if category == GOOD:
            good_rows[c['id']] = extra
        elif extra is not None:
            detail[c['id']] = extra
    return {'read': [f['name'] for f in fresh], 'stale': [f['name'] for f in stale],
            'not_review': not_review, 'complaints': complaints,
            'rows': row_counts, 'reasons': reasons, 'status': status,
            'detail': detail, 'good': good_rows}


def assemble(candidates, safe_ids, good_rows):
    """Сейф, рабочий набор, черновик. Годные из safe_ids в работу не идут."""
    safe_set = set(safe_ids)
    reserve = reserve_chunk(candidates)
    safe = [good_rows[pk] for pk in safe_ids if pk in good_rows][:SAFE_SIZE]
    outside = sorted((r for pk, r in good_rows.items() if pk not in safe_set),
                     key=lambda r: (r['chunk'] == reserve, r['chunk'], r['n']))
    work = outside[:WORK_SIZE]
    final = len(safe) == SAFE_SIZE and len(work) == WORK_SIZE
    return {'final': final, 'safe': safe if final else [],
            'work': work if final else [], 'draft': [] if final else outside,
            'safe_good': len([pk for pk in safe_ids if pk in good_rows]),
            'outside_good': len(outside)}


def chunks_reviewed(candidates, status, chunks):
    """Все кандидаты этих пачек получили хоть одну годную строку."""
    return all(status[c['id']] != UNREVIEWED for c in candidates if c['chunk'] in chunks)


def invariants(candidates, safe_ids, accepted, built):
    safe_ids_set = set(safe_ids)
    safe = {r['id'] for r in built['safe']}
    work = [r['id'] for r in built['work']]
    draft = [r['id'] for r in built['draft']]
    every = [r['id'] for r in built['safe']] + work + draft
    counts = Counter(accepted['status'].values())
    return {
        'сейф ∩ рабочий': len(safe & set(work)),
        'safe_candidates ∩ черновик': len(safe_ids_set & set(draft)),
        'safe_candidates ∩ рабочий': len(safe_ids_set & set(work)),
        'повторов id': len(every) - len(set(every)),
        'сумма категорий': sum(counts[c] for c in CATEGORIES),
        'кандидатов': len(candidates),
    }


def dump_rows(rows):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n'
                   for r in rows).encode('utf-8')


# ── BUILD.md ────────────────────────────────────────────────────────────

def _by_section(rows):
    return dict(sorted(Counter(r['section'] for r in rows).items()))


def build_report(candidates, safe_info, accepted, built, inv, today):
    """Текст BUILD.md. Папка вне репозитория — id здесь писать можно."""
    counts = Counter(accepted['status'].values())
    reserve = reserve_chunk(candidates)
    main_chunks = sorted({c['chunk'] for c in candidates if c['chunk'] != reserve})
    lines = ['# Сборка экзамена v0', '', 'Дата: %s · seed сейфа: %s' % (today, safe_info['seed']), '']
    if not accepted['read'] and not accepted['stale'] and not accepted['not_review']:
        lines += ['**Разметки нет** — папка reviews_in пуста.', '']

    lines += ['## Файлы', '',
              '- прочитано: %d' % len(accepted['read'])]
    lines += ['  - %s' % name for name in accepted['read']]
    lines.append('- устарели (есть выгрузка того же человека и пачки позже): %d'
                 % len(accepted['stale']))
    lines += ['  - %s' % name for name in accepted['stale']]
    lines.append('- не разметка: %d' % len(accepted['not_review']))
    lines += ['  - %s — %s' % item for item in accepted['not_review']]

    rows = accepted['rows']
    lines += ['', '## Строки разметки', '',
              '- ok: %d' % rows['ok'],
              '- bad: %d%s' % (rows['bad'], (' (%s)' % ', '.join(
                  '%s %d' % kv for kv in sorted(accepted['reasons'].items())))
                  if rows['bad'] else ''),
              '- skip: %d' % rows['skip'],
              '- жалоб: %d' % len(accepted['complaints'])]
    for c in accepted['complaints']:
        lines.append('  - %s · id %s · %s — %s' % (c['file'], c['id'], c['kind'], c['text']))

    lines += ['', '## Задачи по категориям', '']
    lines += ['- %s: %d' % (cat, counts[cat]) for cat in CATEGORIES]
    conflicts = [pk for pk, cat in accepted['status'].items() if cat == CONFLICT]
    if conflicts:
        lines += ['', '### Конфликты (решает владелец правкой файлов)', '']
        for pk in sorted(conflicts):
            lines.append('- id %s: %s' % (pk, '; '.join(
                '%s — %s%s' % (who, verdict, (' (%s)' % reason) if reason else '')
                for who, verdict, reason in accepted['detail'][pk])))
    changed = [pk for pk, cat in accepted['status'].items() if cat == HASH_CHANGED]
    if changed:
        lines += ['', '### Условие поменялось после проверки', '']
        lines += ['- id %s: %s' % (pk, accepted['detail'][pk]) for pk in sorted(changed)]

    lines += ['', '## Итог', '']
    if built['final']:
        lines += ['**ФИНАЛ**: exam.jsonl — %d, safe.jsonl — %d.'
                  % (len(built['work']), len(built['safe'])), '',
                  'Рабочий набор по блокам: %s' % _by_section(built['work']),
                  'Сейф по блокам: %s' % _by_section(built['safe'])]
        spare = built['outside_good'] - len(built['work'])
        if spare:
            lines.append('Годных вне сейфа сверх %d: %d (в экзамен не вошли).' % (WORK_SIZE, spare))
    else:
        lines += ['**ЧЕРНОВИК**: exam_draft.jsonl — %d задач (все годные вне safe_candidates). '
                  'Сейф не собирается.' % len(built['draft']), '',
                  'До финала не хватает: в рабочем наборе %d из %d, годных в сейфе %d из %d.'
                  % (min(built['outside_good'], WORK_SIZE), WORK_SIZE,
                     min(built['safe_good'], SAFE_SIZE), SAFE_SIZE),
                  'Черновик по блокам: %s' % _by_section(built['draft']),
                  'Годные кандидаты сейфа по блокам: %s' % _by_section(
                      [r for pk, r in accepted['good'].items() if pk in set(safe_info['ids'])])]
        if (built['safe_good'] < SAFE_SIZE
                and chunks_reviewed(candidates, accepted['status'], main_chunks)):
            lines += ['', '## ⚠️ НУЖНО РЕШЕНИЕ ВЛАДЕЛЬЦА', '',
                      'Пачки %s проверены целиком, а годных среди кандидатов сейфа %d < %d. '
                      'Финал не собирается.' % (main_chunks, built['safe_good'], SAFE_SIZE)]

    lines += ['', '## Инварианты', '']
    lines += ['- %s: %s' % kv for kv in inv.items()]
    return '\n'.join(lines) + '\n'
