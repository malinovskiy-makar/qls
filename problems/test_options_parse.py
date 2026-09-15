# -*- coding: utf-8 -*-
"""Варианты теста, записанные текстом в хвосте условия, — чистый разбор без базы.

⚠️ ЗАЧЕМ (решение владельца 15.09.2026). У тестов переноса варианты вписаны в
конец условия текстом («Варианты ответа: 1. (a) …»), подпунктов нет — виджет
теста их не видит (`reports/corpus_transfer_20260913/TEST_WIDGET_RECON.md`).
Варианты переносятся в `ProblemPart`, блок вырезается из условия; пишет
команда `test_options_from_statement`, здесь только разбор.

⚠️ ЛОЖНОЕ СРАБАТЫВАНИЕ ХУЖЕ ПРОПУСКА. Нумерованные подвопросы («1. Найдите
равновесие. 2. Постройте график») — это задача, а не тест: вырезать их значит
испортить условие. Поэтому блок берётся только с хвоста, одним стилем, по
порядку без пропусков; строки с глаголом-заданием в нумерованном стиле
отклоняют разбор целиком; верные варианты обязаны сойтись с ответом задачи.
Звать — только для тестов `single`/`multi` без подпунктов.
"""
import re
from dataclasses import dataclass, field

from problems.answer_check import label_set, normalize_label

HEADER_RE = re.compile(r'^\s*варианты(\s+ответ(а|ов))?\s*[:.]?\s*$', re.IGNORECASE)

# Порядок важен: «1. (a) …» проверяется раньше «1. …», иначе буква ушла бы в текст.
STYLES = (
    ('numbered_lettered', re.compile(
        r'^\s*(\d{1,2})[.)]\s*\(?([a-zа-яё])\)?[.)]?\s+(.+)$', re.IGNORECASE)),
    ('lettered', re.compile(r'^\s*([а-яёa-z])[.)]\s+(.+)$', re.IGNORECASE)),
    ('numbered', re.compile(r'^\s*(\d{1,2})[.)]\s+(.+)$')),
)
STYLE_RE = dict(STYLES)

# Буквы вариантов по порядку: «ё» и «й» в списках вариантов не встречаются.
ALPHABETS = ('абвгдежзиклмнопрс', 'abcdefghijklmnopq')

TASK_VERBS = ('найдите', 'постройте', 'определите', 'рассчитайте',
              'докажите', 'объясните')

# Подпункты «верно/неверно» — ровно как у живых виджетов банка (задачи 5038,
# 5475): метка «а» — «Верно», «б» — «Неверно».
BOOLEAN_PARTS = (('а', 'Верно'), ('б', 'Неверно'))
TRUE_WORDS = ('верно', 'да')
FALSE_WORDS = ('неверно', 'нет')

_INLINE_OPTION_RE = re.compile(r'(\d)[.)]\s*(.+?)(?=\s+\d[.)]|$)')
_UNESCAPED_DOLLAR_RE = re.compile(r'(?<!\\)\$')
# Номер строки, повторённый в начале варианта: «1. (1) …», «1. 1) …», «1. 1. …».
# Пробел после «N.» обязателен, иначе «1.5 млн» потеряло бы число.
_REPEATED_NUMBER_RE = re.compile(r'^\s*(?:\((\d{1,2})\)\s*|(\d{1,2})[.)]\s+)')


@dataclass(frozen=True)
class ParsedOptions:
    stem: str
    options: tuple            # ((метка, текст), …) в порядке условия
    header: bool
    style: str
    aliases: dict = field(default_factory=dict)   # номер → буква у «1. (a)»


def parse_options(statement):
    """Варианты с хвоста условия или None (причина — `parse_with_reason`)."""
    return parse_with_reason(statement)[0]


