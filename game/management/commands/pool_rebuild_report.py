# -*- coding: utf-8 -*-
u"""pool_rebuild_report: отчёт о пересборке игрового пула.

Читает три источника и ничего не меняет:
  1. текущий пул GameQuestion в базе,
  2. разбор судьбы кандидатов из build_game_pool --audit-json,
  3. снимок пула ДО пересборки из копии базы (--before), чтобы числа
     «было и стало» брались из замера, а не из памяти.

Запуск:
    manage.py build_game_pool --audit-json reports/game/pool_audit.json
    manage.py pool_rebuild_report --audit reports/game/pool_audit.json \
        --before reports/game/backups/db_before_classify_20260902.sqlite3
"""
import collections
import html
import json
import os
import random
import re
import sqlite3

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from game.models import GameQuestion
from problems.models import Problem

EXAMPLES_PER_REASON = 20

# Источники, строки по которым в отчёте обязательны: их владелец смотрит
# в первую очередь. Отсутствие строки значит ноль, и это тоже ответ.
REQUIRED_SOURCES = [
    'Сборник тестов АА',
    'SolveHub',
    'Школково',
    'ЛЭШ',
]

CSS = """
body{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;
     background:#f7f7f8;color:#1c1c1e}
main{max-width:1100px;margin:0 auto;padding:32px 24px 80px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:20px;margin:34px 0 10px}
h3{font-size:16px;margin:22px 0 8px;color:#3c3c43}
.lead{color:#5c5c62;margin:0 0 22px}
table{border-collapse:collapse;width:100%;background:#fff;margin:10px 0 18px;
      box-shadow:0 1px 2px rgba(0,0,0,.07)}
th,td{padding:8px 11px;border-bottom:1px solid #e6e6ea;text-align:left;
      vertical-align:top;font-size:14px}
th{background:#efeff2;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.card{background:#fff;border:1px solid #e6e6ea;border-radius:8px;
      padding:11px 13px;margin:0 0 9px;font-size:14px}
.meta{font-size:13px;color:#5c5c62;margin:2px 0}
.ok{color:#1a7f37;font-weight:600}
.warn{color:#9a6700;font-weight:600}
.bad{color:#b3261e;font-weight:600}
.grow{color:#1a7f37} .drop{color:#b3261e}
code{background:#f0f0f3;padding:1px 5px;border-radius:4px;font-size:13px}
"""


def esc(value):
    return html.escape(str(value if value is not None else ''))


def cut(value, limit=300):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text if len(text) <= limit else text[:limit] + '…'


def delta(before, after):
    diff = after - before
    if diff == 0:
        return '0'
    css = 'grow' if diff > 0 else 'drop'
    return '<span class="%s">%+d</span>' % (css, diff)


class Report(object):

    def __init__(self, title):
        self.parts = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
                      '<title>%s</title>' % esc(title),
                      '<style>%s</style><main>' % CSS,
                      '<h1>%s</h1>' % esc(title)]

    def add(self, chunk):
        self.parts.append(chunk)

    def table(self, headers, rows):
        out = ['<table><tr>']
        for head in headers:
            css = ' class="num"' if head.startswith('#') else ''
            out.append('<th%s>%s</th>' % (css, esc(head.lstrip('#'))))
        out.append('</tr>')
        for row in rows:
            out.append('<tr>')
            for head, cell in zip(headers, row):
                css = ' class="num"' if head.startswith('#') else ''
                out.append('<td%s>%s</td>' % (css, cell))
            out.append('</tr>')
        out.append('</table>')
        self.add(''.join(out))

    def html(self):
        return ''.join(self.parts) + '</main></html>'


def read_before(path):
    u"""Снимок пула из копии базы: всего, банк, сгенерированные, по типам."""
    if not os.path.exists(path):
        raise CommandError('нет копии базы: %s' % path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM game_gamequestion')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM game_gamequestion WHERE is_generated=0')
    bank = cur.fetchone()[0]
    cur.execute('SELECT question_type, COUNT(*) FROM game_gamequestion '
                'WHERE is_generated=0 GROUP BY question_type')
    by_type = dict(cur.fetchall())
    cur.execute(
        'SELECT s.name, COUNT(*) FROM game_gamequestion g '
        'LEFT JOIN problems_source s ON s.id = g.source_id '
        'WHERE g.is_generated=0 GROUP BY s.name')
    by_source = {(name or 'без источника'): n for name, n in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM game_gamequestion "
                "WHERE is_generated=0 AND tag_ids NOT IN ('[]', '')")
    tagged = cur.fetchone()[0]
    con.close()
    return {'total': total, 'bank': bank, 'generated': total - bank,
            'by_type': by_type, 'by_source': by_source, 'tagged': tagged}


