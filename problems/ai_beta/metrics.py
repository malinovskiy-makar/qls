"""Цифры беты ИИ — чистые функции (сессия «Данные беты 1», 08.10.2026).

К базе не обращаются: команда `ai_beta_report` читает строки в обычные
словари и отдаёт их сюда. Так каждую цифру можно проверить на выдуманных
данных, а отчёт — пересчитать без копии боя.

⚠️ ЧЕЛОВЕК ВЕЗДЕ — НОМЕРОМ. Сюда не приходят ни имя, ни логин, ни почта;
тексты реплик приходят только ради счётчиков (испорченная формула, длина
ответа, число из ответа банка) и наружу не выходят.

Сутки и недели — по московскому времени (UTC+3 без перехода, как с 2014 г.).

Строки на входе (`data`):
  users  — {id, is_staff, is_superuser, role, date_joined}
  events — {user_id, ts, name, problem_id}; клик «Спросить ИИ» команда
           отдаёт под именем `ai_open`
  turns  — {id, user_id, problem_id, thread, mode, created_at, latency_ms,
           cost_usd (Decimal), input_tokens, output_tokens, vision_in,
           vision_out, vision_text, reply, error, files: [{mime, pages}]}
  ai     — {kind, user_id, created_at, seconds, ok, cost_usd, input_tokens,
           output_tokens, reasoning_tokens}
  search — {user_id, ts, status, ms, rating}
  solves — {user_id, problem_id, ts}; opened — {(user_id, problem_id)}
  topics — {problem_id: [название темы]}
"""
import math
import re
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from decimal import Decimal

MSK = timezone(timedelta(hours=3), 'MSK')

SLICES = (('all', 'все'), ('no_staff', 'без сотрудников'))
MODES = ('free', 'theory', 'method', 'check')

#: Виды потерь реплики, в порядке таблицы отчёта.
ERROR_KINDS = (
    ('personal_limit', 'личный лимит'),
    ('cost_cap', 'дневной потолок расходов'),
    ('format', 'сбой формата («неожиданный ответ»)'),
    ('empty', 'пустой ответ'),
    ('timeout', 'обрыв по времени'),
    ('network', 'связь'),
    ('other', 'прочее'),
)

#: Ответ дольше этого — «долгий» (секунды).
SLOW_SECONDS = 20
#: Длина ответа от этой доли потолка — «упёрся в потолок».
NEAR_CAP = 0.99

# ─── Время ─────────────────────────────────────────────────────────────────


def msk_day(dt):
    return dt.astimezone(MSK).date()


def week_start(dt):
    """Понедельник московской недели, в которую попал момент."""
    day = msk_day(dt)
    return day - timedelta(days=day.weekday())


# ─── Распределения ─────────────────────────────────────────────────────────


