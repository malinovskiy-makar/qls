"""Формат файла разметки `ai_exam_review/2` и его проверка.

Файл отдаёт страница проверки (`problems/ai_exam/page.py`), принимает —
следующая сессия («Экзамен B»). Проверка здесь, рядом с форматом, чтобы
страница и приёмщик не разошлись в понимании одного и того же файла.

Плохая строка — ЖАЛОБА, а не падение: годные строки возвращаются, даже
если соседние плохи. Человек проверял полсотни задач, и одна опечатка в
ключе не должна выбрасывать остальные.

У вопроса может быть несколько чисел (цена и количество), у каждого своя
подпись; вопрос, ответ на который не число («объясните», «постройте
график»), помечается `skip` и из проверки выпадает. Формат 1 (одно число на
вопрос) не принимается: файлов в нём не существует.

    {"format": "ai_exam_review/2", "seed": 20261007, "chunk": 1,
     "reviewer": "…", "exported_at": "…",
     "rows": [{"id": 123, "verdict": "ok" | "bad" | "skip",
               "reason": "", "comment": "",
               "asks": [{"part_id": null, "skip": false,
                         "values": [{"label": "P", "value": "5", "unit": "",
                                     "percent": false, "tol": ""}]}]}]}
"""
from problems.ai_exam.numbers import parse_tol, to_number

FORMAT = 'ai_exam_review/2'

VERDICTS = ('ok', 'bad', 'skip')

#: Причины «Не годится» — ключ и подпись на странице.
REASONS = (
    ('statement', 'условие неполное или битое'),
    ('answer_wrong', 'ответ банка неверный'),
    ('not_numeric', 'ответ не число или неоднозначен'),
    ('needs_figure', 'нужна картинка'),
    ('not_calc', 'не расчётная'),
    ('other', 'другое'),
)
REASON_KEYS = tuple(key for key, _label in REASONS)

#: Десять видов жалоб.
UNKNOWN_ID = 'unknown_id'
UNKNOWN_VERDICT = 'unknown_verdict'
KEY_SHAPE = 'key_shape'
KEY_VALUE = 'key_value'
BAD_TOL = 'bad_tol'
NO_REASON = 'no_reason'
NO_REVIEWER = 'no_reviewer'
NO_VALUES = 'no_values'
LABELS = 'labels'
ALL_SKIPPED = 'all_skipped'


def _complaint(kind, row_id, text):
    return {'kind': kind, 'id': row_id, 'text': text}


def _row_complaints(row, candidates_by_id):
    row_id = row.get('id')
    candidate = candidates_by_id.get(row_id)
    if candidate is None:
        return [_complaint(UNKNOWN_ID, row_id, 'такой задачи нет среди кандидатов')]
    verdict = row.get('verdict')
    if verdict not in VERDICTS:
        return [_complaint(UNKNOWN_VERDICT, row_id,
                           'неизвестный вердикт: %r' % (verdict,))]
    if verdict == 'bad':
        if row.get('reason') not in REASON_KEYS:
            return [_complaint(NO_REASON, row_id, '«Не годится» без причины')]
        return []
    if verdict == 'skip':
        return []

    asks = row.get('asks')
    asks = asks if isinstance(asks, list) else []
    expected = sorted(str(ask.get('part_id')) for ask in candidate['asks'])
    got = sorted(str(a.get('part_id')) if isinstance(a, dict) else '?' for a in asks)
    if got != expected:
        return [_complaint(
            KEY_SHAPE, row_id,
            'вопросов в разметке %d при %d в задаче, или вопрос чужой'
            % (len(asks), len(expected)))]

    complaints = []
    for ask in asks:
        if ask.get('skip'):
            continue
        values = ask.get('values')
        values = [v for v in values if isinstance(v, dict)]             if isinstance(values, list) else []
        if not values:
            complaints.append(_complaint(
                NO_VALUES, row_id,
                'у вопроса %s нет ни одного числа и нет пометки «не проверяется»'
                % (ask.get('part_id'),)))
            continue
        if len(values) > 1:
            labels = [str(v.get('label') or '').strip().casefold() for v in values]
            if '' in labels or len(set(labels)) != len(labels):
                complaints.append(_complaint(
                    LABELS, row_id,
                    'у вопроса %s несколько чисел, а подписи пустые или повторяются'
                    % (ask.get('part_id'),)))
        for item in values:
            if to_number(item.get('value')) is None:
                complaints.append(_complaint(
                    KEY_VALUE, row_id, 'ключ не число: %r' % (item.get('value'),)))
            try:
                parse_tol(item.get('tol'))
            except ValueError:
                complaints.append(_complaint(
                    BAD_TOL, row_id,
                    'допуск не положительное число: %r' % (item.get('tol'),)))
    if all(ask.get('skip') for ask in asks):
        complaints.append(_complaint(
            ALL_SKIPPED, row_id, 'все вопросы «не проверяется» — проверять нечего'))
    return complaints


def validate_review(payload, candidates_by_id):
    """(годные строки, жалобы). `candidates_by_id` — id → строка
    candidates.jsonl (нужны её `asks`).

    Не файл разметки вовсе (не объект, чужой `format`, нет списка `rows`) —
    ValueError: это не опечатка в строке, а не тот файл.
    """
    if not isinstance(payload, dict) or payload.get('format') != FORMAT:
        raise ValueError('это не файл разметки %s' % FORMAT)
    rows = payload.get('rows')
    if not isinstance(rows, list):
        raise ValueError('в файле разметки нет списка rows')

    complaints = []
    if not str(payload.get('reviewer') or '').strip():
        complaints.append(_complaint(NO_REVIEWER, None,
                                     'не указано имя проверяющего'))
    good = []
    for row in rows:
        row_complaints = _row_complaints(row if isinstance(row, dict) else {},
                                         candidates_by_id)
        if row_complaints:
            complaints.extend(row_complaints)
        else:
            good.append(row)
    return good, complaints
