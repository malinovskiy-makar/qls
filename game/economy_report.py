# -*- coding: utf-8 -*-
u"""
Замер экономики очков v2 по живым забегам.

⚠️ ЭТО ПРИБОР, А НЕ ТЮНИНГ. Сами числа (BASE_BY_DIFFICULTY, COMBO_STEPS,
SCOPE_MULTIPLIER и прочее) правит человек и только по замеру — правило
проекта «пороги игры тюнить замером, а не на глаз». Пока живых забегов
десятки, крутить нечего; прибор нужен, чтобы было чем мерить, когда они
появятся.

Одна функция `report()` на два потребителя — команду `game_economy_report`
и раздел служебной страницы `/game/stats/`. Второй расчёт того же самого
разошёлся бы с первым при первой же правке.
"""
import collections

from django.db.models import Count

from game import config
from game.models import GameQuestion, GameResult

# Перцентили, которые показываем. Медиана говорит про типичный забег,
# p90 — про хороший, максимум — про потолок шкалы.
PERCENTILES = (50, 90)


def percentile(values, p):
    u"""Перцентиль по отсортированному списку, ближайший ранг.

    Без numpy: список тут в тысячи элементов, а тащить зависимость в
    страницу ради одного числа незачем.
    """
    if not values:
        return None
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round(p / 100.0 * len(values)) - 1)))
    return values[k]


def _bucket_accuracy(correct, total):
    if not total:
        return None
    return correct / float(total)


def report(min_attempts=None):
    u"""Сводка по забегам экономики v2. Ничего не меняет, только читает."""
    min_attempts = (config.STATS_MIN_ATTEMPTS if min_attempts is None
                    else min_attempts)
    rows = list(GameResult.objects.filter(economy_version=2)
                .values('mode', 'score', 'raw_score', 'accuracy_mult',
                        'correct_count', 'wrong_count', 'skip_count',
                        'total_count', 'max_combo', 'avg_correct_ms',
                        'is_unfiltered', 'ranked', 'unranked_reason',
                        'difficulty_breakdown'))

    by_mode = collections.OrderedDict()
    for key, mode in config.MODES.items():
        runs = [r for r in rows if r['mode'] == key]
        scores = [r['score'] for r in runs]
        accs = [a for a in (_bucket_accuracy(r['correct_count'],
                                             r['correct_count']
                                             + r['wrong_count'])
                            for r in runs) if a is not None]
        times = [r['avg_correct_ms'] for r in runs if r['avg_correct_ms']]
        # Доля забегов, у которых точность СНИЗИЛА итог. Это главный тормоз
        # угадывания, и надо видеть, срабатывает ли он вообще.
        penalized = [r for r in runs if (r['accuracy_mult'] or 1.0) < 1.0]
        # Сколько итога дали множители сверх сырых очков: если сырые очки
        # почти равны итогу, множители не работают.
        raw = sum(r['raw_score'] for r in runs)
        final = sum(r['score'] for r in runs)
        by_mode[key] = {
            'key': key,
            'title': mode['title'],
            'runs': len(runs),
            'score_p50': percentile(scores, 50),
            'score_p90': percentile(scores, 90),
            'score_max': max(scores) if scores else None,
            'accuracy_p50': (round(percentile(accs, 50) * 100)
                             if accs else None),
            'penalized_share': (round(100.0 * len(penalized) / len(runs))
                                if runs else None),
            'unfiltered_share': (round(100.0 * sum(
                1 for r in runs if r['is_unfiltered']) / len(runs))
                if runs else None),
            'raw_total': raw,
            'final_total': final,
            'mult_gain': (round(100.0 * (final - raw) / raw)
                          if raw else None),
            'avg_correct_s': (round(percentile(times, 50) / 1000.0, 1)
                              if times else None),
            'think_s': config.THINK_S.get(key),
        }

    # Причины незачётности — закрытым списком, в порядке проверки.
    reasons = collections.OrderedDict(
        (key, {'key': key, 'text': text, 'n': 0})
        for key, text in config.UNRANKED_REASONS)
    unranked = 0
    for r in rows:
        if r['ranked']:
            continue
        unranked += 1
        item = reasons.get(r['unranked_reason'])
        if item is not None:
            item['n'] += 1

    # Доля верных по ЭФФЕКТИВНОЙ сложности: появились ли 5★ по замеру.
    by_diff = collections.OrderedDict(
        (d, {'star': d, 'total': 0, 'correct': 0}) for d in range(1, 6))
    for r in rows:
        for item in (r['difficulty_breakdown'] or []):
            try:
                star = int(item.get('key'))
            except (TypeError, ValueError):
                continue
            if star in by_diff:
                by_diff[star]['total'] += int(item.get('total') or 0)
                by_diff[star]['correct'] += int(item.get('correct') or 0)
    for item in by_diff.values():
        item['share'] = (round(100.0 * item['correct'] / item['total'])
                         if item['total'] else None)

    # Кандидаты на чистку пула: почти никто не решает или решают все.
    # Считаем ТОЛЬКО по вопросам с достаточным числом попыток — иначе это
    # шум, а не сложность (то же правило, что у измеренной сложности).
    from game import stats as stats_mod
    questions = list(GameQuestion.objects.all().only(
        'id', 'question', 'question_type', 'problem_id', 'is_generated'))
    by_id = stats_mod.bulk_stats(questions)
    hard, trivial = [], []
    for gq in questions:
        st = by_id.get(gq.id)
        if not st or st.attempts < min_attempts:
            continue
        row = {'id': gq.id, 'problem_id': gq.problem_id,
               'text': (gq.question or '')[:120],
               'attempts': st.attempts,
               'share': round(100 * st.p_correct)}
        if st.p_correct < config.STATS_BROKEN_BELOW:
            hard.append(row)
        elif st.p_correct > config.STATS_TRIVIAL_ABOVE:
            trivial.append(row)
    hard.sort(key=lambda r: r['share'])
    trivial.sort(key=lambda r: -r['share'])

    return {
        'total_runs': len(rows),
        'unranked': unranked,
        'by_mode': list(by_mode.values()),
        'reasons': [r for r in reasons.values() if r['n']],
        'by_difficulty': list(by_diff.values()),
        'hard': hard[:10],
        'trivial': trivial[:10],
        'min_attempts': min_attempts,
        'pool_total': GameQuestion.objects.count(),
        'pool_by_type': dict(
            GameQuestion.objects.values_list('question_type')
            .annotate(n=Count('id')).values_list('question_type', 'n')),
    }