def percentile(values, p):
    """Перцентиль методом ближайшего ранга: элемент с номером ⌈p·n/100⌉.

    Без интерполяции: каждое число отчёта — значение, которое реально было.
    Пустой список → None.
    """
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(1, -(-(p * len(ordered)) // 100))
    return ordered[int(rank) - 1]


def dist(values):
    """n, медиана, P75, P90, P99, максимум и среднее одним словарём."""
    values = list(values)
    return {
        'n': len(values),
        'median': percentile(values, 50), 'p75': percentile(values, 75),
        'p90': percentile(values, 90), 'p99': percentile(values, 99),
        'max': max(values) if values else None,
        'mean': (sum(values) / len(values)) if values else None,
    }


def share(part, whole):
    return (part / whole) if whole else None


# ─── Одновременность ───────────────────────────────────────────────────────


def _sweep(intervals):
    """(момент, уровень, начало?) по возрастанию времени.

    ⚠️ При равных моментах конец идёт РАНЬШЕ начала: вызов, кончившийся в
    10 с, и вызов, начавшийся в 10 с, не пересекаются. Нулевые отрезки
    (вызов без длительности) выбрасываются — иначе свой же конец шёл бы
    раньше своего начала.
    """
    points = []
    for start, end in intervals:
        if end > start:
            points.append((end, 0))
            points.append((start, 1))
    points.sort()
    level = 0
    for moment, is_start in points:
        level += 1 if is_start else -1
        yield moment, level, bool(is_start)


def max_concurrency(intervals):
    """Наибольшее число отрезков [начало, конец], идущих одновременно."""
    return max((level for _m, level, _s in _sweep(intervals)), default=0)


def concurrency_episodes(intervals, k):
    """Моменты, когда одновременных вызовов СТАЛО k (поднялось с k−1 до k)."""
    return [moment for moment, level, is_start in _sweep(intervals)
            if is_start and level == k]


# ─── Ошибки и ответы ───────────────────────────────────────────────────────


def error_kind(error, latency_ms=None, timeout_ms=None):
    """Вид потери по тексту `ChatTurn.error` («вид: текст»). Пусто → None.

    У GLM обрыв по времени приходит тем же текстом, что и обрыв связи
    (таймаут библиотеки — подкласс ошибки соединения), поэтому «связь»,
    длившаяся до потолка времени (без секунды), считается обрывом по времени.
    """
    text = (error or '').strip()
    if not text:
        return None
    if 'лимит обращений' in text:
        return 'personal_limit'
    if 'бюджет' in text:
        return 'cost_cap'
    if 'неожиданный ответ' in text:
        return 'format'
    if 'Помощник не ответил' in text:
        return 'empty'
    if 'занял больше' in text or 'прерван' in text:
        return 'timeout'
    if 'связаться' in text:
        if latency_ms and timeout_ms and latency_ms >= timeout_ms - 1000:
            return 'timeout'
        return 'network'
    return 'other'


#: След TeX-команд, съеденных JSON-экранированием: \b, \f — сами символы,
#: \t и \r — перед хвостами \times, \text, \theta, \tau, \right, \rho, \rangle.
_BROKEN_RE = re.compile(r'[\x08\x0c]|\t(?:imes|ext\{|heta|au)|\r(?:ight|ho|angle)')


def is_broken_formula(text):
    """Испорчена ли формула в ответе: \\frac, \\times, \\beta, \\right в JSON
    превратились в служебные символы. Обычный перенос строки — не порча."""
    return bool(_BROKEN_RE.search(text or ''))


def near_cap(reply, cap):
    """Ответ длиной от 0,99 потолка — скорее всего обрезан предохранителем."""
    return bool(reply) and len(reply) >= NEAR_CAP * cap


# ─── Сотрудники ────────────────────────────────────────────────────────────


def read_team_ids(lines):
    """Номера из файла команды: номер в строке, пустые и `#…` пропускаются."""
    ids = set()
    for line in lines:
        line = line.split('#', 1)[0].strip()
        if line:
            ids.add(int(line))
    return ids


def staff_ids(users, team_ids=()):
    """Сотрудник — is_staff или is_superuser, плюс номера из файла команды."""
    flagged = {u['id'] for u in users if u.get('is_staff') or u.get('is_superuser')}
    return flagged | set(team_ids)


def without(rows, excluded, key='user_id'):
    """Строки без людей из `excluded`. Гость (номер пуст) остаётся."""
    return [row for row in rows if row.get(key) is None or row[key] not in excluded]


def sliced(data, excluded):
    """Те же данные без людей из `excluded` — срез «без сотрудников»."""
    return {
        'users': [u for u in data['users'] if u['id'] not in excluded],
        'events': without(data['events'], excluded),
        'turns': without(data['turns'], excluded),
        'ai': without(data['ai'], excluded),
        'search': without(data['search'], excluded),
        'solves': without(data['solves'], excluded),
        'opened': {pair for pair in data['opened'] if pair[0] not in excluded},
        'topics': data['topics'],
    }


# ─── Блоки отчёта ──────────────────────────────────────────────────────────


def _money(value):
    return float(value) if value is not None else None


def block_a(d):
    """Охват: активные за неделю, доля написавших в чат, возвраты, воронка."""
    active, chat = defaultdict(set), defaultdict(set)
    for e in d['events']:
        if e['user_id'] is not None:
            active[week_start(e['ts'])].add(e['user_id'])
    for t in d['turns']:
        chat[week_start(t['created_at'])].add(t['user_id'])
    weeks = []
    for week in sorted(set(active) | set(chat)):
        wrote = chat[week] & active[week]
        weeks.append({'week': week.isoformat(), 'active': len(active[week]),
                      'chat_users': len(chat[week]), 'wrote_active': len(wrote),
                      'share': share(len(wrote), len(active[week]))})
    ever_active = set().union(*active.values()) if active else set()
    ever_chat = {t['user_id'] for t in d['turns']}
    days = defaultdict(set)
    for t in d['turns']:
        days[t['user_id']].add(msk_day(t['created_at']))
    returned = sum(1 for u in ever_chat if len(days[u]) > 1)
    opened = {e['user_id'] for e in d['events']
              if e['name'] == 'problem_open' and e['user_id'] is not None}
    ai_open = {e['user_id'] for e in d['events']
               if e['name'] == 'ai_open' and e['user_id'] is not None}
    return {
        'weeks': weeks,
        'ever_active': len(ever_active), 'ever_chat': len(ever_chat),
        'ever_share': share(len(ever_chat & ever_active), len(ever_active)),
        'returned': returned, 'returned_share': share(returned, len(ever_chat)),
        'funnel': {'opened_problem': len(opened),
                   'opened_ai': len(ai_open & opened),
                   'wrote': len(ever_chat & ai_open & opened),
                   'wrote_any': len(ever_chat)},
    }


def block_b(d, staff=frozenset()):
    """Нагрузка: реплик на человека в неделю, самые активные, длина разговора."""
    per_week = Counter((t['user_id'], week_start(t['created_at'])) for t in d['turns'])
    per_user = Counter(t['user_id'] for t in d['turns'])
    threads = Counter(t['thread'] or 'turn-%s' % t['id'] for t in d['turns'])
    sizes = list(threads.values())
    return {
        'per_user_week': dist(per_week.values()),
        'top_users': [{'user_id': u, 'turns': n, 'staff': u in staff}
                      for u, n in sorted(per_user.items(), key=lambda x: (-x[1], x[0]))[:10]],
        'thread_sizes': dist(sizes),
        'thread_size_counts': {str(k): v for k, v in sorted(Counter(sizes).items())},
        'single_share': share(sum(1 for s in sizes if s == 1), len(sizes)),
        'threads': len(sizes),
    }


def block_c(d):
    """Режимы и фото."""
    turns = d['turns']
    users = {t['user_id'] for t in turns}
    by_mode = Counter(t['mode'] for t in turns)
    people = defaultdict(set)
    for t in turns:
        people[t['mode']].add(t['user_id'])
    with_files = [t for t in turns if t['files']]
    mimes = Counter(f['mime'] for t in with_files for f in t['files'])
    return {
        'modes': {m: {'turns': by_mode.get(m, 0), 'turn_share': share(by_mode.get(m, 0), len(turns)),
                      'people': len(people[m]), 'people_share': share(len(people[m]), len(users))}
                  for m in MODES},
        'turns': len(turns), 'users': len(users),
        'file_turns': len(with_files), 'file_share': share(len(with_files), len(turns)),
        'pages_per_file_turn': dist(sum(f['pages'] for f in t['files']) for t in with_files),
        'mimes': dict(mimes.most_common()),
        'empty_vision': sum(1 for t in with_files if not (t['vision_text'] or '').strip()),
        'empty_vision_share': share(
            sum(1 for t in with_files if not (t['vision_text'] or '').strip()), len(with_files)),
        'file_users': len({t['user_id'] for t in with_files}),
    }


def block_d(d, reply_max, check_reply_max, timeout_ms=None):
    """Потери: виды ошибок, частые тексты, испорченные формулы, ответы у потолка."""
    turns = d['turns']
    kinds = Counter(error_kind(t['error'], t['latency_ms'], timeout_ms) for t in turns)
    texts = Counter(t['error'].strip() for t in turns if (t['error'] or '').strip())
    replies = [t for t in turns if (t['reply'] or '').strip()]
    broken = sum(1 for t in replies if is_broken_formula(t['reply']))
    capped = sum(1 for t in replies
                 if near_cap(t['reply'], check_reply_max if t['mode'] == 'check' else reply_max))
    return {
        'turns': len(turns),
        'errors': sum(v for k, v in kinds.items() if k),
        'error_share': share(sum(v for k, v in kinds.items() if k), len(turns)),
        'kinds': {k: {'n': kinds.get(k, 0), 'share': share(kinds.get(k, 0), len(turns))}
                  for k, _label in ERROR_KINDS},
        'top_texts': [{'text': text, 'n': n} for text, n in texts.most_common(10)],
        'replies': len(replies),
        'broken': broken, 'broken_share': share(broken, len(replies)),
        'near_cap': capped, 'near_cap_share': share(capped, len(replies)),
    }


def _price(prices, model):
    row = prices[model]
    return (Decimal(str(row[0])), Decimal(str(row[-1])))


def block_e(d, prices, chat_model='glm-5.3', vision_model='glm-5.3-flash',
            flash_model='glm-5.3-flash'):
    """Время и деньги чата; пересчёт тех же токенов на Flash."""
    turns = d['turns']
    ok = [t for t in turns if not (t['error'] or '').strip()]
    latency = {m: dist(t['latency_ms'] / 1000 for t in ok if t['mode'] == m) for m in MODES}
    latency['all'] = dist(t['latency_ms'] / 1000 for t in ok)
    latency['with_files'] = dist(t['latency_ms'] / 1000 for t in ok if t['files'])
    latency['without_files'] = dist(t['latency_ms'] / 1000 for t in ok if not t['files'])
    slow = sum(1 for t in ok if t['latency_ms'] > SLOW_SECONDS * 1000)
    costs = [t['cost_usd'] for t in turns]
    total = sum(costs, Decimal(0))
    per_day = defaultdict(Decimal)
    for t in turns:
        per_day[msk_day(t['created_at'])] += t['cost_usd']
    cap_days = sorted({msk_day(t['created_at']).isoformat() for t in turns
                       if error_kind(t['error']) == 'cost_cap'})
    chat_in, chat_out = _price(prices, chat_model)
    vis_in, vis_out = _price(prices, vision_model)
    fl_in, fl_out = _price(prices, flash_model)
    million = Decimal(10 ** 6)
    tokens_in = sum(t['input_tokens'] for t in turns)
    tokens_out = sum(t['output_tokens'] for t in turns)
    vis_tin = sum(t['vision_in'] for t in turns)
    vis_tout = sum(t['vision_out'] for t in turns)
    vision_cost = (vis_tin * vis_in + vis_tout * vis_out) / million
    now_by_table = (tokens_in * chat_in + tokens_out * chat_out) / million + vision_cost
    flash = (tokens_in * fl_in + tokens_out * fl_out) / million + vision_cost
    chat_ai = [a for a in d['ai'] if a['kind'] == 'catalog_chat']
    return {
        'latency': latency, 'ok_turns': len(ok),
        'slow': slow, 'slow_share': share(slow, len(ok)),
        'cost': {'n': len(costs), 'total': str(total),
                 'median': _money(percentile(costs, 50)), 'p90': _money(percentile(costs, 90)),
                 'mean': _money(total / len(costs)) if costs else None},
        'tokens': {'input': tokens_in, 'output': tokens_out,
                   'vision_input': vis_tin, 'vision_output': vis_tout,
                   'reasoning': sum(a['reasoning_tokens'] for a in chat_ai),
                   'per_turn_input': dist(t['input_tokens'] for t in turns),
                   'per_turn_output': dist(t['output_tokens'] for t in turns)},
        'per_day': {day.isoformat(): float(v) for day, v in sorted(per_day.items())},
        'max_day': float(max(per_day.values(), default=Decimal(0))),
        'cap_days': cap_days,
        'flash': {'now_by_table': float(now_by_table), 'flash': float(flash),
                  'flash_per_turn': float(flash / len(turns)) if turns else None,
                  'ratio': float(flash / now_by_table) if now_by_table else None},
        'ai_log_cost': float(sum((a['cost_usd'] for a in chat_ai), Decimal(0))),
        'ai_log_calls': len(chat_ai),
    }


def _intervals(rows):
    return [(r['created_at'].timestamp() - r['seconds'], r['created_at'].timestamp())
            for r in rows]


def _concurrency(rows):
    intervals = _intervals(rows)
    hours = Counter()
    for moment in concurrency_episodes(intervals, 3):
        hours[(int(moment // 3600) + 3) % 24] += 1
    return {'calls': len(rows), 'max': max_concurrency(intervals),
            'episodes_2': len(concurrency_episodes(intervals, 2)),
            'episodes_3': len(concurrency_episodes(intervals, 3)),
            'episodes_4': len(concurrency_episodes(intervals, 4)),
            'hours_3': {str(h): n for h, n in sorted(hours.items())}}


def block_f(d):
    """Одновременность вызовов ИИ: все виды работ и только чат."""
    return {'all_kinds': _concurrency(d['ai']),
            'chat': _concurrency([a for a in d['ai'] if a['kind'] == 'catalog_chat']),
            'kinds': dict(Counter(a['kind'] for a in d['ai']).most_common())}


def block_g(d):
    """После чата: доля пар «ученик–задача», где задачу потом решили."""
    first_chat = {}
    for t in d['turns']:
        if t['problem_id'] is None:
            continue
        key = (t['user_id'], t['problem_id'])
        if key not in first_chat or t['created_at'] < first_chat[key]:
            first_chat[key] = t['created_at']
    solved = defaultdict(list)
    for s in d['solves']:
        solved[(s['user_id'], s['problem_id'])].append(s['ts'])
    after = sum(1 for key, ts in first_chat.items() if any(x > ts for x in solved[key]))
    plain = d['opened'] - set(first_chat)
    plain_solved = sum(1 for key in plain if solved[key])
    return {'chat_pairs': len(first_chat), 'chat_solved_after': after,
            'chat_share': share(after, len(first_chat)),
            'plain_pairs': len(plain), 'plain_solved': plain_solved,
            'plain_share': share(plain_solved, len(plain))}


def block_h(d, cap_usd=None):
    """Умный поиск: запросы, переранжирование, оценки, время, цена, потолок."""
    rows = d['search']
    rerank = [r for r in rows if r['status'] == 'rerank']
    rated = Counter(r['rating'] for r in rows if r['rating'])
    ai = [a for a in d['ai'] if a['kind'] == 'search_rerank']
    cost = sum((a['cost_usd'] for a in ai), Decimal(0))
    per_day = defaultdict(Decimal)
    for a in ai:
        per_day[msk_day(a['created_at'])] += a['cost_usd']
    cap_days = sorted(day.isoformat() for day, v in per_day.items()
                      if cap_usd is not None and v >= Decimal(str(cap_usd)))
    quota_days = sorted({msk_day(r['ts']).isoformat() for r in rows if r['status'] == 'quota'})
    by_day = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        day = by_day[msk_day(r['ts']).isoformat()]
        day[0] += 1
        day[1] += r['status'] == 'fallback'
        day[2] += r['user_id'] is None
    return {
        'queries': len(rows), 'rerank': len(rerank), 'rerank_share': share(len(rerank), len(rows)),
        'statuses': dict(Counter(r['status'] or '—' for r in rows).most_common()),
        'rated_yes': rated.get('yes', 0), 'rated_no': rated.get('no', 0),
        'rated_share': share(sum(rated.values()), len(rows)),
        'ms_all': dist(r['ms'] for r in rows if r['ms'] is not None),
        'ms_rerank': dist(r['ms'] for r in rerank if r['ms'] is not None),
        'ai_calls': len(ai), 'ai_cost': float(cost),
        'cost_per_rerank': float(cost / len(rerank)) if rerank else None,
        'cost_per_call': dist(float(a['cost_usd']) for a in ai),
        'max_day': float(max(per_day.values())) if per_day else 0.0,
        'cap_days': cap_days, 'quota_days': quota_days,
        'guest_queries': sum(1 for r in rows if r['user_id'] is None),
        'per_day': {day: {'queries': v[0], 'fallback': v[1], 'guest': v[2]}
                    for day, v in sorted(by_day.items())},
    }


def block_i(d):
    """Темы и задачи, по которым спрашивают чаще всего."""
    topic_turns, topic_people = Counter(), defaultdict(set)
    problems, problem_people = Counter(), defaultdict(set)
    for t in d['turns']:
        if t['problem_id'] is None:
            continue
        problems[t['problem_id']] += 1
        problem_people[t['problem_id']].add(t['user_id'])
        for name in d['topics'].get(t['problem_id'], ()):
            topic_turns[name] += 1
            topic_people[name].add(t['user_id'])
    return {
        'topics': [{'topic': name, 'turns': n, 'people': len(topic_people[name])}
                   for name, n in topic_turns.most_common(10)],
        'problems': [{'problem_id': pid, 'turns': n, 'people': len(problem_people[pid])}
                     for pid, n in sorted(problems.items(), key=lambda x: (-x[1], x[0]))[:20]],
        'without_topic': sum(1 for t in d['turns']
                             if t['problem_id'] is not None and not d['topics'].get(t['problem_id'])),
    }


def block_j(d, e_block, f_block, role='student'):
    """Одна таблица для юнит-экономики."""
    students = {u['id'] for u in d['users'] if u.get('role') == role}
    active = defaultdict(set)
    for e in d['events']:
        if e['user_id'] in students:
            active[week_start(e['ts'])].add(e['user_id'])
    asked = Counter((t['user_id'], week_start(t['created_at']))
                    for t in d['turns'] if t['user_id'] in students)
    per_active = [asked.get((u, week), 0) for week, people in active.items() for u in people]
    chat_students = {t['user_id'] for t in d['turns'] if t['user_id'] in students}
    photo_students = {t['user_id'] for t in d['turns'] if t['user_id'] in students and t['files']}
    return {
        'questions_per_active_student_week': dist(per_active),
        'student_weeks': len(per_active),
        'chat_students': len(chat_students), 'photo_students': len(photo_students),
        'photo_share': share(len(photo_students), len(chat_students)),
        'cost_now_median': e_block['cost']['median'], 'cost_now_mean': e_block['cost']['mean'],
        'cost_flash_mean': e_block['flash']['flash_per_turn'],
        'max_concurrency_all': f_block['all_kinds']['max'],
        'max_concurrency_chat': f_block['chat']['max'],
    }


def problem_keys(answers, statements):
    """Ключи задачи для блока K: [(число, допуск, проценты?)].

    Берутся ответы банка (задачи и пунктов), у которых `propose_key` даёт
    вид `exact`. Число, которое есть в самом условии, ключом не считается:
    его назовёт и честный помощник, пересказывая задачу.
    """
    from problems.ai_exam import numbers

    in_statement = set()
    for text in statements:
        in_statement.update(numbers.find_numbers(text or ''))
    keys = []
    for answer in answers:
        key = numbers.propose_key(answer)
        if key['kind'] != 'exact':
            continue
        value = numbers.to_number(key['value'])
        if value is None or value in in_statement:
            continue
        keys.append((value, numbers.default_tol(key['value']), key['percent']))
    return keys


def reply_has_key(reply, keys):
    """Встречается ли в ответе число из ответа банка (с допуском ключа)."""
    from problems.ai_exam import numbers

    found = numbers.find_numbers(reply or '')
    for value, tol, percent in keys:
        for got in found:
            if abs(got - value) <= tol or (percent and abs(got * 100 - value) <= tol):
                return True
    return False


def block_k(d, keys_by_problem, modes=('method', 'free')):
    """Грубая оценка «выдал ответ»: число из ответа банка в ответе помощника."""
    result = {}
    for mode in modes + ('both',):
        wanted = modes if mode == 'both' else (mode,)
        pool = [t for t in d['turns'] if t['mode'] in wanted and (t['reply'] or '').strip()
                and keys_by_problem.get(t['problem_id'])]
        hits = sum(1 for t in pool if reply_has_key(t['reply'], keys_by_problem[t['problem_id']]))
        replies = sum(1 for t in d['turns'] if t['mode'] in wanted and (t['reply'] or '').strip())
        result[mode] = {'replies': replies, 'with_key': len(pool), 'hits': hits,
                        'share': share(hits, len(pool))}
    return result
