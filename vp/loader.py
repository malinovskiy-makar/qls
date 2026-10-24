"""Загрузчик вариантов «Высшей пробы» из YAML-файлов (`data/vp/*.yaml`).

Три слоя, каждый можно звать отдельно (их зовёт `manage.py import_vp`):

1. `normalize` — файл → словари полей и список ОШИБОК. Ничего не пишет.
2. `summarize`, `find_chain_breaks` — инварианты: число заданий, сумма
   баллов, разбивка по блокам, разрывы цепочки змейки.
3. `write_variant` — идемпотентная запись: меняет только отличающееся.

⚠️ `max_score` варианта считается из суммы `points`, а не читается из файла.
⚠️ `chain_first` / `chain_second` заполняются ЗДЕСЬ, а не в `save()`: логика не
должна прятаться в сохранении модели.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_slug
from django.db import transaction

from vp.models import VPItem, VPVariant
from vp.scoring import NUMBER_FORMAT

TOUR1_NUMBERS = list(range(1, 45))
TOUR1_MAX_SCORE = Decimal('100')
GRADE_BANDS = ('9-10', '11')

#: Правила по турам: какие классы бывают и как устроен вариант.
#: `structure` — по классу: {блок: (сколько заданий, баллов за каждое)}.
#: У 1 тура структуры нет: его держат прежние проверки (номера 1..44, сумма 100),
#: и ни одна из них не ослаблена. Формат 2 тура — рекомендации ВШЭ 2026/27.
TOUR_RULES = {
    1: {'grade_bands': GRADE_BANDS, 'max_score': TOUR1_MAX_SCORE, 'structure': None},
    2: {'grade_bands': ('9', '10', '11'), 'max_score': Decimal('100'),
        'structure': {
            '9': {'number': (12, Decimal('6')), 'multi': (3, Decimal('4')),
                  'matching': (1, Decimal('8')), 'gaptext': (1, Decimal('8'))},
            '10': {'number': (14, Decimal('5')), 'multi': (2, Decimal('6')),
                   'matching': (1, Decimal('9')), 'gaptext': (1, Decimal('9'))},
            '11': {'number': (14, Decimal('5')), 'multi': (2, Decimal('6')),
                   'matching': (1, Decimal('9')), 'gaptext': (1, Decimal('9'))},
        }},
}

#: Какой вид ответа у блока 2 тура: блок говорит, что рисовать, вид — как считать.
TOUR2_BLOCK_KINDS = {'number': 'number', 'multi': 'multi',
                     'matching': 'match', 'gaptext': 'match'}

#: Метка пропуска в тексте: `[[3]]`.
GAP_MARK = re.compile(r'\[\[(\d+)\]\]')

BLOCKS = {value for value, _ in VPItem.Block.choices}
KINDS = {value for value, _ in VPItem.Kind.choices}
SOURCE_KINDS = {value for value, _ in VPVariant.SourceKind.choices}

# Поля задания, которые берутся из файла как есть (кроме `n`, `options`,
# `correct`, чисел и `penalty` — им нужна проверка).
_ITEM_TEXT_FIELDS = ('intro', 'statement', 'prefix', 'suffix', 'answer',
                     'figure', 'figure_caption', 'figure_source',
                     'table_html', 'solution')
_ITEM_KNOWN_KEYS = set(_ITEM_TEXT_FIELDS) | {
    'n', 'block', 'kind', 'options', 'correct', 'accepted', 'points',
    'wrong_penalty', 'penalty', 'rows', 'group'}
_VARIANT_TEXT_FIELDS = ('title', 'olympiad_slug', 'grade_band', 'source_kind',
                        'source_note', 'author')


@dataclass
class Parsed:
    """Разобранный файл: поля варианта, поля заданий, ошибки, предупреждения."""
    variant: dict = field(default_factory=dict)
    items: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class WriteResult:
    variant_created: bool = False
    variant_changed: list = field(default_factory=list)
    created: list = field(default_factory=list)      # номера
    updated: dict = field(default_factory=dict)      # номер -> [поля]
    deleted: list = field(default_factory=list)      # номера
    unchanged: int = 0
    saved_items: int = 0                             # заданий в базе после записи
    has_attempts: bool = False

    @property
    def is_noop(self):
        return not (self.variant_created or self.variant_changed
                    or self.created or self.updated or self.deleted)


class StaleItemsError(Exception):
    """В базе есть задания, которых нет в файле, а у варианта уже есть попытки."""


# ---------------------------------------------------------------- цепочка

def chain_letters(word):
    """Первая и вторая буквы слова: нижний регистр, «ё» → «е», не-буквы мимо."""
    letters = [ch for ch in (word or '').lower().replace('ё', 'е')
               if ch.isalpha()]
    first = letters[0] if letters else ''
    second = letters[1] if len(letters) > 1 else ''
    return first, second


def find_chain_breaks(items):
    """Разрывы змейки: строки вида «№22 «отрасль» → №23 «…»: ожидалась буква «т»».

    `items` — словари из `normalize` (нужны `number`, `block`, `answer`,
    `chain_first`, `chain_second`). Пары берутся по соседним номерам блока
    `snake`.
    """
    snake = sorted((i for i in items if i.get('block') == 'snake'),
                   key=lambda i: i['number'])
    breaks = []
    for a, b in zip(snake, snake[1:]):
        head = f"№{a['number']} «{a.get('answer', '')}» → " \
               f"№{b['number']} «{b.get('answer', '')}»"
        if not a.get('chain_second'):
            breaks.append(f'{head}: у ответа №{a["number"]} нет второй буквы')
        elif b.get('chain_first') != a['chain_second']:
            breaks.append(f"{head}: ожидалась буква «{a['chain_second']}»")
    return breaks


# ------------------------------------------------------------ инварианты

def summarize(items):
    """Число заданий, сумма баллов и разбивка по блокам (по порядку файла)."""
    total = Decimal('0')
    blocks = {}
    for item in items:
        points = item.get('points')
        points = points if isinstance(points, Decimal) else Decimal('0')
        total += points
        count, block_sum = blocks.get(item.get('block'), (0, Decimal('0')))
        blocks[item.get('block')] = (count + 1, block_sum + points)
    return {'count': len(items), 'total': total, 'blocks': blocks}


# ----------------------------------------------------------------- разбор

def _decimal(value):
    """Число из YAML → Decimal через строку (без float-шума) или None."""
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite() or result != result.quantize(Decimal('0.01')):
        return None
    return result.quantize(Decimal('0.01'))


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _text(value):
    return '' if value is None else str(value).strip()


def _check_length(model, name, value, where, errors):
    limit = model._meta.get_field(name).max_length
    if limit and len(value) > limit:
        errors.append(f'{where}: поле «{name}» длиннее {limit} знаков ({len(value)})')


def _normalize_item(raw, position, errors, warnings):
    """Одно задание → словарь полей модели (или None, если номера нет)."""
    if not isinstance(raw, dict):
        errors.append(f'задание в позиции {position}: ожидался словарь полей')
        return None
    number = _int(raw.get('n'))
    if number is None or number <= 0:
        errors.append(f'задание в позиции {position}: нет номера `n`')
        return None
    where = f'№{number}'
    for key in raw:
        if key not in _ITEM_KNOWN_KEYS:
            warnings.append(f'{where}: неизвестное поле «{key}» пропущено')

    values = {'number': number}
    for name in _ITEM_TEXT_FIELDS:
        values[name] = _text(raw.get(name))
        _check_length(VPItem, name, values[name], where, errors)
    if not values['statement']:
        errors.append(f'{where}: пустое условие `statement`')

    for name, allowed in (('block', BLOCKS), ('kind', KINDS)):
        values[name] = _text(raw.get(name))
        if values[name] not in allowed:
            errors.append(f'{where}: `{name}` = «{values[name]}», допустимо: '
                          f'{", ".join(sorted(allowed))}')

    points = _decimal(raw.get('points'))
    if points is None:
        errors.append(f'{where}: `points` не число с двумя знаками '
                      f'({raw.get("points")!r})')
    elif points <= 0:
        errors.append(f'{where}: `points` должен быть больше нуля ({points})')
    values['points'] = points

    penalty_value = _decimal(raw.get('wrong_penalty', 0))
    if penalty_value is None or penalty_value < 0:
        errors.append(f'{where}: `wrong_penalty` не число ≥ 0 '
                      f'({raw.get("wrong_penalty")!r})')
        penalty_value = Decimal('0.00')
    values['wrong_penalty'] = penalty_value

    flag = raw.get('penalty', False)
    if not isinstance(flag, bool):
        errors.append(f'{where}: `penalty` должен быть true или false')
        flag = False
    values['penalty'] = flag

    accepted = raw.get('accepted') or []
    if not isinstance(accepted, list):
        errors.append(f'{where}: `accepted` должен быть списком строк')
        accepted = []
    values['accepted'] = [_text(a) for a in accepted]

    rows = raw.get('rows') or []
    if not isinstance(rows, list) or any(isinstance(r, (list, dict)) for r in rows):
        errors.append(f'{where}: `rows` должен быть списком строк')
        rows = []
    values['rows'] = [_text(r) for r in rows]

    group = raw.get('group')
    if group is not None:
        number_ = _int(group)
        if number_ is None or number_ <= 0 or isinstance(group, float):
            errors.append(f'{where}: `group` должен быть целым числом больше нуля ({group!r})')
            number_ = None
        group = number_
    values['group'] = group

    _normalize_choices(raw, values, where, errors)

    if values['kind'] == 'short_text' and not values['answer']:
        errors.append(f'{where}: у короткого ответа пусто поле `answer`')

    # Цепочка змейки считается от слова, которое вводит участник.
    first, second = chain_letters(VPItem(answer=values['answer']).chain_word())
    values['chain_first'], values['chain_second'] = first, second
    return values


def _normalize_choices(raw, values, where, errors):
    """options / correct: нумерация вариантов с единицы, ссылки в пределах."""
    kind = values['kind']
    options = raw.get('options') or []
    correct = raw.get('correct') if raw.get('correct') is not None else []

    if not isinstance(options, list) or any(
            isinstance(o, (list, dict)) for o in options):
        errors.append(f'{where}: `options` должен быть списком строк')
        options = []
    values['options'] = [{'n': n, 'text': _text(o)}
                         for n, o in enumerate(options, start=1)]

    if kind == 'match':
        if not isinstance(correct, dict) or not correct:
            errors.append(f'{where}: у сопоставления пусто `correct` '
                          f'(нужен словарь «ключ: номер»)')
            correct = {}
        values['correct'] = {str(k): v for k, v in correct.items()}
        return

    if kind in ('single', 'multi'):
        if not values['options']:
            errors.append(f'{where}: пусто `options`')
        if not isinstance(correct, list):
            errors.append(f'{where}: `correct` должен быть списком номеров, '
                          f'например [3] ({correct!r})')
            correct = []
        elif not correct:
            errors.append(f'{where}: пусто `correct` (нужен список номеров)')
        numbers = [_int(c) for c in correct]
        if any(n is None for n in numbers):
            errors.append(f'{where}: в `correct` есть не число ({correct!r})')
            numbers = [n for n in numbers if n is not None]
        known = {o['n'] for o in values['options']}
        for n in numbers:
            if n not in known:
                errors.append(f'{where}: `correct` ссылается на номер {n}, '
                              f'которого нет в options (их {len(known)})')
        values['correct'] = numbers
    else:
        values['correct'] = correct if isinstance(correct, (list, dict)) else []


def _normalize_variant(data, errors):
    values = {}
    slug = _text(data.get('slug'))
    try:
        validate_slug(slug)
        if len(slug) > 80:
            raise ValidationError('длиннее 80 знаков')
    except ValidationError:
        errors.append(f'вариант: slug «{slug}» не подходит под шаблон slug '
                      f'(латиница, цифры, «-» и «_», до 80 знаков)')
    values['slug'] = slug
    for name in _VARIANT_TEXT_FIELDS:
        values[name] = _text(data.get(name))
        _check_length(VPVariant, name, values[name], 'вариант', errors)
    values['olympiad_slug'] = values['olympiad_slug'] or 'vysshaya-proba'
    if not values['title']:
        errors.append('вариант: пустое `title`')
    if values['source_kind'] not in SOURCE_KINDS:
        errors.append(f'вариант: `source_kind` = «{values["source_kind"]}», '
                      f'допустимо: {", ".join(sorted(SOURCE_KINDS))}')
    for name, default in (('tour', 1), ('year', None), ('duration_seconds', 1800)):
        number = _int(data.get(name, default))
        if number is None or number <= 0:
            errors.append(f'вариант: `{name}` не положительное целое '
                          f'({data.get(name)!r})')
            number = default or 0
        values[name] = number
    rules = TOUR_RULES.get(values['tour'])
    if rules is None:
        errors.append(f'вариант: `tour` = {values["tour"]}, допустимо: '
                      f'{", ".join(str(t) for t in TOUR_RULES)}')
    elif values['grade_band'] not in rules['grade_bands']:
        errors.append(f'вариант: `grade_band` = «{values["grade_band"]}», '
                      f'допустимо: {", ".join(rules["grade_bands"])}')
    values.update(_normalize_source(data, errors))
    return values


def _normalize_source(data, errors):
    """`source: {label, url}` — необязательный блок; оба поля или ни одного.

    Отсутствие блока — не предупреждение, а нормальное состояние (у
    официальных демовариантов ВШЭ подписи источника нет).
    """
    source = data.get('source') or {}
    if not isinstance(source, dict):
        errors.append('вариант: `source` должен быть словарём {label, url}')
        source = {}
    label = _text(source.get('label'))
    url = _text(source.get('url'))
    _check_length(VPVariant, 'source_label', label, 'вариант', errors)
    _check_length(VPVariant, 'source_url', url, 'вариант', errors)
    if bool(label) != bool(url):
        errors.append('вариант: `source.label` и `source.url` заполняются оба '
                      'или оба пусты')
    elif url and not url.startswith('https://'):
        errors.append(f'вариант: `source.url` должен начинаться с https:// '
                      f'({url!r})')
    return {'source_label': label, 'source_url': url}


def normalize(data):
    """Словарь из YAML → `Parsed` со всеми найденными ошибками (без записи)."""
    parsed = Parsed()
    if not isinstance(data, dict):
        parsed.errors.append('файл должен быть словарём (slug, title, …, items)')
        return parsed
    parsed.variant = _normalize_variant(data, parsed.errors)

    raw_items = data.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        parsed.errors.append('вариант: нет списка `items`')
        return parsed
    for position, raw in enumerate(raw_items, start=1):
        values = _normalize_item(raw, position, parsed.errors, parsed.warnings)
        if values:
            parsed.items.append(values)

    _check_numbering(parsed)
    rules = TOUR_RULES.get(parsed.variant.get('tour'))
    if rules and rules['structure']:
        _check_tour2(parsed, rules)
    max_score = rules['max_score'] if rules else TOUR1_MAX_SCORE
    total = summarize(parsed.items)['total']
    if total != max_score:
        parsed.errors.append(f'сумма `points` по всем заданиям {total}, '
                             f'а должна быть {max_score}')
    return parsed


def _check_numbering(parsed):
    numbers = [i['number'] for i in parsed.items]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        parsed.errors.append(f'номера заданий повторяются: {duplicates}')
    if parsed.variant.get('tour') == 1:
        got = set(numbers)
        missing = [n for n in TOUR1_NUMBERS if n not in got]
        extra = sorted(got - set(TOUR1_NUMBERS))
        if missing or extra or len(numbers) != len(TOUR1_NUMBERS):
            parsed.errors.append(
                'при tour=1 номера заданий не образуют ровно 1..44: '
                f'не хватает {missing}, лишние {extra}')


# ------------------------------------------------------------ 2 тур

def _check_tour2(parsed, rules):
    """Проверки варианта 2 тура: структура класса, номера, число, соотнесение,
    пропуски и пары с общим условием. Всё — ошибки, а не предупреждения."""
    errors = parsed.errors
    items = sorted(parsed.items, key=lambda i: i['number'])
    structure = rules['structure'].get(parsed.variant.get('grade_band'))
    if structure is None:
        return  # класс уже назван ошибкой в шапке варианта

    expected = sum(count for count, _ in structure.values())
    numbers = [i['number'] for i in items]
    if numbers != list(range(1, expected + 1)):
        errors.append(f'при tour=2 номера заданий не образуют ровно 1..{expected} '
                      f'(класс {parsed.variant["grade_band"]}): в файле {numbers}')

    counts = {}
    for item in items:
        where = f'№{item["number"]}'
        block = item['block']
        if block not in structure:
            errors.append(f'{where}: блок «{block}» не бывает во 2 туре '
                          f'(допустимо: {", ".join(structure)})')
            continue
        counts[block] = counts.get(block, 0) + 1
        need_points = structure[block][1]
        if item['points'] is not None and item['points'] != need_points:
            errors.append(f'{where}: в блоке «{block}» задание стоит {need_points} '
                          f'баллов, а в файле {item["points"]}')
        need_kind = TOUR2_BLOCK_KINDS[block]
        if item['kind'] != need_kind:
            errors.append(f'{where}: у блока «{block}» вид ответа `{need_kind}`, '
                          f'а в файле `{item["kind"]}`')
            continue
        if block == 'number':
            _check_number_item(item, where, errors)
        elif block == 'matching':
            _check_matching_item(item, where, errors)
        elif block == 'gaptext':
            _check_gaptext_item(item, where, errors)
    for block, (count, _) in structure.items():
        if counts.get(block, 0) != count:
            errors.append(f'блок «{block}»: заданий {counts.get(block, 0)}, а у '
                          f'{parsed.variant["grade_band"]} класса должно быть {count}')
    _check_groups(items, errors)


def _check_number_item(item, where, errors):
    """Эталон числа сам проходит строгий формат ВШЭ; `accepted` — как есть."""
    if not item['answer']:
        errors.append(f'{where}: у задания с числом пусто поле `answer`')
    elif not NUMBER_FORMAT.fullmatch(item['answer']):
        errors.append(f'{where}: эталон «{item["answer"]}» не в формате ответа ВШЭ '
                      f'(цифры, минус, запятая и до двух знаков после неё: «37,5»)')


def _option_refs(item, where, errors):
    known = {o['n'] for o in item['options']}
    if not known:
        errors.append(f'{where}: пусто `options`')
    for key, value in item['correct'].items():
        if _int(value) not in known:
            errors.append(f'{where}: `correct` «{key}» ссылается на {value!r}, '
                          f'которого нет в options (их {len(known)})')


def _check_matching_item(item, where, errors):
    """Соотнесение: строка на каждый ключ «1»…«N», значения — номера категорий."""
    correct, rows = item['correct'], item['rows']
    if not rows:
        errors.append(f'{where}: у соотнесения пусто `rows` (тексты утверждений)')
    elif len(rows) != len(correct):
        errors.append(f'{where}: строк `rows` {len(rows)}, а ключей `correct` {len(correct)}')
    if correct and sorted(correct) != sorted(str(k) for k in range(1, len(correct) + 1)):
        errors.append(f'{where}: ключи `correct` должны быть «1»…«{len(correct)}», '
                      f'а в файле {sorted(correct)}')
    _option_refs(item, where, errors)


def _check_gaptext_item(item, where, errors):
    """Пропуски: метки `[[k]]` в тексте ровно те же, что ключи `correct`."""
    marks = GAP_MARK.findall(item['statement'])
    if len(marks) != len(set(marks)):
        errors.append(f'{where}: метка пропуска повторяется в тексте')
    marks, keys = set(marks), set(item['correct'])
    if marks != keys:
        def listed(labels):
            return '[' + ', '.join(sorted(labels, key=lambda k: (len(k), k))) + ']'
        errors.append(f'{where}: метки пропусков в тексте {listed(marks)} '
                      f'не совпадают с ключами `correct` {listed(keys)}'
                      + (f'; без ключа: {listed(marks - keys)}' if marks - keys else '')
                      + (f'; без метки: {listed(keys - marks)}' if keys - marks else ''))
    _option_refs(item, where, errors)


def _check_groups(items, errors):
    """Пара с общим условием: в группе минимум два задания, и они идут подряд."""
    groups = {}
    for item in items:
        if item.get('group') is not None:
            groups.setdefault(item['group'], []).append(item['number'])
    for group, numbers in sorted(groups.items()):
        if len(numbers) < 2:
            errors.append(f'группа {group}: в ней одно задание ({numbers[0]}), '
                          f'а общее условие бывает минимум у двух')
        elif numbers != list(range(numbers[0], numbers[0] + len(numbers))):
            errors.append(f'группа {group}: задания {numbers} идут не подряд')


# ----------------------------------------------------------------- запись

def _changed_fields(obj, values):
    """Имена полей, значения которых в базе отличаются от `values`."""
    return [name for name, value in values.items()
            if getattr(obj, name) != value]


def write_variant(parsed, publish=False, dry_run=False):
    """Идемпотентная запись. `dry_run` выполняет всё и откатывает транзакцию,
    поэтому числа сухого прогона — те же, что у настоящей записи.

    Вариант ищется по `slug`, задание — по паре (вариант, номер). Задания,
    которых в файле больше нет, удаляются; но если у варианта есть попытки —
    `StaleItemsError` и ничего не пишется.
    """
    result = WriteResult()
    variant_values = dict(parsed.variant)
    variant_values['max_score'] = summarize(parsed.items)['total']
    file_numbers = {i['number'] for i in parsed.items}

    with transaction.atomic():
        variant = VPVariant.objects.filter(slug=variant_values['slug']).first()
        result.variant_created = variant is None
        if variant is None:
            variant = VPVariant(**variant_values,
                                is_published=bool(publish))
            variant.save()
            existing = {}
        else:
            result.has_attempts = variant.attempts.exists()
            existing = {i.number: i for i in variant.items.all()}
            stale = sorted(set(existing) - file_numbers)
            if stale and result.has_attempts:
                raise StaleItemsError(
                    f'в базе есть задания {stale}, которых нет в файле, а у '
                    f'варианта уже есть попытки ({variant.attempts.count()}); '
                    f'удалить их нельзя — сданные ответы потеряли бы задания. '
                    f'Верните эти номера в файл или заведите новый вариант.')
            changed = _changed_fields(variant, variant_values)
            if publish and not variant.is_published:
                variant.is_published = True
                changed.append('is_published')
            if changed:
                for name in changed:
                    if name != 'is_published':
                        setattr(variant, name, variant_values[name])
                variant.save(update_fields=changed)
                result.variant_changed = changed

        new_items = []
        for values in parsed.items:
            item = existing.get(values['number'])
            if item is None:
                new_items.append(VPItem(variant=variant, **values))
                result.created.append(values['number'])
                continue
            changed = _changed_fields(item, values)
            if changed:
                for name in changed:
                    setattr(item, name, values[name])
                item.save(update_fields=changed)
                result.updated[values['number']] = changed
            else:
                result.unchanged += 1
        VPItem.objects.bulk_create(new_items)

        stale = sorted(set(existing) - file_numbers)
        if stale:
            variant.items.filter(number__in=stale).delete()
            result.deleted = stale

        result.saved_items = variant.items.count()
        if dry_run:
            transaction.set_rollback(True)
    return result

