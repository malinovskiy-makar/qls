# -*- coding: utf-8 -*-
"""
Свип new_sentence Батча 2: классификация «новых строк» по ПРОИСХОЖДЕНИЮ
(решение в Notion «Решения» от 2026-07-21, карточка 3a4b11c92bc181a1bfb9e25be1fa5b8d).

Категория new_sentence прошлого свипа (`batch2_full_sweep`, 361 поле в
292 задачах) сознательно не откатывалась: числовая подпись поля совпала,
но появились фрагменты, которых не было в ДО ЭТОГО ЖЕ поля. Ревью Макара
показало, что часть таких фрагментов — не выдумка Sonnet, а ПЕРЕНОС
содержимого из других полей той же задачи (соседних подпунктов, их
ответов, куска условия): превью показывало ДО только того же поля, и
перенос был неотличим от выдумки.

⚠️ КРИТЕРИЙ ПО СЛОВАМ ОТМЕНЁН (решение 2026-07-28, карточка
3abb11c92bc1814ba792d754a6095108). Ревью секции C показало: словесный порог
(«≥80% содержательных слов нового фрагмента должны найтись в ДО») заворачивал
в откат не выдумки, а ПОЧИНКУ — исправленная опечатка по определению даёт
слово, которого в оригинале нет («Составте»→«составьте», «качественый»→
«качественный», «курсы к заклу»→«к экзамену»). Исходные тексты полны
опечаток и PDF-мусора, поэтому большинство «новых слов» Sonnet — ремонт.

Действующий критерий:

  - REVERT ⟺ в новом фрагменте есть ЧИСЛОВОЙ ИЛИ ЗНАКОВЫЙ токен, которого
    нет в «фонде происхождения» задачи (нормализованные множества токенов
    ВСЕГО ДО задачи из бэкапа: statement + текст и answer всех подпунктов
    + Problem.answer + Problem.solution). Выдумать содержание, не тронув
    ни одного числа и ни одного знака, практически нельзя — а вот
    починить текст можно.
  - Блок \\begin{array} / tikzpicture откатывается по тому же правилу:
    только если внутри есть числа без происхождения (дорисованный с нуля
    чертёж — #4541 — именно так и ловится: координат его линий в ДО нет).
  - Фрагмент без слов и без чисел выдуманного содержания нести не может —
    всегда KEEP.
  - Слова по-прежнему считаются и печатаются, но ТОЛЬКО как пометка на
    человеческий взгляд (`new_words`, файл kept_with_new_words.txt).
    Основанием для отката они не являются НИКОГДА.

  - TABLE_KEEP — поле оставлено и несёт новый блок array/tikzpicture
    (голый блок оборачивается в $$...$$: Sonnet маркеры не ставил —
    проверено на #4407/#33489/#43769, в его cleaned_statement ноль
    вхождений «$$»; наши чистильщики $$ не снимают).
  - MOVED_KEEP — поле оставлено, новых блоков нет.

Поверх классификации действует ШЛЮЗ «НЕ НАВРЕДИ» (batch2_ns_gate.py):
откат отменяется, если после него рендер боевой страницы становится хуже.
Шлюз сильнее классификации — тем же решением отменено допущение «откат к
авторскому тексту безопасен по построению».

Сравнение слов — без учёта регистра (и ё=е); числа — точно, но десятичная
запятая и точка считаются одной записью («1047,62» = «1047.62»), LaTeX-
скобка разделителя «0{,}5» нормализуется как в canon_for_sweep. Знаковые
токены канонизируются (отрицательн\\w* → NEG), иначе смена падежа читалась
бы как смена знака.
"""
from typing import Dict, List, Set, Tuple
import re

from problems.batch2_unblock import (
    _looks_like_sentence, apply_glue, canon_for_sweep, sweep_field)

import difflib

# Порог покрытия слов ОТМЕНЁН решением 2026-07-28. Константа оставлена
# только для отчётности («что сделал бы отменённый критерий») — в вердикт
# она не входит.
LEGACY_WORD_COVERAGE = 0.80

