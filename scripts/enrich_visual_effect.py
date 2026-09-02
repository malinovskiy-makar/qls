# -*- coding: utf-8 -*-
"""Замер: что меняется в ответе модели, если показать ей визуальное.

Два режима, один механизм — вызов 1 прогоняется ДВАЖДЫ на одной и той же
задаче, и ответы сравниваются:

* `--mode tikz`   — с подстановкой исходника чертежа (§3.5) и без неё;
* `--mode raster` — с приложенной растровой картинкой задачи и без неё.

⚠️ ЭТО ЗАМЕР, А НЕ БОЕВОЙ ПРОГОН. Пишется только отчёт; база не
меняется ни в одном режиме, вызов 2 не делается вовсе.

⚠️ Как и `pilot_enrich_v2`, скрипт зовёт `providers.OpenAIProvider`
напрямую — по той же записанной причине (нужны конкретная модель и
уровень рассуждения, а `core.run()` берёт их из настроек). Картинки
уходят через тот же слой `problems/ai/`: наружу идёт только содержимое
самой задачи.

Запуск (потолок расхода обязателен, считается по факту `usage`):

    python scripts/enrich_visual_effect.py --mode tikz   --max-cost 0.5
    python scripts/enrich_visual_effect.py --mode raster --max-cost 1.0 --limit 20
"""
import argparse
import html
import json
import os
import random
import sys
from decimal import Decimal
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings  # noqa: E402
from django.test import override_settings  # noqa: E402

from problems.ai import providers  # noqa: E402
from problems.enrich import prompts_v2  # noqa: E402
from problems.enrich.shortlist import shortlist_for  # noqa: E402
from problems.enrich.text import (problem_full_text, with_figure_note,  # noqa: E402
                                  with_tikz_sources)
from problems.models import Problem  # noqa: E402

SEED = 20260902
MODEL = 'gpt-5.6-terra'
EFFORT = 'none'
OUT_DIR = BASE_DIR / 'reports' / 'enrich_pilot'
#: Форматы, которые принимает Responses API (см. OpenAIProvider.IMAGE_TYPES).
IMAGE_TYPES = providers.OpenAIProvider.IMAGE_TYPES


def cost(model, reply):
    price_in, price_cache, price_out = settings.AI_PRICES[model]
    total = (Decimal(reply.input_tokens) * Decimal(str(price_in))
             + Decimal(reply.output_tokens) * Decimal(str(price_out))
             + Decimal(reply.cache_read_tokens) * Decimal(str(price_cache)))
    return total / Decimal(10 ** 6)


def call1(provider, user_text, images=None):
    core = prompts_v2.call1_core(with_concepts=True)
    schema = prompts_v2.call1_schema(with_concepts=True)
    with override_settings(AI_REASONING_EFFORT=EFFORT):
        return provider.complete([core], user_text, schema, MODEL,
                                 getattr(settings, 'AI_MAX_TOKENS', 4000),
                                 images=images)


def payload_text(problem):
    """Текст задачи ровно в том виде, в каком его собирает пилот."""
    text = problem_full_text(problem.statement, problem.parts.all())
    return with_figure_note(text, problem.figures.count())


def pick_tikz(limit):
    """Все задачи, у которых подстановка §3.5 РЕАЛЬНО меняет payload.

    Это не выборка, а вся совокупность: настоящих чертежей в банке 7 на
    4 задачи, и лишь у части маркер стоит в условии, а не в решении.
    """
    found = []
    qs = (Problem.objects.filter(figures__isnull=False).distinct()
          .prefetch_related('parts', 'figures'))
    for problem in qs.iterator(chunk_size=200):
        _, stats = with_tikz_sources(payload_text(problem),
                                     problem.figures.all())
        if stats['replaced']:
            found.append(problem)
    found.sort(key=lambda p: p.id)
    return found[:limit] if limit else found


