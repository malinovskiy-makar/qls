"""Какая версия задачи внутри кластера дублей выглядит лучше остальных.

Ничего не удаляет, не скрывает и не схлопывает. Считает объяснимый счёт по
УЖЕ СУЩЕСТВУЮЩИМ сигналам качества и помечает лучшего в кластере — чтобы
позже, отдельной работой, было чем выбрать каноническую версию для показа.

⚠️ НИ ОДИН СИГНАЛ ЗДЕСЬ НЕ ПРИДУМАН — все взяты из того, что проект уже
считает и чему уже доверяет:

  human_review          `human_review_mark` по вердиктам живых ревьюеров
  status                'duplicate' / 'hidden' / 'draft' / 'archived'
  needs_quality_review  шлюз качества `quality_gate` (битый рендер условия)
  solution_needs_review тот же шлюз, но про решение
  дефекты текста        `text_clean.defects()` — шесть именованных признаков
  пропавшие картинки    маркер `[[FIGURE:<hex>]]` без строки `ProblemFigure`;
                        тот же признак, что код `FIGURE-MISSING` в
                        `corpus_converter/preflight_gate.py`
  content_format        `markdown` — новый math-aware конвейер, `plain` —
                        легаси-поведение (миграция 0045)
  пустые подпункты      доля `ProblemPart` с пустым `statement`
  длина условия         обрезанная версия задачи короче полной

⚠️ `hidden_pending_review` В СЧЁТ НЕ ВХОДИТ, И ЭТО НЕ ЗАБЫВЧИВОСТЬ.
Комментарий к полю в `models.py` говорит прямо: это «скрыто, потому что
человек ЕЩЁ НЕ СМОТРЕЛ», а не оценка качества. На 2026-09-02 флаг стоит у
26 832 задач из 41 307 — почти две трети банка. Считать его признаком
плохого значило бы наказывать задачу за то, что до неё не дошла очередь.

⚠️ ВЕСА ПОДОБРАНЫ ПО ПОРЯДКУ ДОВЕРИЯ, А НЕ ПО ТОЧНОСТИ. Человек, посмотревший
задачу, весит больше машины; машина, отрендерившая условие, — больше
косвенного признака вроде формата импорта. Счёт нужен только для СРАВНЕНИЯ
внутри кластера одинаковых задач, где всё остальное совпадает; абсолютное
значение смысла не имеет и никуда, кроме отчёта, не идёт.
"""
from problems.text_clean import defects

# Маркер картинки в тексте задачи — тот же, что в `problems/figures.py`.
FIGURE_MARKER = '[[FIGURE:'

#: Человеческие названия слагаемых — одни и те же в отчёте и в CSV.
COMPONENT_NAMES = {
    'human_review': 'вердикт живого ревьюера',
    'status': 'статус задачи',
    'quality_gate': 'шлюз качества: рендер условия',
    'solution_gate': 'шлюз качества: рендер решения',
    'figures_missing': 'картинка потеряна (маркер без файла)',
    'text_defects': 'признаки порчи текста',
    'content_format': 'формат импорта',
    'empty_parts': 'пустые подпункты',
    'length': 'длина условия',
}

_HUMAN_REVIEW = {'approved': 3.0, 'defect': -3.0}
_STATUS = {'published': 0.0, 'draft': -1.0, 'hidden': -2.0,
           'archived': -2.0, 'duplicate': -3.0}

# Дальше этой длины прибавка за объём перестаёт расти: иначе длинная, но
# грязная версия перевесила бы короткую и чистую.
LENGTH_CAP = 1000


def _figure_markers(text):
    """Сколько маркеров картинок стоит в тексте."""
    return (text or '').count(FIGURE_MARKER)


def quality_components(*, human_review='', status='published',
                       needs_quality_review=False,
                       solution_needs_review=False,
                       content_format='plain', text='',
                       figure_rows=0, part_statements=()):
    """Слагаемые счёта по отдельности — чтобы отчёт назвал, что сыграло.

    Чистая функция: принимает значения, а не объект модели. Так её можно
    проверить без базы и так видно, что именно входит в оценку.
    """
    markers = _figure_markers(text)
    missing_figures = max(0, markers - figure_rows)
    parts = list(part_statements)
    empty_share = (sum(1 for p in parts if not (p or '').strip()) / len(parts)
                   if parts else 0.0)
    return {
        'human_review': _HUMAN_REVIEW.get(human_review, 0.0),
        'status': _STATUS.get(status, 0.0),
        'quality_gate': -2.0 if needs_quality_review else 0.0,
        'solution_gate': -0.5 if solution_needs_review else 0.0,
        # Потерянная картинка бьёт больно, но не бесконечно: две потери и
        # десять — одинаково «рисунка нет».
        'figures_missing': -min(missing_figures, 2) * 1.0,
        # Шесть именованных признаков порчи, по полбалла за каждый.
        'text_defects': -0.5 * len(defects(text)),
        'content_format': 0.5 if content_format == 'markdown' else 0.0,
        'empty_parts': -1.0 * empty_share,
        'length': min(len(text or ''), LENGTH_CAP) / LENGTH_CAP,
    }


def quality_score(components):
    """Один счёт из слагаемых. Больше — лучше."""
    return round(sum(components.values()), 4)


def pick_best(scores):
    """Победитель кластера: наибольший счёт, при ничьей — наименьший id.

    ⚠️ ПРАВИЛО НИЧЬЕЙ ДЕТЕРМИНИРОВАНО НАМЕРЕННО. Кластер из побайтово
    одинаковых задач даёт ровно равные счета сплошь и рядом, и без явного
    правила победитель зависел бы от порядка выборки из базы — то есть
    менялся бы от прогона к прогону. Наименьший `problem_id` — это версия,
    попавшая в банк раньше.

    Возвращает `(problem_id, была_ли_ничья)`.
    """
    if not scores:
        return None, False
    best = max(scores.values())
    winners = sorted(pid for pid, score in scores.items() if score == best)
    return winners[0], len(winners) > 1


def explain(components, other_components):
    """Чем победитель отличается от соперника — только различающиеся слагаемые.

    Итоговый счёт говорит «лучше», но не говорит «чем». Отчёту нужно
    второе.
    """
    return {
        name: (round(components[name], 3), round(other_components[name], 3))
        for name in components
        if abs(components[name] - other_components.get(name, 0.0)) > 1e-9
    }