# Блоки, собранные/дорисованные Sonnet: таблица и чертёж. Лимит длины — как
# у маски математики glue_pdf_lines (4000), вложенных блоков в этих данных
# нет. tikzpicture обычно завёрнут в \begin{center} — центрирование само по
# себе блоком не считается, важна начинка.
ARRAY_RE = re.compile(r'\\begin\{array\}[\s\S]{0,4000}?\\end\{array\}')
TIKZ_RE = re.compile(r'\\begin\{tikzpicture\}[\s\S]{0,6000}?\\end\{tikzpicture\}')

# Математика, СПОСОБНАЯ обернуть array: $$...$$, $...$, \(...\), \[...\].
# Это _MATH_RE из glue_pdf_lines БЕЗ альтернативы \begin...\end — иначе
# каждый голый array сам маскировался бы, и «уже обёрнут» было бы не
# отличить от «голый».
_WRAPPING_MATH_RE = re.compile(
    r'(?<!\\)\$\$[\s\S]{0,3000}?\$\$'
    r'|(?<!\\)\$(?:\\.|[^$\\\n]){0,400}?\$'
    r'|\\\([\s\S]{0,800}?\\\)'
    r'|\\\[[\s\S]{0,3000}?\\\]'
)

_BRACED_SEP_RE = re.compile(r'(\d)\{([,.:])\}(?=\d)')

# Пара координат «(0,0)» — ДВА числа, а не десятичное «0.0»: запятая здесь
# разделитель. Правило узкое намеренно — срабатывает, только когда в скобках
# нет ничего, кроме двух целых («(1,5 млн)» не трогается и остаётся
# десятичным). Без него чертёж с координатами, честно взятыми из условия,
# уходил бы в откат из-за несуществующих чисел вида «0.40».
_COORD_PAIR_RE = re.compile(r'\((\d+),(\d+)\)')
_TEXT_CMD_RE = re.compile(r'\\text(?:bf|it|rm|sf|tt)?\{([^{}]*)\}')
# Бэкслеш опционален: фрагмент из диффа может начинаться посреди команды
# («begin{center}» без «\» — реальный случай #4541), а слов «begin{...}» в
# живом тексте задач не бывает.
_BEGIN_END_RE = re.compile(r'\\?(?:begin|end)\{[A-Za-z*]+\}(?:\{[^{}]*\})?')
_ESCAPED_CHAR_RE = re.compile(r'\\([%&_#$])')
_CONTROL_SEQ_RE = re.compile(r'\\[a-zA-Z]+')

_NUM_RE = re.compile(r'\d[\d.,]*')
_WORD_RE = re.compile(r'[A-Za-zА-Яа-яЁё]{3,}')

# Знаковые токены — второй (после чисел) вид содержания, выдумать которое
# нельзя «починкой». Набор тот же, что у детектора подмен sweep_field
# (_NUM_TOKEN_RE в batch2_unblock): смена знака меняет смысл задачи.
_SIGN_TOKEN_RE = re.compile(
    r'\\pm|\\geq|\\leq|\\ge|\\le'
    r'|[±≤≥⩽⩾<>]'
    r'|\bnegative\b|\bpositive\b|\bminus\b|\bplus\b'
    r'|отрицательн\w*|положительн\w*',
    re.IGNORECASE)

_SIGN_CANON = {
    '\\pm': 'PM', '±': 'PM',
    '\\geq': 'GE', '\\ge': 'GE', '≥': 'GE', '⩾': 'GE',
    '\\leq': 'LE', '\\le': 'LE', '≤': 'LE', '⩽': 'LE',
    '<': 'LT', '>': 'GT',
    'negative': 'NEG', 'positive': 'POS', 'minus': 'MINUS', 'plus': 'PLUS',
}

