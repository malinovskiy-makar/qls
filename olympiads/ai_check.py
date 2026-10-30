"""Проверка решения задания тура моделью по критериям жюри (ночь 30.10, Э7).

По образцу `catalog/attempts.py`: сборка запроса, схема ответа, валидация
на своей стороне. Решение владельца 30.10 (карточка «Решения»
408b11c9…): развёрнутое олимпиадное решение проверяет ИИ по официальным
критериям; критериев нет — ИИ балл не ставит, ученик видит эталон.

⚠️ ЧТО УХОДИТ НАРУЖУ — ТОЛЬКО ЭТО: условие задания и пунктов, критерии и
правила жюри, максимум за задание, текст решения ученика и картинки его
листов (расшифровка — `catalog.attachments.recognise`). Ни имени, ни почты,
ни логина, ни класса (P0, `problems/ai/CLAUDE.md`). Эталонное решение не
уходит: оценка — по критериям. Пользователь передаётся в `core.run` лишь
ради лимита и журнала расхода.

⚠️ ВАЛИДАЦИЯ ОБЯЗАТЕЛЬНА: код только из списка (каждый ровно раз), балл не
больше максимума критерия и кратен 0,5, сумма не больше максимума задания.
Иначе — статус `error`, балла нет, страница не падает.
"""
import re
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from problems.ai import core

from .criteria import split_solution

PROFILE = 'olympiad_check'
VERDICTS = ('ok', 'part', 'miss')
SUMMARY_MAX = 600
WHY_MAX = 400
APPROX_NOTE = 'КРИТЕРИИ НЕ РАЗОБРАНЫ ПО БАЛЛАМ: поставь один общий балл задания.'
OFF_SCHEMA = 'Проверка вернула ответ не по критериям — балл не поставлен.'

_CODE = r'[KК]\s?\d{1,3}'
# «- K1 Текст → 1 балл», «K7. Нахождение p₃ — 1 балл», «K2 … → 2 балла».
_SCORED = re.compile(
    r'^\s*[-*•]?\s*(' + _CODE + r')[.:)]?\s+(.*?)\s*(?:→|—|–|->|-)\s*'
    r'(\d+(?:[.,]\d+)?)\s*балл\w*\s*\.?\s*$', re.IGNORECASE)
_RULE = re.compile(r'^\s*[-*•]?\s*(' + _CODE + r')[.:)]?\s+(.+?)\s*$', re.IGNORECASE)
_PART = re.compile(r'^\s*([а-яa-z])\)\s')

CHECK_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['criteria', 'summary'],
    'properties': {
        'criteria': {
            'type': 'array',
            'items': {
                'type': 'object', 'additionalProperties': False,
                'required': ['code', 'score', 'verdict', 'why'],
                'properties': {
                    'code': {'type': 'string'},
                    'score': {'type': 'number'},
                    'verdict': {'type': 'string', 'enum': list(VERDICTS)},
                    'why': {'type': 'string'},
                },
            },
        },
        'summary': {'type': 'string'},
    },
}
APPROX_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['score', 'summary'],
    'properties': {'score': {'type': 'number'}, 'summary': {'type': 'string'}},
}


def _code(raw):
    """«К 7» / «k7» → «K7»: одна запись кода (латинская K)."""
    return 'K' + re.sub(r'\D', '', raw)


def parse_criteria(text):
    """Критерии жюри → (критерии с баллами, правила, части).

    Критерий — строка с кодом и баллом в конце: `{code, text, max, part}`.
    Правило — строка с кодом БЕЗ балла («K7 Если…, то…»): уходит модели
    целиком. Часть — метка пункта («а)»), под которой стоит критерий.
    """
    scored, rules = [], []
    part = ''
    for line in (text or '').splitlines():
        head = _PART.match(line)
        if head:
            part = head.group(1)
        found = _SCORED.match(line)
        if found:
            scored.append({'code': _code(found.group(1)),
                           'text': found.group(2).strip(),
                           'max': float(found.group(3).replace(',', '.')),
                           'part': part})
            continue
        found = _RULE.match(line)
        if found:
            rules.append({'code': _code(found.group(1)),
                          'text': found.group(2).strip(), 'part': part})
    return scored, rules


def plan(problem, maximum):
    """Как проверять: `None` — критериев нет (модель не зовём), иначе словарь.

    Сумма максимумов разобранных критериев ≠ максимуму задания → проверка
    целиком по тексту критериев одним баллом, «ориентировочно».
    """
    _reference, text = split_solution(problem.solution)
    if not text.strip():
        return None
    scored, rules = parse_criteria(text)
    total = sum(c['max'] for c in scored)
    exact = bool(scored) and maximum is not None and \
        abs(total - float(maximum)) < 1e-6
    return {'text': text, 'criteria': scored if exact else [],
            'rules': rules if exact else [], 'approximate': not exact,
            'maximum': float(maximum) if maximum is not None else total}


