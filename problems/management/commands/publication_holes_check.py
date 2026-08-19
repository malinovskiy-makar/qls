"""Проверка одобренных человеком задач НА ФАКТЫ перед выкладкой.

⚠️ ТОЛЬКО ЧИТАЕТ. Ничего не меняет и метку `approved` не снимает.

ЗАЧЕМ. Человек оценивал ВНЕШНИЙ ВИД по снимку страницы. Есть дефекты,
которых на снимке не видно в принципе: у задачи нет ни ответа, ни решения
(страница выглядит нормально), в поле решения лежит вопрос ученика с форума
(связный текст, ничего не сломано). Плюс снимки сделаны в июле, а база с тех
пор менялась — вердикт может относиться к другой версии текста.

Поэтому проверяются только факты: то, что либо есть, либо нет. Никаких
эвристик «похоже на плохую задачу» — детекторы качества для отбора не
годятся (решение Notion 3abb11c92bc18133aea8c3ee9d8716bd).

ПРИЗНАКИ:
  а  statement пустой или короче 30 символов
  б  пусто и solution, и answer, и нет ни одного подпункта с ответом
  в  KaTeX даёт ОШИБКУ при рендере любого поля
  г  рендер без ошибки, но внутри формулы неизвестная команда: KaTeX молча
     её выбрасывает, и соседние числа слипаются (ловушка \\myarray, #27420)
  д  у задачи нет ни одной канонической темы
  е  непарное число неэкранированных «$» в любом поле
  ж  задача изменялась ПОСЛЕ сборки своего пакета ревью
  з  в solution текст, похожий на форумную реплику, а не на разбор

Признаки «в» и «г» считает НАСТОЯЩИЙ БРАУЗЕР (шлюз «не навреди»: текстовый
предфильтр к ошибкам KaTeX слеп, рендерить надо всё). Без --with-render эти
две строки в отчёте помечаются «не измерено».

    venv\\Scripts\\python manage.py publication_holes_check
    venv\\Scripts\\python manage.py publication_holes_check --with-render
"""

import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from problems.models import Problem, ReviewVerdict
from problems.management.commands.apply_topic_mapping import CANONICAL
from problems.management.commands.ile_forum_solutions import forum_signals

OUT_DIR = os.path.join('reports', 'publication_check')
BUNDLES_DIR = os.path.join('reports', 'review_bundles')
QUEUE = os.path.join(OUT_DIR, 'render_queue.json')
RENDER_OUT = os.path.join(OUT_DIR, 'render_result.json')

MIN_STATEMENT = 30

SIGNS = [
    ('a', 'statement пустой или короче {} символов'.format(MIN_STATEMENT)),
    ('b', 'нет ни решения, ни ответа, ни ответа в подпунктах'),
    ('v', 'KaTeX даёт ошибку при рендере'),
    ('g', 'рендер без ошибки, но команда выброшена (числа слипаются)'),
    ('d', 'нет ни одной канонической темы'),
    ('e', 'непарное число неэкранированных $'),
    ('zh', 'задача изменялась после сборки своего пакета ревью'),
    ('z', 'в решении форумная реплика, а не разбор'),
]
SIGN_LABEL = dict(SIGNS)


def dollar_count(text):
    """Число $ без учёта экранированных \\$ (как считает боевой конвейер)."""
    return (text or '').replace('\\$', '').count('$')


def bundle_dates():
    """{bundle_id: момент сборки пакета} по манифестам на диске."""
    out = {}
    if not os.path.isdir(BUNDLES_DIR):
        return out
    for name in sorted(os.listdir(BUNDLES_DIR)):
        path = os.path.join(BUNDLES_DIR, name, 'manifest.json')
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                man = json.load(fh)
        except (ValueError, OSError):
            continue
        when = parse_datetime(man.get('created_at') or '')
        if man.get('bundle_id') and when:
            out[man['bundle_id']] = when
    return out


def baseline_rates():
    """Доли признаков «б» и «д» в других выборках — ФОН для сравнения.

    Без фона числа читаются неверно. «Нет ответа и решения» звучит как
    дефект, но в этом банке это НОРМА: у видимого каталога доля выше, чем у
    одобренных. А вот «нет канонической темы» у одобренных ХУЖЕ фона — и это
    настоящая просадка, которую видно только рядом с фоном.
    """
    from problems.models import ProblemPart, Topic
    from django.db.models import Q

    canon_ids = set(Topic.objects.filter(name__in=set(CANONICAL))
                    .values_list('id', flat=True))

    def one(qs, label):
        ids = set(qs.values_list('id', flat=True))
        n = len(ids)
        if not n:
            return (label, 0, 0, 0)
        empty = set(qs.filter(Q(solution='') | Q(solution__isnull=True))
                      .filter(Q(answer='') | Q(answer__isnull=True))
                      .values_list('id', flat=True))
        with_part = set(ProblemPart.objects.filter(problem_id__in=empty)
                        .exclude(answer='').exclude(answer__isnull=True)
                        .values_list('problem_id', flat=True))
        b = len(empty - with_part)
        has_topic = set(Problem.objects.filter(id__in=ids,
                                               topics__id__in=canon_ids)
                        .values_list('id', flat=True))
        return (label, n, b, n - len(has_topic))

    return [
        one(Problem.objects.filter(human_review=Problem.HumanReview.APPROVED),
            'одобренные человеком (approved)'),
        one(Problem.objects.filter(status='published',
                                   needs_quality_review=False),
            'весь видимый каталог сегодня'),
        one(Problem.objects.filter(status='published'), 'всё published'),
        one(Problem.objects.filter(human_review=Problem.HumanReview.DEFECT),
            'помеченные браком (defect)'),
    ]