# Чисто-LaTeXная обвязка, уцелевшая после нормализации из-за обрезанных
# диффом команд («aligned}» без «\begin{», реальные случаи #49651 и др.).
# Содержания задачи эти слова не несут — на происхождение не проверяются.
# ВАЖНО: слов tikz-рисования (draw, node, line…) здесь НЕТ намеренно —
# дорисованный Sonnet tikzpicture (#4541) обязан проваливать проверку.
LATEX_SCAFFOLD_WORDS = frozenset(
    'begin end aligned cases array tabular equation center gather gathered '
    'split matrix pmatrix bmatrix vmatrix smallmatrix hline cline text textbf '
    'textit mathrm mathbf mathit operatorname'.split())


def origin_normalize(text):
    # type: (str) -> str
    """Нормализация текста для проверки происхождения — одна и та же для
    фонда задачи и для новых фрагментов, поэтому LaTeX-обвязка (\\text{...},
    \\hline, &, $, \\\\) сокращается с обеих сторон и на вердикт не влияет."""
    t = canon_for_sweep(text or '')
    prev = None
    while prev != t:
        prev = t
        t = _TEXT_CMD_RE.sub(r' \1 ', t)
        t = _BRACED_SEP_RE.sub(r'\1\2', t)
    t = _COORD_PAIR_RE.sub(r'(\1 \2)', t)
    t = _BEGIN_END_RE.sub(' ', t)
    t = t.replace('\\\\', ' ').replace('\\hline', ' ')
    t = _ESCAPED_CHAR_RE.sub(r'\1', t)
    t = _CONTROL_SEQ_RE.sub(' ', t)
    t = t.replace('$', ' ').replace('&', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def origin_nums(normalized):
    # type: (str) -> List[str]
    """Числовые токены в канонической записи: хвостовая пунктуация
    отрезана, десятичная запятая приведена к точке («1047,62» = «1047.62»)."""
    out = []
    for m in _NUM_RE.finditer(normalized):
        tok = m.group(0).rstrip('.,').replace(',', '.')
        if tok:
            out.append(tok)
    return out


def origin_words(normalized):
    # type: (str) -> List[str]
    """Содержательные слова: кириллица/латиница от 3 букв, без регистра, ё=е."""
    return [w.lower().replace('ё', 'е') for w in _WORD_RE.findall(normalized)]


def origin_signs(text):
    # type: (str) -> List[str]
    """Знаковые токены в канонической форме. Берутся из canon_for_sweep, а
    НЕ из origin_normalize: та вычищает управляющие последовательности, и
    «\\geq» исчезло бы вместе с обвязкой. Канонизация («отрицательным» и
    «отрицательный» → NEG) нужна, чтобы смена падежа не читалась как смена
    знака — а вот negative→positive обязана читаться."""
    out = []
    for m in _SIGN_TOKEN_RE.finditer(canon_for_sweep(text or '')):
        tok = m.group(0).lower()
        if tok in _SIGN_CANON:
            out.append(_SIGN_CANON[tok])
        elif tok.startswith('отрицательн'):
            out.append('NEG')
        elif tok.startswith('положительн'):
            out.append('POS')
        else:
            out.append(tok.upper())
    return out


def build_fund(texts):
    # type: (List[str]) -> Dict[str, Set[str]]
    """Фонд происхождения задачи: множества числовых, знаковых и словесных
    токенов ВСЕГО ДО задачи (statement + подпункты с ответами + answer +
    solution). Слова в фонде нужны только для пометок — вердикт по ним
    больше не выносится (решение 2026-07-28)."""
    nums, signs, words = set(), set(), set()
    for t in texts:
        norm = origin_normalize(t)
        nums.update(origin_nums(norm))
        signs.update(origin_signs(t))
        words.update(origin_words(norm))
    return {'nums': nums, 'signs': signs, 'words': words}


def _check_fragment(fragment, fund):
    # type: (str, Dict[str, Set[str]]) -> Dict
    """Проверка одного фрагмента против фонда.

    ok ⟺ нет чисел и знаков без происхождения. Слова считаются и
    возвращаются, но на ok НЕ влияют (критерий по словам отменён
    решением 2026-07-28)."""
    norm = origin_normalize(fragment)
    nums = origin_nums(norm)
    signs = origin_signs(fragment)
    words = sorted(set(origin_words(norm)) - LATEX_SCAFFOLD_WORDS)
    missing_nums = sorted({n for n in nums if n not in fund['nums']})
    missing_signs = sorted({s for s in signs if s not in fund['signs']})
    missing_words = [w for w in words if w not in fund['words']]
    coverage = (1.0 - len(missing_words) / len(words)) if words else None
    return {'ok': not missing_nums and not missing_signs,
            'missing_nums': missing_nums, 'missing_signs': missing_signs,
            'missing_words': missing_words, 'coverage': coverage,
            'empty': not words and not nums and not signs}


def new_blocks_of(old_c, cur_c):
    # type: (str, str) -> List[str]
    """Блоки array/tikzpicture, которых в ДО поля не было."""
    found = ARRAY_RE.findall(cur_c) + TIKZ_RE.findall(cur_c)
    return [b for b in found if b not in old_c]


def inserted_chunks(old_c, masked_cur):
    # type: (str, str) -> List[str]
    """Все вставленные/заменённые куски посимвольного диффа с расширением
    границ до целого слова или числа.

    ⚠️ Фильтра «похоже на предложение» здесь НЕТ намеренно: он выбрасывал
    куски вроде «(60,0) -- (0,40)» (меньше пяти букв), а именно в них живут
    координаты дорисованного чертежа — проверка чисел обязана их видеть
    (#4541). Фильтр применяется отдельно и только для ОТЧЁТНОСТИ.
    """
    sm = difflib.SequenceMatcher(None, old_c, masked_cur, autojunk=False)
    n = len(masked_cur)
    chunks = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag not in ('insert', 'replace'):
            continue
        # Посимвольный дифф режет слова и числа посередине («дходящие»,
        # «спис», «047,62» — реальные обрубки на этих данных): огрызок не
        # найдётся в фонде, и поле утонуло бы в REVERT незаслуженно.
        while j1 > 0 and (masked_cur[j1 - 1].isalnum()
                          or masked_cur[j1 - 1] in '\\.,'):
            j1 -= 1
        while j2 < n and (masked_cur[j2].isalnum()
                          or (masked_cur[j2] in '.,' and j2 + 1 < n
                              and masked_cur[j2 + 1].isalnum())):
            j2 += 1
        chunk = masked_cur[j1:j2]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def classify_field(old_text, current_text, fund):
    # type: (str, str, Dict[str, Set[str]]) -> Dict
    """Классификация одного поля new_sentence по происхождению.

    ЕДИНСТВЕННОЕ основание для REVERT — числовой или знаковый токен без
    происхождения (решение 2026-07-28). Слова считаются и возвращаются в
    `new_words`, но вердикта не выносят; `legacy_word_revert` показывает,
    что сделал бы отменённый словесный критерий (для отчёта «было → стало»).

    Вердикт выносится полю целиком: один фрагмент без происхождения топит
    всё поле, потому что и откат делается полем целиком.
    """
    old_c = canon_for_sweep(old_text)
    cur_c = canon_for_sweep(current_text)

    new_blocks = new_blocks_of(old_c, cur_c)
    masked_cur = cur_c
    for b in new_blocks:
        masked_cur = masked_cur.replace(b, ' ', 1)

    chunks = inserted_chunks(old_c, masked_cur)
    sentence_like = [c for c in chunks if _looks_like_sentence(c)]

    reasons = []
    checks = []
    all_ok = True
    new_words = []
    legacy_word_revert = False

    for kind, frag in ([('block', b) for b in new_blocks]
                       + [('moved', c) for c in chunks]):
        res = _check_fragment(frag, fund)
        checks.append({'kind': kind, 'fragment': frag[:400], **res})
        for w in res['missing_words']:
            if w not in new_words:
                new_words.append(w)
        if not res['ok']:
            all_ok = False
            if res['missing_nums']:
                reasons.append('{}: new_number_without_origin {}'.format(
                    kind, res['missing_nums'][:10]))
            if res['missing_signs']:
                reasons.append('{}: new_sign_without_origin {}'.format(
                    kind, res['missing_signs'][:10]))
        elif res['empty']:
            reasons.append('boundary: fragment_without_words_and_nums (KEEP — '
                           'выдуманного содержания нести не может)')
        # Что сделал бы ОТМЕНЁННЫЙ словесный критерий — только для отчёта.
        if res['missing_words']:
            if kind == 'block':
                legacy_word_revert = True
            elif (_looks_like_sentence(frag) and res['coverage'] is not None
                    and res['coverage'] < LEGACY_WORD_COVERAGE):
                legacy_word_revert = True

    if new_words:
        reasons.append('note: новые слова без происхождения (НЕ основание '
                       'для отката, только на глаза): {}'.format(new_words[:12]))

    if '|' in origin_normalize(' '.join(sentence_like)):
        reasons.append('boundary: pipe_table_fragment (markdown-таблица '
                       'палочками, KaTeX её не рендерит — смотреть глазами)')

    if not new_blocks and not chunks:
        reasons.append('boundary: no_new_fragments_on_recheck')

    if not all_ok:
        verdict = 'REVERT'
    elif new_blocks:
        verdict = 'TABLE_KEEP'
        if sentence_like:
            reasons.append('boundary: table_plus_moved_text_in_one_field')
    else:
        verdict = 'MOVED_KEEP'

    return {'verdict': verdict, 'reasons': reasons,
            'new_blocks': len(new_blocks),
            'moved_fragments': len(sentence_like),
            'new_words': new_words,
            'legacy_word_revert': legacy_word_revert,
            'checks': checks}


def wrap_bare_arrays(text):
    # type: (str) -> Tuple[str, int]
    """Оборачивает каждый голый \\begin{array}...\\end{array} (не лежащий
    уже внутри $...$/$$...$$/\\(...\\)/\\[...\\]) в $$...$$. Повторный
    вызов на результате даёт 0 обёрток (обёрнутый блок попадает в зону
    $$...$$ и пропускается).

    Внутри оборачиваемого блока валютный «\\$» заменяется на
    «\\text{\\textdollar}»: боевые страницы каталога маскируют «\\$»
    часовым U+E000 ДО KaTeX (maskEscapedDollars в catalog/base.html —
    защита текста от псевдоформул), и внутри $$...$$ этот часовой роняет
    парсер («Unexpected character», реальные случаи #31119/#41269/#49156).
    Сам по себе \\textdollar в math-режиме KaTeX 0.16.9 НЕ поддержан
    (Undefined control sequence — проверено в консоли), поэтому
    обязательно в обёртке \\text{...}. Кроме вставки $$ и этой замены
    блок не меняется."""
    if not text or '\\begin{array}' not in text:
        return text, 0
    covered = [(m.start(), m.end()) for m in _WRAPPING_MATH_RE.finditer(text)]
    out = []
    last = 0
    wrapped = 0
    for m in ARRAY_RE.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue
        out.append(text[last:m.start()])
        out.append('$$' + m.group(0).replace('\\$', '\\text{\\textdollar}') + '$$')
        last = m.end()
        wrapped += 1
    out.append(text[last:])
    return ''.join(out), wrapped


def wrap_invariant_holds(current, wrapped):
    # type: (str, str) -> bool
    """Обёртка не имеет права менять ничего, кроме вставленных $$ и замены
    валютного \\$ на \\text{\\textdollar} внутри блока."""
    return (wrapped.replace('$$', '').replace('\\text{\\textdollar}', '\\$')
            == current.replace('$$', ''))


def display_dollar_pairs_balanced(text):
    # type: (str) -> bool
    """Чётное ли число неэкранированных «$$» в поле (контроль после обёртки)."""
    return len(re.findall(r'(?<!\\)\$\$', text or '')) % 2 == 0