def build_prompt(problem, parts, how, student_text, ocr_text=''):
    """Пользовательская часть запроса — только текст задания и решения."""
    lines = ['УСЛОВИЕ:', (problem.statement or '').strip()]
    for part in parts:
        if (part.statement or '').strip():
            lines.append('%s) %s' % ((part.label or '').strip().rstrip(').') or '?',
                                     part.statement.strip()))
    lines.append('МАКСИМУМ ЗА ЗАДАНИЕ: %s' % _num(how['maximum']))
    if how['approximate']:
        lines += [APPROX_NOTE, 'КРИТЕРИИ ЖЮРИ (как есть):', how['text'].strip()]
    else:
        lines.append('КРИТЕРИИ ЖЮРИ:')
        lines += ['- %s (максимум %s): %s' % (c['code'], _num(c['max']), c['text'])
                  for c in how['criteria']]
        if how['rules']:
            lines.append('ПРАВИЛА ЖЮРИ:')
            lines += ['- %s: %s' % (r['code'], r['text']) for r in how['rules']]
    # Эталонный ответ — для сверки чисел (день 30.10, У2): полей краткого
    # ответа у развёрнутой задачи больше нет, машина его не сверяет. Эталонное
    # РЕШЕНИЕ по-прежнему не передаётся (решение ночи 31).
    reference = [(problem.answer or '').strip()] + [
        '%s) %s' % ((part.label or '').strip().rstrip(').') or '?', part.answer.strip())
        for part in parts if (part.answer or '').strip()]
    reference = [line for line in reference if line]
    if reference:
        lines += ['ЭТАЛОННЫЙ ОТВЕТ ЖЮРИ (только для сверки; балл — по критериям):'] + reference
    lines += ['РЕШЕНИЕ УЧЕНИКА:', (student_text or '').strip() or '(текстом не дано)']
    if (ocr_text or '').strip():
        lines += ['ТЕКСТ, РАСПОЗНАННЫЙ С ФОТО ЛИСТОВ:', ocr_text.strip()]
    return '\n'.join(lines)


