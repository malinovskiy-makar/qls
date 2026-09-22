"""Что кладётся в `VPAnswer.raw`: проверка присланного и запись.

Клиенту не верим ни в чём: номер варианта проверяется по вариантам ЭТОГО задания,
длина ответа ограничена, вид ответа соответствует виду задания. Баллов здесь нет —
их считает только `vp.scoring`, и только при сдаче.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from vp.models import VPAnswer, VPItem

# Длина короткого ответа — как у эталона `VPItem.answer`: больше в ответ не влезет
# ни одно слово змейки, а безразмерный JSON в базу принимать нельзя.
MAX_ANSWER_LENGTH = 200


class AnswerError(ValueError):
    """Ответ не подходит заданию: чужой номер варианта, не тот вид, слишком длинный."""


def _option_numbers(item):
    numbers = set()
    for option in item.options or []:
        number = option.get('n') if isinstance(option, dict) else None
        if isinstance(number, int) and not isinstance(number, bool):
            numbers.add(number)
    return numbers


def _option_number(value, allowed):
    if isinstance(value, bool):
        raise AnswerError('номер варианта — число')
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise AnswerError('номер варианта — число') from None
    if number not in allowed:
        raise AnswerError('такого варианта нет')
    return number


def clean_answer(item, value):
    """Присланное → то, что кладётся в `raw`. Пусто → `None` («не отвечено»)."""
    if item.kind == VPItem.Kind.SHORT_TEXT:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AnswerError('короткий ответ — строка')
        text = value.strip()
        if len(text) > MAX_ANSWER_LENGTH:
            raise AnswerError('ответ длиннее %d знаков' % MAX_ANSWER_LENGTH)
        return text or None

    allowed = _option_numbers(item)
    if item.kind == VPItem.Kind.SINGLE:
        if value in (None, '', []):
            return None
        if isinstance(value, (list, tuple)):
            if len(value) != 1:
                raise AnswerError('в этом задании выбирается один вариант')
            value = value[0]
        return _option_number(value, allowed)

    if item.kind == VPItem.Kind.MULTI:
        if value in (None, '', []):
            return None
        if not isinstance(value, (list, tuple)):
            raise AnswerError('нужен список номеров вариантов')
        numbers = sorted({_option_number(v, allowed) for v in value})
        return numbers or None

    if item.kind == VPItem.Kind.MATCH:
        if value in (None, '', [], {}):
            return None
        if not isinstance(value, dict):
            raise AnswerError('нужен словарь «пара: номер варианта»')
        keys = set(item.correct) if isinstance(item.correct, dict) else set()
        chosen = {}
        for key, option in value.items():
            if key not in keys:
                raise AnswerError('нет такой пары')
            if option in (None, ''):
                continue
            chosen[key] = _option_number(option, allowed)
        return chosen or None

    raise AnswerError('неизвестный вид задания')


def save_answers(attempt, cleaned):
    """Upsert ответов `[(задание, raw), …]`. Пишет ТОЛЬКО `raw`, баллы не трогает.

    ⚠️ ГОНКА ДВУХ СОХРАНЕНИЙ (урок `exam_engine.save_draft`): пачки уходят и по
    таймеру, и при уходе из поля, и на `pagehide`; два запроса по одному заданию
    легко оказываются в полёте одновременно. `update_or_create` делает SELECT →
    INSERT, и второй INSERT ломается об уникальность (attempt, item). Повтор идёт
    обновлением — побеждает тот, кто пришёл последним, что для черновика и нужно.
    """
    for item, raw in cleaned:
        try:
            with transaction.atomic():
                VPAnswer.objects.update_or_create(
                    attempt=attempt, item=item, defaults={'raw': raw})
        except IntegrityError:
            VPAnswer.objects.filter(attempt=attempt, item=item).update(
                raw=raw, updated_at=timezone.now())
