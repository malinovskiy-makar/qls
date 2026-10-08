# -*- coding: utf-8 -*-
"""`ai_beta_report` — цифры беты по ИИ-чату и умному поиску (08.10.2026).

Шаг 0 настройки ИИ: прежде чем менять чат и выбирать модель, заменить
допущения цифрами — охват, нагрузка, режимы и фото, потери, время и деньги,
одновременность, темы. Опись копии, блоки A–K и таблица для юнит-экономики.
Определения и правила — docs/AI_BETA.md, расчёты — `problems/ai_beta/metrics.py`.

Команда ТОЛЬКО ЧИТАЕТ базу. Запускается на копии боя:
    DATABASE_URL=postgres://…/weco_beta_20261007 manage.py ai_beta_report \\
        --settings=config.settings_test_pg --out C:/Users/…/beta_20261007

⚠️ ДАННЫЕ ЛЮДЕЙ. Ни имя, ни логин, ни почта, ни телефон не читаются:
человек — номером. Тексты реплик читаются ради счётчиков и в отчёт не
попадают; в отчёт идут только тексты ошибок системы. Файлы пишутся в папку
вне репозитория — в git они не попадают.
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max, Min, Q

from problems.ai import core
from problems.ai_beta import metrics as m

REPORT = 'BETA_REPORT.md'
NUMBERS = 'beta_numbers.json'
TEAM_FILE = 'team_user_ids.txt'
#: Клик, открывающий чат в панели помощи: «Спросить ИИ» в лестнице и на
#: полоске, «Спросить ИИ, почему так» под тестом. Подпись кнопки — текст
#: интерфейса, текст человека здесь не читается: фильтр идёт в базе.
AI_OPEN_PREFIX = 'Спросить ИИ'


def _day(value, end=False):
    try:
        day = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=m.MSK)
    except ValueError:
        raise CommandError('Дата — ГГГГ-ММ-ДД, получено: %r' % value)
    return day + timedelta(days=1) if end else day


def _window(qs, field, since, until):
    if since:
        qs = qs.filter(**{field + '__gte': since})
    if until:
        qs = qs.filter(**{field + '__lt': until})
    return qs


def _pid(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ─── Чтение копии ──────────────────────────────────────────────────────────

def load(since=None, until=None):
    """Строки базы → обычные словари (см. шапку `metrics`)."""
    from problems.models import CatalogAttempt, Problem, ProblemPart, User
    from problems.models_platform import (
        AiUsageLog, ChatAttachment, ChatTurn, Event, LearningEvent, ProblemProgress,
        SearchLog,
    )

    users = [{'id': u['id'], 'is_staff': u['is_staff'], 'is_superuser': u['is_superuser'],
              'role': u['profile__role'], 'date_joined': u['date_joined']}
             for u in User.objects.values('id', 'is_staff', 'is_superuser',
                                          'profile__role', 'date_joined')]

    events_qs = _window(Event.objects.filter(user__isnull=False), 'ts', since, until)
    ai_open = set(events_qs.filter(name='click', props__text__startswith=AI_OPEN_PREFIX)
                  .values_list('pk', flat=True))
    events = []
    for e in events_qs.values('pk', 'user_id', 'ts', 'name', 'props__problem_id').iterator():
        events.append({'user_id': e['user_id'], 'ts': e['ts'],
                       'name': 'ai_open' if e['pk'] in ai_open else e['name'],
                       'problem_id': _pid(e['props__problem_id'])})

    turns = {}
    for t in (_window(ChatTurn.objects.all(), 'created_at', since, until)
              .order_by('created_at', 'pk')
              .values('id', 'user_id', 'problem_id', 'thread', 'mode', 'created_at',
                      'latency_ms', 'cost_usd', 'input_tokens', 'output_tokens',
                      'vision_input_tokens', 'vision_output_tokens', 'vision_text',
                      'reply', 'error', 'attachment_id')):
        turns[t['id']] = {
            'id': t['id'], 'user_id': t['user_id'], 'problem_id': t['problem_id'],
            'thread': str(t['thread']) if t['thread'] else None, 'mode': t['mode'],
            'created_at': t['created_at'], 'latency_ms': t['latency_ms'],
            'cost_usd': t['cost_usd'], 'input_tokens': t['input_tokens'],
            'output_tokens': t['output_tokens'], 'vision_in': t['vision_input_tokens'],
            'vision_out': t['vision_output_tokens'], 'vision_text': t['vision_text'],
            'reply': t['reply'], 'error': t['error'], 'files': [],
            '_first': t['attachment_id']}
    # Вложения: новое поле (до трёх) и старое `attachment` для реплик до 18.09.
    links = {}
    for row in (ChatTurn.attachments.through.objects
                .filter(chatturn_id__in=list(turns)).values('chatturn_id', 'chatattachment_id')):
        links.setdefault(row['chatturn_id'], set()).add(row['chatattachment_id'])
    for turn in turns.values():
        if turn['_first']:
            links.setdefault(turn['id'], set()).add(turn.pop('_first'))
        turn.pop('_first', None)
    att = {a['id']: a for a in ChatAttachment.objects.values('id', 'mime', 'pages')}
    for turn_id, ids in links.items():
        turns[turn_id]['files'] = [{'mime': att[i]['mime'], 'pages': att[i]['pages']}
                                   for i in sorted(ids) if i in att]

    ai = [{'kind': a['kind'], 'user_id': a['user_id'], 'created_at': a['created_at'],
           'seconds': a['seconds'] or 0, 'ok': a['ok'], 'cost_usd': a['cost_usd'],
           'input_tokens': a['input_tokens'], 'output_tokens': a['output_tokens'],
           'reasoning_tokens': a['reasoning_tokens']}
          for a in _window(AiUsageLog.objects.all(), 'created_at', since, until).values(
              'kind', 'user_id', 'created_at', 'seconds', 'ok', 'cost_usd',
              'input_tokens', 'output_tokens', 'reasoning_tokens')]

    search = list(_window(SearchLog.objects.all(), 'ts', since, until)
                  .values('user_id', 'ts', 'status', 'ms', 'rating'))

    solves = []
    for row in _window(ProblemProgress.objects.filter(
            status__in=('solved_self', 'solved_hint')), 'updated_at', since, until).values(
            'user_id', 'problem_id', 'updated_at'):
        solves.append({'user_id': row['user_id'], 'problem_id': row['problem_id'],
                       'ts': row['updated_at']})
    for row in _window(CatalogAttempt.objects.filter(verdict='ok'), 'created_at',
                       since, until).values('user_id', 'problem_id', 'created_at'):
        solves.append({'user_id': row['user_id'], 'problem_id': row['problem_id'],
                       'ts': row['created_at']})
    for row in events_qs.filter(name='test_answer', props__correct=True).values(
            'user_id', 'ts', 'props__problem_id'):
        if _pid(row['props__problem_id']):
            solves.append({'user_id': row['user_id'], 'problem_id': _pid(row['props__problem_id']),
                           'ts': row['ts']})
    for row in _window(LearningEvent.objects.filter(
            event_type='solved', user__isnull=False, catalog_problem__isnull=False),
            'created_at', since, until).values('user_id', 'catalog_problem_id', 'created_at'):
        solves.append({'user_id': row['user_id'], 'problem_id': row['catalog_problem_id'],
                       'ts': row['created_at']})
    opened = set(_window(ProblemProgress.objects.all(), 'updated_at', since, until)
                 .values_list('user_id', 'problem_id'))
    opened |= {(e['user_id'], e['problem_id']) for e in events
               if e['name'] == 'problem_open' and e['problem_id']}

    chat_problems = {t['problem_id'] for t in turns.values() if t['problem_id']}
    topics = {}
    for pid, name in (Problem.topics.through.objects.filter(problem_id__in=chat_problems)
                      .values_list('problem_id', 'topic__name')):
        topics.setdefault(pid, []).append(name)
    keys = {}
    texts = {p['id']: ([p['answer']], [p['statement']]) for p in
             Problem.objects.filter(id__in=chat_problems).values('id', 'answer', 'statement')}
    for part in ProblemPart.objects.filter(problem_id__in=chat_problems).values(
            'problem_id', 'answer', 'statement'):
        texts[part['problem_id']][0].append(part['answer'])
        texts[part['problem_id']][1].append(part['statement'])
    for pid, (answers, statements) in texts.items():
        keys[pid] = m.problem_keys(answers, statements)

    data = {'users': users, 'events': events, 'turns': list(turns.values()), 'ai': ai,
            'search': search, 'solves': solves, 'opened': opened, 'topics': topics}
    return data, keys


def inventory():
    """Опись копии: число строк и первая/последняя дата по таблицам."""
    from problems.models import CatalogAttempt, User
    from problems.models_platform import (
        AiUsageLog, ChatAttachment, ChatTurn, Event, Feedback, LearningEvent,
        ProblemProgress, ProblemReport, SearchLog,
    )

    def span(qs, field):
        agg = qs.aggregate(n=Count('pk'), first=Min(field), last=Max(field))
        return {'n': agg['n'],
                'first': m.msk_day(agg['first']).isoformat() if agg['first'] else None,
                'last': m.msk_day(agg['last']).isoformat() if agg['last'] else None}

    tables = {
        'User': span(User.objects.all(), 'date_joined'),
        'ChatTurn': span(ChatTurn.objects.all(), 'created_at'),
        'ChatAttachment': span(ChatAttachment.objects.all(), 'created_at'),
        'AiUsageLog': span(AiUsageLog.objects.all(), 'created_at'),
        'Event': span(Event.objects.all(), 'ts'),
        'SearchLog': span(SearchLog.objects.all(), 'ts'),
        'CatalogAttempt': span(CatalogAttempt.objects.all(), 'created_at'),
        'ProblemProgress': span(ProblemProgress.objects.all(), 'updated_at'),
        'Feedback': span(Feedback.objects.all(), 'created_at'),
        'ProblemReport': span(ProblemReport.objects.all(), 'created_at'),
        'LearningEvent': span(LearningEvent.objects.all(), 'created_at'),
    }
    roles = Counter(User.objects.values_list('profile__role', flat=True))
    staff = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).count()
    weeks = Counter(m.week_start(d).isoformat()
                    for d in User.objects.values_list('date_joined', flat=True))
    ai_kinds = {row['kind']: span(AiUsageLog.objects.filter(kind=row['kind']), 'created_at')
                for row in AiUsageLog.objects.values('kind').distinct()}
    events = [{'name': row['name'], 'n': row['n'], 'people': row['people']}
              for row in Event.objects.values('name').annotate(
                  n=Count('pk'), people=Count('user', distinct=True)).order_by('-n', 'name')[:30]]
    feedback = dict(Counter(Feedback.objects.values_list('kind', flat=True)))
    learning = dict(Counter('%s/%s' % pair for pair in
                            LearningEvent.objects.values_list('source', 'event_type')))
    return {'tables': tables, 'roles': {str(k or '—'): v for k, v in roles.items()},
            'staff_flags': staff, 'signup_weeks': dict(sorted(weeks.items())),
            'ai_kinds': ai_kinds, 'events_top': events, 'feedback': feedback,
            'learning': learning}


# ─── Отчёт ────────────────────────────────────────────────────────────────

def pct(x):
    return '—' if x is None else ('%.1f %%' % (100 * x)).replace('.', ',')


def num(x, nd=1):
    if x is None:
        return '—'
    if isinstance(x, int):
        return '{:,}'.format(x).replace(',', ' ')
    return ('%.*f' % (nd, x)).replace('.', ',')


def usd(x, nd=4):
    return '—' if x is None else '$' + ('%.*f' % (nd, float(x))).replace('.', ',')


def dist_row(d, nd=1, fmt=None):
    fmt = fmt or (lambda v: num(v, nd))
    return '%s / %s / %s / %s (n=%s)' % (fmt(d['median']), fmt(d['p90']), fmt(d['p99']),
                                         fmt(d['max']), d['n'])


def table(header, rows):
    out = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    out += ['| ' + ' | '.join(str(c) for c in row) + ' |' for row in rows]
    return '\n'.join(out)


def two(blocks, rows):
    """Таблица «показатель | все | без сотрудников»."""
    return table(['Показатель', 'все', 'без сотрудников'],
                 [(label, fn(blocks['all']), fn(blocks['no_staff'])) for label, fn in rows])


def render(result):
    b = result['blocks']
    inv = result['inventory']
    lines = ['# Бета: ИИ-чат и умный поиск — цифры', '',
             'Копия боя %s. Окно: %s — %s (МСК). Создано командой `ai_beta_report`.'
             % (result['copy'], result['since'] or 'начало', result['until'] or 'конец'),
             'Сотрудников (флаги + файл команды): %d; файл команды: %s.'
             % (result['staff_count'], result['team_file'] or 'нет'), '',
             'Определения — docs/AI_BETA.md. Перцентили — ближайший ранг; '
             'распределение пишется как «медиана / P90 / P99 / максимум (n)».', '',
             '## Опись копии', '',
             table(['Таблица', 'строк', 'первая дата', 'последняя дата'],
                   [(k, num(v['n']), v['first'] or '—', v['last'] or '—')
                    for k, v in inv['tables'].items()]), '',
             'Пользователи по ролям: %s; с флагом is_staff/is_superuser: %d.'
             % (', '.join('%s %d' % kv for kv in sorted(inv['roles'].items())), inv['staff_flags']),
             '', 'Регистрации по неделям (понедельник): ' + ', '.join(
                 '%s — %d' % kv for kv in inv['signup_weeks'].items()), '',
             table(['AiUsageLog: вид', 'строк', 'с', 'по'],
                   [(k, num(v['n']), v['first'], v['last']) for k, v in inv['ai_kinds'].items()]),
             '', 'Feedback по видам: ' + ', '.join('%s %d' % kv for kv in inv['feedback'].items()),
             '', 'LearningEvent (источник/событие): ' + ', '.join(
                 '%s %d' % kv for kv in sorted(inv['learning'].items(), key=lambda x: -x[1])), '',
             table(['Event: 30 частых имён', 'событий', 'людей'],
                   [(e['name'], num(e['n']), num(e['people'])) for e in inv['events_top']]), '']

    a = {k: v['A'] for k, v in b.items()}
    lines += ['## A. Охват', '', two(a, [
        ('Активных за всё время (вошедшие с событием)', lambda x: num(x['ever_active'])),
        ('Писали в чат', lambda x: num(x['ever_chat'])),
        ('Доля активных, писавших в чат', lambda x: pct(x['ever_share'])),
        ('Вернулись в чат в другой день', lambda x: '%s (%s)' % (
            num(x['returned']), pct(x['returned_share']))),
        ('Воронка: открыл задачу', lambda x: num(x['funnel']['opened_problem'])),
        ('→ открыл «Спросить ИИ»', lambda x: num(x['funnel']['opened_ai'])),
        ('→ написал', lambda x: num(x['funnel']['wrote'])),
    ]), '', 'По неделям (без сотрудников): активных / писали в чат из активных / доля.', '',
        table(['Неделя с', 'активных', 'писали', 'доля'],
              [(w['week'], w['active'], w['wrote_active'], pct(w['share']))
               for w in a['no_staff']['weeks']]), '']

    bb = {k: v['B'] for k, v in b.items()}
    lines += ['## B. Нагрузка', '', two(bb, [
        ('Реплик на человека в неделю: медиана / P75 / P90 / макс.', lambda x: '%s / %s / %s / %s' % (
            num(x['per_user_week']['median']), num(x['per_user_week']['p75']),
            num(x['per_user_week']['p90']), num(x['per_user_week']['max']))),
        ('Разговоров', lambda x: num(x['threads'])),
        ('Реплик в разговоре', lambda x: dist_row(x['thread_sizes'], 0)),
        ('Разговоров из одной реплики', lambda x: pct(x['single_share'])),
    ]), '', 'Распределение длины разговора (все): ' + ', '.join(
        '%s реплик — %d' % kv for kv in bb['all']['thread_size_counts'].items()), '',
        table(['Номер', 'реплик', 'сотрудник'],
              [(u['user_id'], u['turns'], 'да' if u['staff'] else '') for u in bb['all']['top_users']]),
        '']

    c = {k: v['C'] for k, v in b.items()}
    rows = []
    for mode in m.MODES:
        rows.append(('Режим %s: доля реплик' % mode, lambda x, mode=mode: pct(x['modes'][mode]['turn_share'])))
        rows.append(('Режим %s: доля людей' % mode, lambda x, mode=mode: pct(x['modes'][mode]['people_share'])))
    rows += [
        ('Реплик с вложением', lambda x: '%s (%s)' % (num(x['file_turns']), pct(x['file_share']))),
        ('Картинок в модель на реплику с файлом', lambda x: dist_row(x['pages_per_file_turn'], 0)),
        ('Типы файлов', lambda x: ', '.join('%s %d' % kv for kv in x['mimes'].items()) or '—'),
        ('Реплик с файлом и пустой расшифровкой', lambda x: '%s (%s)' % (
            num(x['empty_vision']), pct(x['empty_vision_share']))),
    ]
    lines += ['## C. Режимы и фото', '', two(c, rows), '']

    dd = {k: v['D'] for k, v in b.items()}
    rows = [('Реплик с ошибкой', lambda x: '%s (%s)' % (num(x['errors']), pct(x['error_share'])))]
    for key, label in m.ERROR_KINDS:
        rows.append(('— ' + label, lambda x, key=key: '%s (%s)' % (
            num(x['kinds'][key]['n']), pct(x['kinds'][key]['share']))))
    rows += [('Ответов с испорченными формулами', lambda x: '%s из %s (%s)' % (
                 num(x['broken']), num(x['replies']), pct(x['broken_share']))),
             ('Ответов длиной от 0,99 потолка', lambda x: '%s (%s)' % (
                 num(x['near_cap']), pct(x['near_cap_share'])))]
    lines += ['## D. Потери', '', two(dd, rows), '', 'Частые тексты ошибок (все):', '',
              table(['Текст ошибки', 'раз'],
                    [(t['text'].replace('|', '/'), t['n']) for t in dd['all']['top_texts']]), '']

    e = {k: v['E'] for k, v in b.items()}
    rows = [('Время ответа, с, все режимы', lambda x: dist_row(x['latency']['all']))]
    for mode in m.MODES:
        rows.append(('— %s' % mode, lambda x, mode=mode: dist_row(x['latency'][mode])))
    rows += [
        ('— с фото', lambda x: dist_row(x['latency']['with_files'])),
        ('— без фото', lambda x: dist_row(x['latency']['without_files'])),
        ('Дольше 20 с', lambda x: '%s (%s)' % (num(x['slow']), pct(x['slow_share']))),
        ('Цена реплики: медиана / среднее / P90', lambda x: '%s / %s / %s' % (
            usd(x['cost']['median'], 5), usd(x['cost']['mean'], 5), usd(x['cost']['p90'], 5))),
        ('Сумма cost_usd реплик', lambda x: usd(x['cost']['total'], 4)),
        ('Токены: вход / выход / рассуждение', lambda x: '%s / %s / %s' % (
            num(x['tokens']['input']), num(x['tokens']['output']), num(x['tokens']['reasoning']))),
        ('Токены зрения: вход / выход', lambda x: '%s / %s' % (
            num(x['tokens']['vision_input']), num(x['tokens']['vision_output']))),
        ('Вход на реплику', lambda x: dist_row(x['tokens']['per_turn_input'], 0)),
        ('Выход на реплику', lambda x: dist_row(x['tokens']['per_turn_output'], 0)),
        ('Максимум расхода за сутки', lambda x: usd(x['max_day'], 4)),
        ('Суток с отказом по потолку', lambda x: num(len(x['cap_days']))),
        ('Те же токены по таблице цен сейчас', lambda x: usd(x['flash']['now_by_table'], 4)),
        ('Те же токены на glm-5.3-flash', lambda x: '%s (×%s)' % (
            usd(x['flash']['flash'], 4), num(x['flash']['ratio'], 2))),
        ('AiUsageLog catalog_chat: вызовов / расход', lambda x: '%s / %s' % (
            num(x['ai_log_calls']), usd(x['ai_log_cost'], 4))),
        ('Оплачено, но не записано в реплики (журнал ИИ − реплики)', lambda x: usd(
            x['ai_log_cost'] - float(x['cost']['total']), 4)),
    ]
    lines += ['## E. Время и деньги', '', two(e, rows), '',
              'Расход чата по суткам (все): ' + ', '.join(
                  '%s %s' % (day, usd(v, 3)) for day, v in e['all']['per_day'].items()), '']

    f = {k: v['F'] for k, v in b.items()}
    lines += ['## F. Одновременность вызовов ИИ', '',
              'Вызов занимает отрезок [created_at − seconds, created_at]; касание — '
              'не пересечение.', '', two(f, [
                  ('Все виды: вызовов', lambda x: num(x['all_kinds']['calls'])),
                  ('Все виды: максимум одновременно', lambda x: num(x['all_kinds']['max'])),
                  ('Все виды: раз дошло до 2 / 3 / 4', lambda x: '%s / %s / %s' % (
                      num(x['all_kinds']['episodes_2']), num(x['all_kinds']['episodes_3']),
                      num(x['all_kinds']['episodes_4']))),
                  ('Все виды: часы (МСК) эпизодов ≥3', lambda x: ', '.join(
                      '%s ч — %d' % kv for kv in x['all_kinds']['hours_3'].items()) or '—'),
                  ('Чат: вызовов / максимум', lambda x: '%s / %s' % (
                      num(x['chat']['calls']), num(x['chat']['max']))),
                  ('Чат: раз дошло до 2 / 3 / 4', lambda x: '%s / %s / %s' % (
                      num(x['chat']['episodes_2']), num(x['chat']['episodes_3']),
                      num(x['chat']['episodes_4']))),
              ]), '']

    g = {k: v['G'] for k, v in b.items()}
    lines += ['## G. После чата', '',
              '⚠️ Это ОПИСАНИЕ, а не доказательство пользы: в чат идут с трудными '
              'задачами, и сравниваемые пары разные.', '', two(g, [
                  ('Пар «ученик–задача» с чатом', lambda x: num(x['chat_pairs'])),
                  ('— решил после первой реплики', lambda x: '%s (%s)' % (
                      num(x['chat_solved_after']), pct(x['chat_share']))),
                  ('Пар без чата (открывал задачу)', lambda x: num(x['plain_pairs'])),
                  ('— решил', lambda x: '%s (%s)' % (num(x['plain_solved']), pct(x['plain_share']))),
              ]), '']

    h = {k: v['H'] for k, v in b.items()}
    lines += ['## H. Умный поиск', '', two(h, [
        ('Запросов', lambda x: num(x['queries'])),
        ('— из них гостей', lambda x: num(x['guest_queries'])),
        ('С переранжированием', lambda x: '%s (%s)' % (num(x['rerank']), pct(x['rerank_share']))),
        ('Статусы', lambda x: ', '.join('%s %d' % kv for kv in x['statuses'].items())),
        ('Оценки: да / нет / доля оценённых', lambda x: '%s / %s / %s' % (
            num(x['rated_yes']), num(x['rated_no']), pct(x['rated_share']))),
        ('Время запроса, мс (все)', lambda x: dist_row(x['ms_all'], 0)),
        ('Время запроса, мс (с переранжированием)', lambda x: dist_row(x['ms_rerank'], 0)),
        ('Вызовов модели / расход', lambda x: '%s / %s' % (num(x['ai_calls']), usd(x['ai_cost'], 4))),
        ('Цена запроса с переранжированием', lambda x: usd(x['cost_per_rerank'], 5)),
        ('Максимум расхода за сутки', lambda x: usd(x['max_day'], 4)),
        ('Суток у потолка (расход ≥ потолка) / со статусом quota', lambda x: '%s / %s' % (
            num(len(x['cap_days'])), num(len(x['quota_days'])))),
    ]), '', 'По суткам (все): запросов / fallback / гостей — ' + ', '.join(
        '%s %d/%d/%d' % (day, v['queries'], v['fallback'], v['guest'])
        for day, v in h['all']['per_day'].items()), '']

    i = b['no_staff']['I']
    lines += ['## I. Темы (без сотрудников)', '',
              table(['Тема', 'реплик', 'людей'],
                    [(t['topic'].replace('|', '/'), t['turns'], t['people']) for t in i['topics']]),
              '', 'Реплик по задачам без темы: %d.' % i['without_topic'], '',
              table(['Задача', 'реплик', 'людей'],
                    [(p['problem_id'], p['turns'], p['people']) for p in i['problems']]), '']

    j = {k: v['J'] for k, v in b.items()}
    lines += ['## J. Для юнит-экономики', '', two(j, [
        ('Вопросов на активного ученика в неделю: медиана / P90', lambda x: '%s / %s (n=%s)' % (
            num(x['questions_per_active_student_week']['median']),
            num(x['questions_per_active_student_week']['p90']),
            x['questions_per_active_student_week']['n'])),
        ('Доля учеников с фото (из писавших в чат)', lambda x: '%s (%s из %s)' % (
            pct(x['photo_share']), x['photo_students'], x['chat_students'])),
        ('Цена ответа сейчас: медиана / среднее', lambda x: '%s / %s' % (
            usd(x['cost_now_median'], 5), usd(x['cost_now_mean'], 5))),
        ('Цена ответа на Flash (среднее)', lambda x: usd(x['cost_flash_mean'], 5)),
        ('Максимум одновременных вызовов: все виды / чат', lambda x: '%s / %s' % (
            x['max_concurrency_all'], x['max_concurrency_chat'])),
    ]), '']

    if b['all'].get('K') is not None:
        k = {key: v['K'] for key, v in b.items()}
        rows = []
        for mode in ('method', 'free', 'both'):
            rows.append(('%s: ответов с числом из ответа банка' % mode,
                         lambda x, mode=mode: '%s из %s (%s); всего ответов %s' % (
                             num(x[mode]['hits']), num(x[mode]['with_key']),
                             pct(x[mode]['share']), num(x[mode]['replies']))))
        lines += ['## K. Выдал ли ответ (грубая оценка)', '',
                  '⚠️ Грубая оценка: ключ — `propose_key` вида exact по ответу банка, '
                  'числа из условия не считаются; совпадение числа — ещё не выданный ответ.',
                  '', two(k, rows), '']
    return '\n'.join(lines) + '\n'


class Command(BaseCommand):
    help = 'Цифры беты по ИИ-чату и умному поиску: BETA_REPORT.md и beta_numbers.json. Только читает.'

    def add_arguments(self, parser):
        parser.add_argument('--out', required=True, help='Папка для отчёта (вне репозитория).')
        parser.add_argument('--since', default='', help='С какой даты, ГГГГ-ММ-ДД (МСК).')
        parser.add_argument('--until', default='', help='По какую дату ВКЛЮЧИТЕЛЬНО (МСК).')
        parser.add_argument('--team-file', default='',
                            help='Номера команды, по одному в строке '
                                 '(по умолчанию <out>/team_user_ids.txt, если есть).')

    def handle(self, *args, **options):
        out = options['out']
        os.makedirs(out, exist_ok=True)
        since = _day(options['since']) if options['since'] else None
        until = _day(options['until'], end=True) if options['until'] else None
        team_file = options['team_file'] or os.path.join(out, TEAM_FILE)
        team = set()
        if os.path.exists(team_file):
            with open(team_file, encoding='utf-8') as handle:
                team = m.read_team_ids(handle)
        elif options['team_file']:
            raise CommandError('Нет файла команды: %s' % team_file)
        else:
            team_file = ''

        data, keys = load(since, until)
        staff = m.staff_ids(data['users'], team)
        timeout_ms = core.timeout_seconds() * 1000
        from catalog.chat import CHECK_REPLY_MAX, REPLY_MAX
        caps = getattr(settings, 'AI_DAILY_COST_CAPS', {})
        blocks = {}
        for key, _label in m.SLICES:
            d = data if key == 'all' else m.sliced(data, staff)
            e = m.block_e(d, settings.AI_PRICES)
            f = m.block_f(d)
            blocks[key] = {
                'A': m.block_a(d), 'B': m.block_b(d, staff), 'C': m.block_c(d),
                'D': m.block_d(d, REPLY_MAX, CHECK_REPLY_MAX, timeout_ms),
                'E': e, 'F': f, 'G': m.block_g(d),
                'H': m.block_h(d, caps.get('search_rerank')), 'I': m.block_i(d),
                'J': m.block_j(d, e, f), 'K': m.block_k(d, keys),
            }
        from django.db import connection
        result = {'copy': connection.settings_dict.get('NAME'),
                  'since': options['since'], 'until': options['until'],
                  'team_file': team_file, 'staff_count': len(staff),
                  'staff_ids': sorted(staff),
                  'inventory': inventory(), 'blocks': blocks}
        with open(os.path.join(out, NUMBERS), 'w', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=1, default=str)
        report = render(result)
        with open(os.path.join(out, REPORT), 'w', encoding='utf-8') as handle:
            handle.write(report)
        total = sum((t['cost_usd'] for t in data['turns']), Decimal(0))
        self.stdout.write('Реплик %d, разговоров %d, сотрудников %d, сумма цен $%s; '
                          'знаков «@» в отчёте: %d. Файлы: %s, %s' % (
                              len(data['turns']), blocks['all']['B']['threads'], len(staff),
                              total, report.count('@'), REPORT, NUMBERS))