def parse_with_reason(statement):
    """(ParsedOptions, 'parsed') или (None, причина отказа)."""
    lines = (statement or '').split('\n')
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    start = end
    while start and (not lines[start - 1].strip()
                     or any(rx.match(lines[start - 1]) for _name, rx in STYLES)):
        start -= 1
    block = [line for line in lines[start:end] if line.strip()]
    if len(block) < 2:
        return None, 'no_block'
    cut, header = start, False
    if start and HEADER_RE.match(lines[start - 1]):
        cut, header = start - 1, True

    for style, _rx in STYLES:
        read = _read_block(block, style)
        if read:
            break
    else:
        return None, 'mixed_style'
    rows, aliases = read
    options = tuple((label, _clean(text)) for label, text in rows)
    if any(not text for _label, text in options):
        return None, 'mixed_style'
    if len({normalize_label(label) for label, _text in options}) != len(options):
        return None, 'mixed_style'
    if style == 'numbered' and any(text.lower().startswith(TASK_VERBS)
                                   for _label, text in options):
        return None, 'verb_like_subquestion'
    stem = '\n'.join(lines[:cut]).rstrip()
    if not stem.strip():
        return None, 'empty_stem'
    return ParsedOptions(stem, options, header, style, aliases), 'parsed'


def _label_and_text(groups, style):
    if style == 'numbered':
        label = str(int(groups[0]))
        # ⚠️ Решение владельца 15.09: номер, повторённый в начале варианта
        # («1. (1) …»), — нумерация, а не текст. Другой номер («1. (2) …») остаётся.
        repeated = _REPEATED_NUMBER_RE.match(groups[1])
        if repeated and str(int(repeated.group(1) or repeated.group(2))) == label:
            return label, groups[1][repeated.end():]
        return label, groups[1]
    if style == 'lettered':
        return groups[0].lower(), groups[1]
    return groups[1].lower(), groups[2]


def _read_block(lines, style):
    """([(метка, текст)], псевдонимы) для строк одного стиля по порядку, или None."""
    matches = [STYLE_RE[style].match(line) for line in lines]
    if not all(matches):
        return None
    groups = [m.groups() for m in matches]
    count = len(groups)
    if style != 'lettered' and [int(g[0]) for g in groups] != list(range(1, count + 1)):
        return None
    if style != 'numbered':
        letters = ''.join(g[0 if style == 'lettered' else 1].lower() for g in groups)
        if not any(letters == alphabet[:count] for alphabet in ALPHABETS):
            return None
    aliases = ({str(int(g[0])): g[1].lower() for g in groups}
               if style == 'numbered_lettered' else {})
    return [_label_and_text(g, style) for g in groups], aliases


def _clean(text):
    """Текст варианта: пробелы схлопнуты, завершающие «;» и «.» срезаны."""
    return re.sub(r'\s+', ' ', text).strip().rstrip(';.').strip()


def _norm(text):
    """Для сверки с ответом: без «\\», регистра, лишних пробелов и хвостовых «;.»."""
    return _clean((text or '').replace('\\', '')).lower()


def correct_labels(answer, parsed):
    """Верные метки по `Problem.answer` или пустое множество.

    Ответ в банке записан тремя способами: строкой варианта целиком
    («2. (b) Центральный банк…;»), текстом варианта («дохода») и метками
    («2», «124», «b»). Читаются оба пути; если они дают разное — ответ
    неоднозначен (например «2», когда «2» — ещё и текст другого варианта), и
    вернётся пустое множество: лучше пропустить задачу, чем отметить не то.
    """
    labels = [label for label, _text in parsed.options]
    texts = {label: _norm(text) for label, text in parsed.options}
    by_lines = []
    for piece in (p.strip() for p in (answer or '').split('\n')):
        if not piece:
            continue
        m = STYLE_RE[parsed.style].match(piece)
        if m:
            label, text = _label_and_text(m.groups(), parsed.style)
            if texts.get(label) == _norm(text):
                by_lines.append(label)
                continue
        hits = [label for label, text in texts.items() if text == _norm(piece)]
        by_lines.append(hits[0] if len(hits) == 1 else None)
    lines_set = set(by_lines) if by_lines and None not in by_lines else set()
    marks = {parsed.aliases.get(mark, mark)
             for mark in label_set(answer, labels + list(parsed.aliases))}
    marks_set = marks if marks and marks <= set(labels) else set()
    if lines_set and marks_set and lines_set != marks_set:
        return set()
    return lines_set or marks_set