class Command(BaseCommand):
    help = 'Отчёт о пересборке игрового пула. Ничего не меняет.'

    def add_arguments(self, parser):
        parser.add_argument('--audit', type=str,
                            default=os.path.join('reports', 'game',
                                                 'pool_audit.json'))
        parser.add_argument('--before', type=str, default='')
        parser.add_argument('--out', type=str,
                            default=os.path.join('reports', 'game',
                                                 'pool_rebuild_report.html'))

    def handle(self, *args, **options):
        if not os.path.exists(options['audit']):
            raise CommandError('нет разбора кандидатов: %s' % options['audit'])
        with open(options['audit'], encoding='utf-8') as fh:
            audit = json.load(fh)
        before = read_before(options['before']) if options['before'] else None

        bank = GameQuestion.objects.filter(is_generated=False)
        after = {
            'total': GameQuestion.objects.count(),
            'bank': bank.count(),
            'generated': GameQuestion.objects.filter(is_generated=True).count(),
            'by_type': {r['question_type']: r['n'] for r in
                        bank.values('question_type').annotate(n=Count('id'))},
            'tagged': bank.exclude(tag_ids=[]).count(),
            'topiced': bank.exclude(topics=[]).count(),
        }
        source_names = dict(
            Problem.objects.filter(id__in=[int(k) for k in audit])
            .values_list('id', 'problem_type'))

        report = Report('Пересборка игрового пула Wecon Rush')
        report.add('<p class="lead">Отчёт читает базу и разбор кандидатов. '
                   'Ничего не меняет.</p>')

        # ── 1. Пул до и после ────────────────────────────────────────────
        report.add('<h2>1. Пул до и после</h2>')
        if before:
            report.table(
                ['Что', '#Было', '#Стало', '#Разница'],
                [['Всего в пуле', before['total'], after['total'],
                  delta(before['total'], after['total'])],
                 ['Из банка задач', before['bank'], after['bank'],
                  delta(before['bank'], after['bank'])],
                 ['Сгенерированные', before['generated'], after['generated'],
                  delta(before['generated'], after['generated'])]])
            report.add('<h3>По типам вопросов (только банк)</h3>')
            rows = []
            for qtype in ('single', 'boolean', 'multi', 'numeric'):
                was = before['by_type'].get(qtype, 0)
                now = after['by_type'].get(qtype, 0)
                rows.append([qtype, was, now, delta(was, now)])
            report.table(['Тип', '#Было', '#Стало', '#Разница'], rows)

        # ── 2. По источникам ─────────────────────────────────────────────
        got = collections.Counter()
        lost = collections.defaultdict(collections.Counter)
        for pid, row in audit.items():
            name = row['source'] or 'без источника'
            if row['reason'] is None:
                got[name] += 1
            else:
                lost[name][row['reason']] += 1

        report.add('<h2>2. По источникам</h2>')
        rows = []
        every = sorted(set(got) | set(lost),
                       key=lambda n: -(got[n] + sum(lost[n].values())))
        for name in every:
            candidates = got[name] + sum(lost[name].values())
            was = (before['by_source'].get(name, 0) if before else 0)
            share = 100.0 * got[name] / candidates if candidates else 0.0
            rows.append([esc(name), was, candidates, got[name],
                         '%.1f %%' % share, delta(was, got[name])])
        report.table(['Источник', '#Было в пуле', '#Кандидатов',
                      '#Стало в пуле', 'Доля', '#Разница'], rows)

        missing = [name for name in REQUIRED_SOURCES
                   if not any(name in seen for seen in every)]
        if missing:
            report.add('<p class="warn">Нет ни одного кандидата от: %s. '
                       'Это не сбой отчёта, а факт: у источника нет задач '
                       'с тестовым типом и опубликованным статусом.</p>'
                       % esc(', '.join(missing)))

        # ── 3. Куда делись остальные ─────────────────────────────────────
        report.add('<h2>3. Куда делись невошедшие</h2>')
        report.add('<p class="lead">По каждому источнику: причина отказа и '
                   'до %d примеров на причину.</p>' % EXAMPLES_PER_REASON)
        rnd = random.Random(20260902)
        by_reason_ids = collections.defaultdict(list)
        for pid, row in audit.items():
            if row['reason'] is not None:
                by_reason_ids[(row['source'] or 'без источника',
                               row['reason'])].append(int(pid))

        for name in every:
            if not lost[name]:
                continue
            report.add('<h3>%s: не вошло %d</h3>'
                       % (esc(name), sum(lost[name].values())))
            report.table(['Причина', '#Сколько'],
                         [[esc(r), n] for r, n in lost[name].most_common()])
            for reason, _ in lost[name].most_common():
                ids = by_reason_ids[(name, reason)]
                sample = rnd.sample(ids, min(EXAMPLES_PER_REASON, len(ids)))
                problems = {p.id: p for p in Problem.objects.filter(id__in=sample)}
                report.add('<h3>%s, примеры (%d из %d)</h3>'
                           % (esc(reason), len(sample), len(ids)))
                for pid in sample:
                    problem = problems.get(pid)
                    if problem is None:
                        continue
                    report.add(
                        '<div class="card"><b>#%s</b> %s'
                        '<p class="meta">Ответ: <code>%s</code></p>'
                        '<p class="meta">Тип: %s</p></div>'
                        % (esc(pid), esc(cut(problem.statement)),
                           esc(cut(problem.answer, 120) or 'пусто'),
                           esc(source_names.get(pid, ''))))

        # ── 4. Метаданные пула ───────────────────────────────────────────
        report.add('<h2>4. Темы и теги</h2>')
        report.table(
            ['Что', '#Сколько', 'Доля пула из банка'],
            [['Вопросов с тегами', after['tagged'],
              '%.1f %%' % (100.0 * after['tagged'] / max(after['bank'], 1))],
             ['Вопросов с темами', after['topiced'],
              '%.1f %%' % (100.0 * after['topiced'] / max(after['bank'], 1))]])

        folder = os.path.dirname(options['out'])
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(options['out'], 'w', encoding='utf-8') as fh:
            fh.write(report.html())
        self.stdout.write('Отчёт: %s' % options['out'])
        self.stdout.write('Пул: %d всего, %d из банка, %d сгенерированных'
                          % (after['total'], after['bank'], after['generated']))