class Command(BaseCommand):
    help = ('Проверка задач с human_review=approved на факты перед выкладкой. '
            'Только читает.')

    def add_arguments(self, parser):
        parser.add_argument('--with-render', action='store_true',
                            help='прогнать поля через настоящий KaTeX (node)')
        parser.add_argument('--limit', type=int, default=0,
                            help='ограничить число задач (для пробы)')

    def handle(self, *args, **opts):
        say = self.stdout.write
        os.makedirs(OUT_DIR, exist_ok=True)

        canon = set(CANONICAL)
        dates = bundle_dates()

        qs = (Problem.objects
              .filter(human_review=Problem.HumanReview.APPROVED)
              .prefetch_related('parts', 'topics', 'review_verdicts')
              .order_by('id'))
        if opts['limit']:
            qs = qs[:opts['limit']]

        problems = list(qs)
        say('Одобренных человеком задач: {}'.format(len(problems)))
        if not problems:
            say('Проверять нечего.')
            return

        hits = defaultdict(set)     # признак -> {id}
        detail = defaultdict(dict)  # id -> {признак: пояснение}
        queue = []                  # что отдать браузеру

        for p in problems:
            parts = list(p.parts.all())

            # а — условие пустое или огрызок
            st = (p.statement or '').strip()
            if len(st) < MIN_STATEMENT:
                hits['a'].add(p.id)
                detail[p.id]['a'] = 'длина условия {}'.format(len(st))

            # б — не на что смотреть ученику: ни решения, ни ответа нигде
            has_part_answer = any((pt.answer or '').strip() for pt in parts)
            if (not (p.solution or '').strip()
                    and not (p.answer or '').strip()
                    and not has_part_answer):
                hits['b'].add(p.id)
                detail[p.id]['b'] = 'ни solution, ни answer, ни ответов в подпунктах'

            # д — ни одной канонической темы
            names = {t.name for t in p.topics.all()}
            if not (names & canon):
                hits['d'].add(p.id)
                detail[p.id]['d'] = ('темы: ' + ', '.join(sorted(names))
                                     if names else 'тем нет вовсе')

            # е — непарные доллары в любом поле
            fields = [('statement', p.statement), ('solution', p.solution),
                      ('answer', p.answer)]
            for pt in parts:
                fields.append(('part:{}:statement'.format(pt.pk), pt.statement))
                fields.append(('part:{}:answer'.format(pt.pk), pt.answer))
            odd = [name for name, text in fields
                   if text and dollar_count(text) % 2 == 1]
            if odd:
                hits['e'].add(p.id)
                detail[p.id]['e'] = 'поля: ' + ', '.join(odd)

            # ж — правка ПОСЛЕ сборки пакета: вердикт про другой текст
            late = []
            for v in p.review_verdicts.all():
                built = dates.get(v.bundle)
                if built and p.updated_at and p.updated_at > built:
                    late.append(v.bundle)
            if late:
                hits['zh'].add(p.id)
                detail[p.id]['zh'] = ('правлена {}, пакет {} собран {}'.format(
                    p.updated_at.date(), sorted(set(late))[0],
                    dates[sorted(set(late))[0]].date()))

            # з — форумная реплика вместо разбора
            signals = forum_signals(p.solution or '')
            if signals:
                hits['z'].add(p.id)
                detail[p.id]['z'] = ', '.join(signals)

            # очередь на рендер (в, г)
            for name, text in fields:
                if text and ('$' in text or '\\' in text):
                    queue.append({'pid': p.id, 'field': name, 'text': text})

        with open(QUEUE, 'w', encoding='utf-8') as fh:
            json.dump(queue, fh, ensure_ascii=False)
        say('Полей на рендер: {} -> {}'.format(len(queue), QUEUE))

        rendered = None
        if opts['with_render']:
            say('Запускаю браузер (это небыстро)...')
            # ⚠️ На Windows subprocess не ищет node по PATH сам (нужен .exe
            # или shell): без which здесь падало WinError 2.
            node = shutil.which('node') or 'node'
            proc = subprocess.run(
                [node, os.path.join('scripts', 'holes_render_check.js'),
                 '--queue', QUEUE, '--out', RENDER_OUT],
                capture_output=True, text=True, encoding='utf-8', errors='replace')
            if proc.returncode != 0:
                say('РЕНДЕР НЕ ВЫПОЛНЕН (код {}):'.format(proc.returncode))
                say((proc.stderr or proc.stdout or '')[-2000:])
            else:
                say((proc.stdout or '').strip()[-500:])
        if os.path.exists(RENDER_OUT):
            with open(RENDER_OUT, encoding='utf-8') as fh:
                rendered = json.load(fh)

        if rendered:
            for row in rendered:
                pid = row['pid']
                if row.get('errors'):
                    hits['v'].add(pid)
                    detail[pid]['v'] = '{}: ошибок {}'.format(
                        row['field'], row['errors'])
                elif row.get('red'):
                    hits['g'].add(pid)
                    note = '{}: выброшено команд {}'.format(
                        row['field'], row['red'])
                    if row.get('glued'):
                        note += ', числа слиплись: {}'.format(
                            ', '.join(row['glued'][:4]))
                    detail[pid]['g'] = note

        self.write_report(problems, hits, detail, rendered is not None, say)

    # ------------------------------------------------------------------
    def write_report(self, problems, hits, detail, measured, say):
        ids_all = sorted({pid for s in hits.values() for pid in s})
        total = len(problems)

        lines = []
        lines.append('# Проверка одобренных задач на дыры\n')
        lines.append('Проверено задач с `human_review=approved`: **{}**.\n'
                     .format(total))
        lines.append('Хотя бы один признак: **{}** ({:.1f} %).\n'
                     .format(len(ids_all), 100.0 * len(ids_all) / total))
        lines.append('⚠️ Метка `approved` НЕ снята ни у одной задачи — '
                     'это только отчёт. Решение по ним за владельцем.\n')
        if not measured:
            lines.append('⚠️ Признаки «в» и «г» НЕ ИЗМЕРЕНЫ: прогон без '
                         '`--with-render`.\n')

        lines.append('\n## Сводка\n')
        lines.append('| Признак | Что значит | Задач |')
        lines.append('|---|---|---:|')
        for key, label in SIGNS:
            if key in ('v', 'g') and not measured:
                n = 'не измерено'
            else:
                n = str(len(hits.get(key, ())))
            lines.append('| {} | {} | {} |'.format(key, label, n))

        lines.append('\n## Фон: те же признаки в других выборках\n')
        lines.append('Признак сам по себе ничего не значит, пока не видно '
                     'фона. «Нет ответа и решения» — норма этого банка, а не '
                     'дефект одобренных. «Нет канонической темы» — наоборот, '
                     'у одобренных ХУЖЕ фона.\n')
        lines.append('| Выборка | Задач | б: нет ответа и решения | '
                     'д: нет канонической темы |')
        lines.append('|---|---:|---:|---:|')
        for label, n, b, d in baseline_rates():
            if not n:
                continue
            lines.append('| {} | {} | {} ({:.0f} %) | {} ({:.0f} %) |'.format(
                label, n, b, 100.0 * b / n, d, 100.0 * d / n))

        lines.append('\n## По признакам\n')
        for key, label in SIGNS:
            ids = sorted(hits.get(key, ()))
            lines.append('\n### {} — {}\n'.format(key, label))
            if key in ('v', 'g') and not measured:
                lines.append('Не измерено (нужен `--with-render`).\n')
                continue
            lines.append('Задач: **{}**.\n'.format(len(ids)))
            if not ids:
                continue
            lines.append('Первые 50 id с пояснением:\n')
            for pid in ids[:50]:
                lines.append('- #{} — {}'.format(
                    pid, detail[pid].get(key, '')))
            if len(ids) > 50:
                lines.append('\n…и ещё {}.'.format(len(ids) - 50))

        # Пересечения: сколько задач несёт сразу несколько признаков.
        per = Counter(len(detail[pid]) for pid in ids_all)
        lines.append('\n## Сколько признаков на одну задачу\n')
        lines.append('| Признаков | Задач |')
        lines.append('|---:|---:|')
        for k in sorted(per):
            lines.append('| {} | {} |'.format(k, per[k]))

        path = os.path.join(OUT_DIR, 'holes.md')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')

        ids_path = os.path.join(OUT_DIR, 'holes_ids.txt')
        with open(ids_path, 'w', encoding='utf-8') as fh:
            fh.write('# Задачи approved, у которых нашёлся хотя бы один признак.\n')
            fh.write('# Метка НЕ снята. Решение за владельцем.\n')
            for pid in ids_all:
                fh.write('{}\t{}\n'.format(
                    pid, ','.join(sorted(detail[pid]))))

        say('')
        say('=== НАЙДЕНО ===')
        for key, label in SIGNS:
            mark = ('не измерено' if key in ('v', 'g') and not measured
                    else len(hits.get(key, ())))
            say('  {:3s} {:58s} {}'.format(key, label[:58], mark))
        say('  ИТОГО задач хотя бы с одним признаком: {} из {}'.format(
            len(ids_all), total))
        say('')
        say('Отчёт: {}'.format(path))
        say('Список id: {}'.format(ids_path))
