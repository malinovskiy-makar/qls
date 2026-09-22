"""Разбор сданной попытки ВП: объясняет уже посчитанное, сам баллов не считает.

⚠️ Арифметики баллов здесь НЕТ. Баллы за задания берутся из `VPAnswer` (их записала
сдача), объяснение долей — у `scoring.explain_item`, буквы змейки — у
`loader.chain_letters`. Модуль только раскладывает готовое по строкам экрана.

⚠️ ОТВЕТЫ НЕОТВЕЧЕННЫХ ЗАДАНИЙ СЮДА НЕ ПОПАДАЮТ. Разбор строит только владелец
попытки, но у пустого задания эталона, верных вариантов и решения в строке нет:
«Дорешать вне зачёта» (`practice_check`) должно проверять, а не читать готовое с
экрана. Их отдаёт только проверка ответа.
"""
from bisect import bisect_left
from decimal import Decimal
from statistics import median

from django.core.cache import cache

from vp import blocks, scoring
from vp.loader import chain_letters
from vp.models import VPAttempt, VPItem

#: Меньше стольких людей — процентиля нет: «вы лучше 100% участников» на трёх
#: попытках было бы враньём.
MIN_COHORT = 20
COHORT_TTL = 300

_ZERO = Decimal('0.00')


def _answers(attempt):
    return {a.item_id: a for a in attempt.answers.all()}


def _numbers(value):
    """Номера вариантов из ответа или эталона: целое или список целых."""
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, (list, tuple)):
        return sorted(n for n in value if isinstance(n, int) and not isinstance(n, bool))
    return []


# ------------------------------------------------------------------ змейка

def _first_letter(item):
    """Первая буква эталона: из данных загрузчика, а если поле пусто — из самого ответа."""
    return item.chain_first or chain_letters(item.chain_word())[0]


def _second_letter(raw):
    """Вторая буква первого слова МОЕГО ответа (нормализация — как у проверки)."""
    words = scoring.normalize_short(raw).split()
    return chain_letters(words[0])[1] if words else ''


def chain_review(attempt):
    """Разбор змейки: по строке на задание блока `snake`, по возрастанию номера.

    Разрыв цепи: вторая буква первого слова МОЕГО ответа не совпала с первой буквой
    СЛЕДУЮЩЕГО ЭТАЛОНА. Сравнение не со следующим моим ответом: иначе одна ошибка
    красила бы весь хвост. Разрыв помечает строку, ПОСЛЕ которой цепь порвалась.
    Неотвеченное задание разрыва не даёт. Буква-связка — та, на какую должен
    начинаться следующий ответ (`link_letter`); у последней строки блока её нет.

    ⚠️ Сравнение чисто буквенное: верно засчитанный ответ-синоним из `accepted` с
    другой второй буквой тоже даст разрыв — цепь у него действительно другая.
    """
    items = list(attempt.variant.items.filter(block=VPItem.Block.SNAKE).order_by('number'))
    answers = _answers(attempt)
    rows = []
    for index, item in enumerate(items):
        answer = answers.get(item.pk)
        raw = answer.raw if answer else None
        blank = scoring.is_blank(raw)
        following = items[index + 1] if index + 1 < len(items) else None
        link = _first_letter(following) if following else ''
        mine = '' if blank else _second_letter(raw)
        rows.append({
            'item': item,
            'number': item.number,
            # Условие нужно только там, где его будут дорешивать (пустое задание).
            'statement': item.statement if blank else '',
            'prefix': item.prefix, 'suffix': item.suffix,
            'mine': '' if blank else str(raw).strip(),
            'right': '' if blank else item.answer,
            'is_correct': None if blank else answer.is_correct,
            'score': (answer.score if answer and answer.score is not None else _ZERO),
            'blank': blank,
            'link_letter': link,
            'my_letter': mine,
            'broke_chain': bool(not blank and link and mine != link),
        })
    return rows


# ------------------------------------------------------------ тесты 31–44

def right_answer(item):
    """Эталон словами: короткий ответ или «3. вариант» через «;» для выбора."""
    if item.kind == VPItem.Kind.SHORT_TEXT:
        return item.answer
    correct = set(_numbers(item.correct))
    return '; '.join(f"{o['n']}. {o['text']}" for o in (item.options or [])
                     if isinstance(o, dict) and o.get('n') in correct)