def _num(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else ('%.1f' % value).replace('.', ',')


def _half(value):
    """Число, кратное 0,5, иначе None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if abs(value * 2 - round(value * 2)) > 1e-6:
        return None
    return float(value)


def validate(data, how):
    """Ответ модели → нормализованный словарь; вне схемы или правил → None."""
    if not isinstance(data, dict):
        return None
    summary = str(data.get('summary') or '').strip()[:SUMMARY_MAX]
    maximum = how['maximum']
    if how['approximate']:
        score = _half(data.get('score'))
        if score is None or not 0 <= score <= maximum:
            return None
        return {'score': score, 'criteria': [], 'summary': summary}
    rows = data.get('criteria')
    if not isinstance(rows, list):
        return None
    known = {c['code']: c for c in how['criteria']}
    seen, out = set(), []
    for row in rows:
        if not isinstance(row, dict):
            return None
        code = _code(str(row.get('code') or '')) if row.get('code') else ''
        if code not in known or code in seen:
            return None
        seen.add(code)
        score = _half(row.get('score'))
        if score is None or not 0 <= score <= known[code]['max']:
            return None
        if row.get('verdict') not in VERDICTS:
            return None
        out.append({'code': code, 'text': known[code]['text'],
                    'max': known[code]['max'], 'part': known[code]['part'],
                    'score': score, 'verdict': row['verdict'],
                    'why': str(row.get('why') or '').strip()[:WHY_MAX]})
    if seen != set(known):
        return None
    total = sum(r['score'] for r in out)
    if total > maximum + 1e-6:
        return None
    order = {c['code']: n for n, c in enumerate(how['criteria'])}
    out.sort(key=lambda r: order[r['code']])
    return {'score': total, 'criteria': out, 'summary': summary}


# ---------------------------------------------------------------------------
# Кому и когда
# ---------------------------------------------------------------------------

def enabled():
    return bool(getattr(settings, 'OLYMPIAD_AI_CHECK', False))


def eligible(attempt, item, user):
    """Звать ли модель на это задание: флаг, вошедший с согласием, не тест,
    есть критерии, есть что проверять. Нет — `None` (и ни одного вызова)."""
    from problems.assignment_rows import item_answer_form, item_max_score

    from legal.guards import ai_consent_missing

    if not enabled() or user is None or not getattr(user, 'is_authenticated', False):
        return None
    if attempt.user_id != user.pk or ai_consent_missing(user):
        return None
    kind, _options = item_answer_form(item)
    if kind in ('radio', 'checkbox'):
        return None
    problem = item.catalog_problem
    # Максимум — балл позиции пакета; неизвестен — сумма критериев жюри, а
    # не служебные 10 (день 30.10, У4). Комплект без позиций — как раньше.
    from . import training_engine as engine
    points = engine.package_points(attempt.variant)
    maximum = points.get(problem.pk) if points else item_max_score(item)
    how = plan(problem, maximum)
    if how is None:
        return None
    return how


def _work(attempt, problem):
    from .models import TrainingDraft

    draft = TrainingDraft.objects.filter(attempt=attempt, problem=problem,
                                         part__isnull=True).first()
    text = (draft.solution_draft if draft else '') or ''
    sheets = list(attempt.uploads.filter(problem=problem).order_by('page', 'id'))
    return text, sheets


def enqueue(attempt):
    """При сдаче тура на время: все открытые задания с критериями — в очередь.

    Идемпотентна: уже заведённые проверки не трогает. Возвращает число в очереди.
    """
    from . import training_engine as engine
    from .models import TrainingCheck

    if attempt.submitted_at is None or attempt.user is None:
        return 0
    have = set(attempt.checks.values_list('problem_id', flat=True))
    for item in engine.variant_items(attempt.variant):
        problem = item.catalog_problem
        if problem.pk in have:
            continue
        how = eligible(attempt, item, attempt.user)
        text, sheets = _work(attempt, problem)
        if how is None or not (text.strip() or sheets):
            continue
        TrainingCheck.objects.create(attempt=attempt, problem=problem,
                                     max_score=Decimal(str(how['maximum'])),
                                     approximate=how['approximate'])
    return attempt.checks.filter(status=TrainingCheck.Status.QUEUED).count()


def check_item(attempt, item, user, timeout=None):
    """Проверить одно задание (режим «Без времени» — сразу после сдачи)."""
    from .models import TrainingCheck

    how = eligible(attempt, item, user)
    if how is None:
        return None
    check, _ = TrainingCheck.objects.get_or_create(
        attempt=attempt, problem=item.catalog_problem,
        defaults={'max_score': Decimal(str(how['maximum'])),
                  'approximate': how['approximate']})
    if check.status in (TrainingCheck.Status.DONE, TrainingCheck.Status.ERROR):
        return check
    return run(check, item, user, how, timeout=timeout)


def run_next(attempt, user):
    """Страница результата: проверить ОДНО задание из очереди за запрос."""
    from . import training_engine as engine
    from .models import TrainingCheck

    check = (attempt.checks.filter(status=TrainingCheck.Status.QUEUED)
             .order_by('id').first())
    if check is None:
        return None
    item = next(i for i in engine.variant_items(attempt.variant)
                if i.catalog_problem_id == check.problem_id)
    how = eligible(attempt, item, user)
    if how is None:
        check.status = TrainingCheck.Status.UNAVAILABLE
        check.finished_at = timezone.now()
        check.save(update_fields=['status', 'finished_at'])
        return check
    return run(check, item, user, how)


def run(check, item, user, how, timeout=None):
    """Расшифровать листы, спросить модель, проверить ответ, записать итог."""
    from catalog import attachments

    from . import training_engine as engine
    from .models import TrainingCheck, TrainingItemResult

    problem = item.catalog_problem
    check.status = TrainingCheck.Status.RUNNING
    check.save(update_fields=['status'])
    text, sheets = _work(check.attempt, problem)
    cost = Decimal(0)
    try:
        if sheets:
            # ⚠️ Тот же путь, что у фото к попытке в «Столе»: лист — как
            # `FileAsset` (у обоих есть `.file`); наружу — только байты.
            check.transcription = '\n\n'.join(
                t for t in (attachments.recognise(sheet, user) for sheet in sheets) if t)
        prompt = build_prompt(problem, list(problem.parts.all()), how, text,
                              check.transcription)
        result = core.run(PROFILE, prompt,
                          APPROX_SCHEMA if how['approximate'] else CHECK_SCHEMA,
                          user, timeout=timeout)
        if not result.cached:
            cost += Decimal(str((result.usage or {}).get('cost_usd', 0)))
        data = validate(result.data, how)
    except core.AiUnavailable as exc:
        check.status = TrainingCheck.Status.UNAVAILABLE
        check.summary = str(exc)[:SUMMARY_MAX]
        check.finished_at = timezone.now()
        check.cost = cost
        check.save()
        return check
    check.provider = getattr(core._provider(), 'name', '')
    check.model = getattr(settings, 'AI_MODEL', '') or core.DEFAULT_MODEL
    check.cost = cost
    check.finished_at = timezone.now()
    if data is None:
        check.status = TrainingCheck.Status.ERROR
        check.summary = OFF_SCHEMA
        check.criteria = []
        check.score = None
        check.save()
        return check
    check.status = TrainingCheck.Status.DONE
    check.score = Decimal(str(data['score']))
    check.criteria = data['criteria']
    check.summary = data['summary']
    check.approximate = how['approximate']
    check.save()
    # Итог ИИ — в итог задания: балл есть, «ждёт проверки» снято.
    TrainingItemResult.objects.filter(attempt=check.attempt, problem=problem).update(
        score=check.score, max_score=Decimal(str(how['maximum'])),
        is_pending=False, comment=check.summary[:500])
    engine.recount(check.attempt)
    return check


def by_part(check):
    """Разбор для экрана: [(часть, набрано, максимум, [критерии])]."""
    groups, order = {}, []
    for row in check.criteria or []:
        key = row.get('part', '')
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    return [{'part': key, 'score': sum(r['score'] for r in groups[key]),
             'max': sum(r['max'] for r in groups[key]), 'rows': groups[key]}
            for key in order]