def boolean_correct_label(answer, statement):
    """Метка верной плитки из `BOOLEAN_PARTS` («а» — Верно, «б» — Неверно) или None.

    Ответ бывает словом («Неверно»), строкой варианта («2. нет») или номером
    («1»): тогда слово ищется в вариантах условия — столбиком или одной
    строкой «1) Верно  2) Неверно».
    """
    raw = (answer or '').strip()
    word = _norm(raw)
    numbered = STYLE_RE['numbered'].match(raw)
    if numbered:
        word = _norm(numbered.group(2))
    elif word.isdigit():
        parsed = parse_options(statement)
        options = dict(parsed.options) if parsed else {}
        if not options:
            lines = [line for line in (statement or '').split('\n') if line.strip()]
            options = dict(_INLINE_OPTION_RE.findall(lines[-1])) if lines else {}
        word = _norm(options.get(word, ''))
    if word in TRUE_WORDS:
        return BOOLEAN_PARTS[0][0]
    if word in FALSE_WORDS:
        return BOOLEAN_PARTS[1][0]
    return None


# Вариант «Верно»/«Неверно» в хвосте условия: «1) Верно», «а. неверно;»,
# «(1) Верно», «1. 1) Верно» (номер повторён) или слово без номера.
_BOOLEAN_TOKEN_RE = re.compile(
    r'\s*(?:(\d|[а-яa-z])[.)]\s*(?:\(?\1\)|\1[.)])?\s*|\((\d|[а-яa-z])\)\s*)?'
    r'((?:не)?верно)[.;,]?\s*', re.IGNORECASE)
_BOOLEAN_TAIL_LABELS = (['', ''], ['1', '2'], ['а', 'б'], ['a', 'b'])


def _boolean_tokens(line):
    """[(метка, слово)], если строка целиком из вариантов «Верно»/«Неверно», иначе None."""
    tokens, pos = [], 0
    while pos < len(line):
        m = _BOOLEAN_TOKEN_RE.match(line, pos)
        if not m:
            return None
        tokens.append(((m.group(1) or m.group(2) or '').lower(), m.group(3).lower()))
        pos = m.end()
    return tokens or None


def cut_boolean_tail(statement):
    """(условие без хвоста «Верно/Неверно», 'boolean_tail') или (None, причина).

    ⚠️ ЗАЧЕМ (решение владельца 15.09.2026). У «верно/неверно» плитки «Верно» и
    «Неверно» — подпункты, а в хвосте условия та же пара осталась строкой
    («1) Верно  2) Неверно»): ученик видит варианты дважды. Режется только
    хвост ЦЕЛИКОМ из двух вариантов — по одному «верно» и «неверно», с номерами
    1, 2 / а, б / a, b или без них, в одну строку или в две, с шапкой
    «Варианты ответа» над ними. «Верно ли, что…», «Неверно, что…» и строка с
    любым другим текстом остаются: ложный вырез хуже пропуска.
    """
    lines = (statement or '').split('\n')
    cut, tokens = len(lines), []
    while cut and len(tokens) < 2:
        found = _boolean_tokens(lines[cut - 1]) if lines[cut - 1].strip() else []
        if found is None:
            break
        tokens = found + tokens
        cut -= 1
    if (sorted(word for _label, word in tokens) != ['верно', 'неверно']
            or [label for label, _word in tokens] not in _BOOLEAN_TAIL_LABELS):
        return None, 'no_tail'
    top = cut
    while top and not lines[top - 1].strip():
        top -= 1
    if top and HEADER_RE.match(lines[top - 1]):
        cut = top - 1
    stem = '\n'.join(lines[:cut]).rstrip()
    if not stem.strip():
        return None, 'empty_stem'
    return stem, 'boolean_tail'


def formula_worse(before, after):
    """Стало ли с формулами хуже: нечётное число `$` или сильнее разбаланс `{}`.

    Считается ДИФФЕРЕНЦИАЛЬНО: в банке есть унаследованные поломки, и важно
    не «красиво ли», а «не испортили ли». Экранированный `\\$` — не формула.
    """
    def dollars(text):
        return len(_UNESCAPED_DOLLAR_RE.findall(text or '')) % 2

    def braces(text):
        return abs((text or '').count('{') - (text or '').count('}'))

    return dollars(after) > dollars(before) or braces(after) > braces(before)