def tests_review(attempt):
    """Разбор заданий вне змейки (31–44): что выбрано, что верно, откуда балл.

    Для неотвеченного задания эталон, верные варианты, разбор баллов и решение НЕ
    кладутся в строку вовсе (см. модуль): их отдаст `practice_check` после ответа.
    """
    answers = _answers(attempt)
    rows = []
    items = attempt.variant.items.exclude(block=VPItem.Block.SNAKE).order_by('number')
    for item in items:
        answer = answers.get(item.pk)
        raw = answer.raw if answer else None
        blank = scoring.is_blank(raw)
        chosen = [] if blank else _numbers(raw)
        correct = [] if blank else _numbers(item.correct)
        rows.append({
            'item': item,
            'number': item.number,
            'block_title': blocks.TITLES.get(item.block, {}).get('short', item.block),
            'statement': item.statement,
            'kind': item.kind,
            'options': [{'n': o['n'], 'text': o['text'],
                         'chosen': o['n'] in chosen, 'right': o['n'] in correct}
                        for o in (item.options or []) if isinstance(o, dict) and 'n' in o],
            'blank': blank,
            'is_correct': None if blank else answer.is_correct,
            'tone': ('blank' if blank else 'ok' if answer.is_correct
                     else 'mid' if answer.score and answer.score > 0 else 'bad'),
            'score': (answer.score if answer and answer.score is not None else _ZERO),
            'max': item.points,
            'chosen': chosen,
            'correct': correct,
            'explain': None if blank else scoring.explain_item(item, raw),
            'solution': '' if blank else item.solution,
            'figure': item.figure, 'figure_caption': item.figure_caption,
            'figure_source': item.figure_source, 'table_html': item.table_html,
        })
    return rows


# ------------------------------------------------------------- процентиль

def _cohort_key(variant_id):
    return f'vp:pct:{variant_id}'


def _load_cohort(variant):
    """Баллы «когорты» варианта по возрастанию — один балл на ЧЕЛОВЕКА.

    Считаются сданные попытки всего варианта на время (без таймера сравнивать
    нечестно). Человек — пользователь, у гостя — ключ сессии; берётся его САМАЯ
    РАННЯЯ попытка, иначе усердный ученик, прошедший вариант десять раз, перекосил бы
    статистику. Дедупликация — здесь, в Python, а не `distinct('поле')`: тот работает
    только на PostgreSQL, а тесты идут и на SQLite.
    """
    rows = (VPAttempt.objects
            .filter(variant=variant, mode=VPAttempt.Mode.FULL, with_timer=True,
                    submitted_at__isnull=False, score__isnull=False)
            .order_by('started_at', 'id')
            .values('id', 'user_id', 'session_key', 'score'))
    seen, scores = set(), []
    for row in rows:
        # Гость без ключа сессии (в норме не бывает) — сам себе человек, а не «все
        # безымянные разом».
        person = (('u', row['user_id']) if row['user_id']
                  else ('s', row['session_key']) if row['session_key']
                  else ('a', row['id']))
        if person in seen:
            continue
        seen.add(person)
        scores.append(row['score'])
    return sorted(scores)


def _cohort_scores(variant):
    key = _cohort_key(variant.pk)
    scores = cache.get(key)
    if scores is None:
        scores = _load_cohort(variant)
        cache.set(key, scores, COHORT_TTL)
    return scores


def _comparable(attempt):
    """Сравнивать можно только сданное целиком и на время (как и когорту)."""
    return (attempt.submitted_at is not None and attempt.score is not None
            and attempt.mode == VPAttempt.Mode.FULL and attempt.with_timer)


def percentile(attempt):
    """Доля людей когорты со СТРОГО меньшим баллом, в процентах, вниз; или `None`.

    `None` — если попытка несравнима (не сдана, без таймера, не «весь вариант») или
    в когорте меньше `MIN_COHORT` человек: блок сравнения тогда не показывается.
    """
    if not _comparable(attempt):
        return None
    scores = _cohort_scores(attempt.variant)
    if len(scores) < MIN_COHORT:
        return None
    return 100 * bisect_left(scores, attempt.score) // len(scores)


def comparison(attempt):
    """Всё для полосы сравнения: процентиль, медиана и размер когорты — или `None`."""
    percent = percentile(attempt)
    if percent is None:
        return None
    scores = _cohort_scores(attempt.variant)
    return {'percent': percent, 'median': median(scores), 'count': len(scores)}