def pick_raster(limit):
    """Задачи с растровой картинкой, относящейся к УСЛОВИЮ.

    `source_field='solution'` отбрасывается намеренно: картинка решения
    условие не проясняет, а токены стоит тех же денег.
    """
    ids = list(
        Problem.objects
        .filter(figures__source_field__in=('import', 'statement'),
                figures__content_type__in=IMAGE_TYPES)
        .exclude(figures__image_data=None)
        .distinct().order_by('id').values_list('id', flat=True))
    chosen = sorted(random.Random(SEED).sample(ids, min(limit, len(ids))))
    by_id = {p.id: p for p in Problem.objects.filter(id__in=chosen)
             .prefetch_related('parts', 'figures')}
    return [by_id[i] for i in chosen if i in by_id]


def images_for(problem):
    out = []
    for figure in problem.figures.all():
        if figure.source_field not in ('import', 'statement'):
            continue
        if figure.content_type not in IMAGE_TYPES or not figure.image_data:
            continue
        out.append((figure.content_type, bytes(figure.image_data)))
    return out


FIELDS = ('topic_primary', 'tags', 'econ_concepts', 'given', 'find',
          'task_nature')


def summarize(reply):
    data = json.loads(reply.text)
    return {k: data.get(k) for k in FIELDS}


def jaccard(a, b):
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def run(mode, limit, max_cost):
    provider = providers.OpenAIProvider()
    problems = pick_tikz(limit) if mode == 'tikz' else pick_raster(limit)
    print('Задач в замере: %d — %s' % (
        len(problems), ', '.join('#%d' % p.id for p in problems[:40])))
    spent = Decimal('0')
    rows = []
    failures = []
    for problem in problems:
        if spent >= Decimal(str(max_cost)):
            print('ОСТАНОВ по --max-cost на $%.4f' % spent)
            break
        base_text = payload_text(problem)
        shortlist = shortlist_for(base_text)
        user_a = prompts_v2.call1_user_text(base_text, shortlist)

        if mode == 'tikz':
            text_b, stats = with_tikz_sources(base_text, problem.figures.all())
            user_b, images_b = prompts_v2.call1_user_text(text_b, shortlist), None
        else:
            stats = {'replaced': 0, 'truncated': 0}
            user_b, images_b = user_a, images_for(problem)

        # Отказ на ОДНОЙ задаче не должен терять весь уже оплаченный
        # замер: битая или неподъёмная картинка — ожидаемый случай на
        # корпусе из 2 491 файла, а не повод остановить прогон.
        try:
            reply_a = call1(provider, user_a)
            reply_b = call1(provider, user_b, images=images_b)
        except providers.ProviderError as error:
            failures.append((problem.id, str(error)))
            print('  #%d ПРОПУЩЕНА: %s' % (problem.id, error))
            continue
        spent += cost(MODEL, reply_a) + cost(MODEL, reply_b)

        a, b = summarize(reply_a), summarize(reply_b)
        rows.append({
            'problem_id': problem.id,
            'statement': (problem.statement or '')[:900],
            'stats': stats,
            'images': len(images_b or []),
            'a': a, 'b': b,
            'usage_a': {'input': reply_a.input_tokens,
                        'cached': reply_a.cache_read_tokens,
                        'output': reply_a.output_tokens},
            'usage_b': {'input': reply_b.input_tokens,
                        'cached': reply_b.cache_read_tokens,
                        'output': reply_b.output_tokens},
            'topic_changed': a['topic_primary'] != b['topic_primary'],
            'tags_jaccard': jaccard(a['tags'], b['tags']),
            'tags_changed': set(a['tags'] or []) != set(b['tags'] or []),
            'given_changed': (a['given'] or '') != (b['given'] or ''),
            'find_changed': (a['find'] or '') != (b['find'] or ''),
            'cost_a': float(cost(MODEL, reply_a)),
            'cost_b': float(cost(MODEL, reply_b)),
        })
        print('  #%d тема %s теги J=%.2f  вход %d→%d  потрачено $%.4f'
              % (problem.id, 'СМЕНИЛАСЬ' if rows[-1]['topic_changed'] else 'та же',
                 rows[-1]['tags_jaccard'], reply_a.input_tokens,
                 reply_b.input_tokens, spent))

    if failures:
        print('Пропущено задач: %d — %s' % (
            len(failures), '; '.join('#%d %s' % f for f in failures)))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / ('%s_effect.json' % mode)).write_text(
        json.dumps({'mode': mode, 'model': MODEL, 'effort': EFFORT,
                    'seed': SEED, 'spent': float(spent), 'rows': rows,
                    'failures': failures},
                   ensure_ascii=False, indent=2), encoding='utf-8')
    write_html(mode, rows, spent)
    report(mode, rows, spent)


