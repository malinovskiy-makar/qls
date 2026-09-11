# -*- coding: utf-8 -*-
"""Метрики офлайн-замера по градуированным меткам.

Шкала одна на всё: 2 — годится, 1 — спорно, 0 — не годится. Так размечал
владелец вручную, так же отвечают судьи; смешивать две шкалы в одном
отчёте нельзя.

⚠️ Неразмеченный кандидат считается НЕ годным, а не пропускается. Это
осознанный выбор в пользу строгости: пропуск позволял бы системе поднять
precision, вытащив в топ то, чего никто не смотрел. Насколько это давит
на числа, видно по `labelled_share` — она печатается рядом с каждой
метрикой, а не прячется.
"""
import math

GOOD = 2


def _labels_of(ranked, labels, k):
    return [labels.get(pid, 0) for pid in ranked[:k]]


def precision_at_k(ranked, labels, k):
    """Доля «годится» среди показанных.

    Делится на число ПОКАЗАННЫХ, а не на k: выдача короче k — свойство
    пула, а не промах системы, и штрафовать за него значит мерить размер
    пула вместо качества ранжирования.
    """
    shown = _labels_of(ranked, labels, k)
    if not shown:
        return 0.0
    return sum(1 for label in shown if label >= GOOD) / len(shown)


def precision_among_labelled(ranked, labels, k):
    """Верхняя оценка: доля «годится» СРЕДИ РАЗМЕЧЕННЫХ показанных.

    Пара к `precision_at_k`, а не замена ей. Строгая метрика — нижняя
    граница (неразмеченное считается негодным), эта — верхняя
    (неразмеченного как бы нет). Обе нужны там, где полнота разметки у
    систем разная: на ручной разметке владельца у плотной ноги размечено
    73 % топ-10, у лексической — 30 %, и одна строгая цифра сказала бы
    про полноту разметки, а не про качество выдачи.

    `None`, а не ноль, когда размеченных нет вовсе: ноль означал бы «всё
    плохо», а это «мерить нечем».
    """
    shown = [pid for pid in ranked[:k] if pid in labels]
    if not shown:
        return None
    return sum(1 for pid in shown if labels[pid] >= GOOD) / len(shown)


def ndcg_at_k(ranked, labels, k):
    """nDCG@k по градациям 2/1/0, прирост 2^метка − 1.

    Идеал считается по МЕТКАМ ЭТОГО ЗАПРОСА целиком, а не по показанным:
    система, не нашедшая годную задачу вовсе, обязана получить за это
    меньше единицы.
    """
    gains = [2 ** label - 1 for label in _labels_of(ranked, labels, k)]
    dcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(gains))
    ideal = sorted((2 ** label - 1 for label in labels.values()), reverse=True)[:k]
    idcg = sum(gain / math.log2(i + 2) for i, gain in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def has_n_good(ranked, labels, n, k):
    """Есть ли в топ-k хотя бы n «годится»."""
    return sum(1 for label in _labels_of(ranked, labels, k)
               if label >= GOOD) >= n


def labelled_share(ranked, labels, k):
    """Доля размеченных среди показанных — честность метрик выше."""
    shown = ranked[:k]
    if not shown:
        return 0.0
    return sum(1 for pid in shown if pid in labels) / len(shown)


def anchor_recall(runs, anchors, k):
    """Старая метрика по одному якорю — для справки, не для решения.

    Оставлена, чтобы новые числа можно было приложить к прежним отчётам.
    На пуле она заведомо занижена: якорь у половины запросов вне топ-30
    обеих ног (замер фазы 1).
    """
    if not runs:
        return 0.0
    hits = sum(1 for ranked, anchor in zip(runs, anchors)
               if anchor in ranked[:k])
    return hits / len(runs)