def total_input(usage):
    """ПОЛНЫЙ вход, а не «свежая» его часть.

    ⚠️ `OpenAIProvider` разводит вход на непересекающиеся `input` и
    `cached` (см. его докстринг). Сравнивать прогоны по одному `input`
    нельзя: второй вызов подряд читает тот же префикс из кэша, и
    «прирост» получается отрицательным просто потому, что кэш успел
    прогреться, а не потому, что запрос стал короче.
    """
    return usage['input'] + usage['cached']


def added_token_cost(delta_tokens):
    """Деньги за ДОБАВЛЕННЫЕ токены по цене свежего входа.

    Добавка (чертёж или подпись к картинке) стоит в пользовательской
    части запроса, после неизменного ядра, и в кэш префикса не попадает
    никогда — значит тарифицируется полной ценой входа.
    """
    price_in = settings.AI_PRICES[MODEL][0]
    return delta_tokens * price_in / 1_000_000


def population(mode):
    """Сколько задач в банке реально затронет режим."""
    if mode == 'tikz':
        return len(pick_tikz(0))
    return (Problem.objects
            .filter(figures__source_field__in=('import', 'statement'),
                    figures__content_type__in=IMAGE_TYPES)
            .exclude(figures__image_data=None).distinct().count())


def report(mode, rows, spent):
    n = len(rows)
    if not n:
        print('Ни одной задачи не обработано.')
        return
    din = sum(total_input(r['usage_b']) - total_input(r['usage_a'])
              for r in rows) / n
    dmoney = added_token_cost(din)
    print('')
    print('=== ИТОГ (%s), задач %d, потрачено $%.4f ===' % (mode, n, spent))
    print('  сменили тему:        %d из %d' % (sum(r['topic_changed'] for r in rows), n))
    print('  сменили теги:        %d из %d' % (sum(r['tags_changed'] for r in rows), n))
    print('  среднее пересечение тегов (Жаккар): %.3f'
          % (sum(r['tags_jaccard'] for r in rows) / n))
    print('  изменилось «дано»:   %d из %d' % (sum(r['given_changed'] for r in rows), n))
    print('  изменилось «найти»:  %d из %d' % (sum(r['find_changed'] for r in rows), n))
    print('  прирост ПОЛНОГО входа на задачу:   %+.0f токенов' % din)
    print('  прирост денег на задачу:           $%+.6f' % dmoney)
    # Главное число — цена ПЛАСТА, а не всего корпуса: визуальное есть не у
    # каждой задачи, и «на 41 307» завышало бы в разы.
    affected = population(mode)
    print('  задач, которых это касается:       %d из 41 307' % affected)
    print('  цена всего пласта:                 $%+.4f' % (dmoney * affected))
    print('  (для сравнения, если бы касалось всех 41 307: $%+.2f)'
          % (dmoney * 41307))


def esc(value):
    if isinstance(value, (list, tuple)):
        value = ', '.join(str(v) for v in value)
    return html.escape(str(value or '—'))


def write_html(mode, rows, spent):
    title = ('Эффект подстановки чертежа TikZ' if mode == 'tikz'
             else 'Эффект приложенной растровой картинки')
    parts = ["""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>%s</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;font-size:14px;margin:24px;color:#222}
table{border-collapse:collapse;width:100%%;margin-bottom:28px}
td,th{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}
th{background:#f0f0f0}
.stmt{max-width:420px;white-space:pre-wrap;font-size:13px;color:#444}
.diff{background:#fff6d5}
.col{width:32%%}
h2{margin-top:34px;font-size:16px}
.meta{color:#777;font-size:12px}
</style></head><body>
<h1>%s</h1>
<p class="meta">Модель %s, рассуждение «%s», сид %d. Пар в отчёте: %d.
Потрачено по факту usage: $%.4f. Жёлтым помечены поля, которые
изменились. База не менялась.</p>""" % (esc(title), esc(title), MODEL,
                                         EFFORT, SEED, min(10, len(rows)),
                                         float(spent))]
    # Десять пар — не первые попавшиеся: сначала те, где визуальное
    # изменило ТЕМУ или ТЕГИ, потом остальные. Первые по id показали бы
    # владельцу в основном пары-близнецы, а решение он принимает по
    # расхождениям.
    ranked = sorted(rows, key=lambda r: (not r['topic_changed'],
                                         not r['tags_changed'],
                                         r['tags_jaccard']))
    for row in ranked[:10]:
        parts.append('<h2>Задача #%d%s</h2>' % (
            row['problem_id'],
            (' — приложено картинок: %d' % row['images']) if row['images']
            else (' — чертежей подставлено: %d' % row['stats']['replaced'])))
        parts.append('<table><tr><th class="col">Условие</th>'
                     '<th class="col">БЕЗ визуального</th>'
                     '<th class="col">С визуальным</th></tr><tr>')
        parts.append('<td class="stmt">%s</td>' % esc(row['statement']))
        for side in ('a', 'b'):
            other = 'b' if side == 'a' else 'a'
            cells = []
            for field in FIELDS:
                changed = row[side][field] != row[other][field]
                cells.append('<div%s><b>%s:</b> %s</div>' % (
                    ' class="diff"' if changed else '', field,
                    esc(row[side][field])))
            usage = row['usage_%s' % side]
            cells.append('<div class="meta">вход %d (кэш %d), выход %d, $%.5f</div>'
                         % (usage['input'], usage['cached'], usage['output'],
                            row['cost_%s' % side]))
            parts.append('<td>%s</td>' % ''.join(cells))
        parts.append('</tr></table>')
    parts.append('</body></html>')
    path = OUT_DIR / ('%s_effect.html' % mode)
    path.write_text('\n'.join(parts), encoding='utf-8')
    print('HTML: %s' % path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['tikz', 'raster'], required=True)
    parser.add_argument('--limit', type=int, default=0,
                        help='0 — вся совокупность (для tikz это 2 задачи).')
    parser.add_argument('--max-cost', type=float, default=None,
                        help='Потолок по ФАКТИЧЕСКОМУ usage, не по смете. '
                             'Обязателен, кроме --report-only.')
    parser.add_argument('--report-only', action='store_true',
                        help='Пересчитать итог из уже сохранённого JSON — '
                             'без единого обращения к API.')
    args = parser.parse_args()
    if args.report_only:
        saved = json.loads((OUT_DIR / ('%s_effect.json' % args.mode))
                           .read_text(encoding='utf-8'))
        report(args.mode, saved['rows'], Decimal(str(saved['spent'])))
        write_html(args.mode, saved['rows'], Decimal(str(saved['spent'])))
        return
    if args.max_cost is None:
        parser.error('--max-cost обязателен: прогона без потолка не бывает.')
    run(args.mode, args.limit, args.max_cost)


if __name__ == '__main__':
    main()
