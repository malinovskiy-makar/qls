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

Критерий — происхождение. Новый фрагмент остаётся, только если его
содержимое есть в «фонде происхождения» задачи: нормализованное множество
числовых токенов и содержательных слов ВСЕГО ДО задачи из бэкапа
(statement + текст и answer всех подпунктов + Problem.answer +
Problem.solution). Правила:

  - TABLE_KEEP: новый фрагмент — блок \\begin{array}...\\end{array}, ВСЕ его
    числовые токены есть в фонде И ВСЕ содержательные слова (кириллица/
    латиница от 3 букв) тоже. Такой блок оставляем и оборачиваем в $$...$$
    (Sonnet сам маркеры не ставил — проверено на #4407/#33489/#43769, в его
    cleaned_statement ноль вхождений «$$»; наши чистильщики $$ не снимают).
  - MOVED_KEEP (не-таблица): все числовые токены новых фрагментов есть в
    фонде И ≥80% содержательных слов тоже. Короткие ярлыки («AD:», «ЧП»)
    и разделители («/», «|») словами не считаются — порог длины 3 буквы.
  - Всё остальное — REVERT: откат к ДО с переприменением механической
    чистки (revert_with_recleaning — тот же трёхуровневый fallback, что
    в откате digit_sign_change, вынесен сюда из batch2_full_sweep, чтобы
    оба отката не разошлись логикой).

Сравнение слов — без учёта регистра (и ё=е); числа — точно, но десятичная
запятая и точка считаются одной записью («1047,62» = «1047.62»), LaTeX-
скобка разделителя «0{,}5» нормализуется как в canon_for_sweep.
"""
from typing import Dict, List, Set, Tuple
import re

from problems.batch2_unblock import (
    _looks_like_sentence, apply_glue, canon_for_sweep, sweep_field)

import difflib

# Порог покрытия содержательных слов для MOVED_KEEP (решение 2026-07-21).
MOVED_WORD_COVERAGE = 0.80

# Блок таблицы, собранной Sonnet. Лимит длины — как у маски математики
# glue_pdf_lines (4000), вложенных array в этих данных нет.
ARRAY_RE = re.compile(r'\\begin\{array\}[\s\S]{0,4000}?\\end\{array\}')

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
_TEXT_CMD_RE = re.compile(r'\\text(?:bf|it|rm|sf|tt)?\{([^{}]*)\}')
# Бэкслеш опционален: фрагмент из диффа может начинаться посреди команды
# («begin{center}» без «\» — реальный случай #4541), а слов «begin{...}» в
# живом тексте задач не бывает.
_BEGIN_END_RE = re.compile(r'\\?(?:begin|end)\{[A-Za-z*]+\}(?:\{[^{}]*\})?')
_ESCAPED_CHAR_RE = re.compile(r'\\([%&_#$])')
_CONTROL_SEQ_RE = re.compile(r'\\[a-zA-Z]+')

_NUM_RE = re.compile(r'\d[\d.,]*')
_WORD_RE = re.compile(r'[A-Za-zА-Яа-яЁё]{3,}')

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


def build_fund(texts):
    # type: (List[str]) -> Tuple[Set[str], Set[str]]
    """Фонд происхождения задачи: множества числовых токенов и слов ВСЕГО
    ДО задачи (statement + подпункты с ответами + answer + solution)."""
    nums, words = set(), set()
    for t in texts:
        norm = origin_normalize(t)
        nums.update(origin_nums(norm))
        words.update(origin_words(norm))
    return nums, words


def _check_fragment(fragment, fund_nums, fund_words, require_all_words):
    # type: (str, Set[str], Set[str], bool) -> Dict
    """Проверка одного фрагмента против фонда. Возвращает
    {'ok': bool, 'missing_nums': [...], 'missing_words': [...],
     'coverage': float|None, 'empty': bool}."""
    norm = origin_normalize(fragment)
    nums = origin_nums(norm)
    words = sorted(set(origin_words(norm)) - LATEX_SCAFFOLD_WORDS)
    missing_nums = sorted({n for n in nums if n not in fund_nums})
    missing_words = [w for w in words if w not in fund_words]
    coverage = (1.0 - len(missing_words) / len(words)) if words else None
    if missing_nums:
        ok = False
    elif require_all_words:
        ok = not missing_words
    elif words:
        ok = coverage >= MOVED_WORD_COVERAGE
    else:
        ok = True  # ни слов, ни чужих чисел — судим по числам (все свои)
    return {'ok': ok, 'missing_nums': missing_nums,
            'missing_words': missing_words, 'coverage': coverage,
            'empty': not words and not nums}


def classify_field(old_text, current_text, fund_nums, fund_words):
    # type: (str, str, Set[str], Set[str]) -> Dict
    """Классификация одного поля new_sentence по происхождению.

    Возвращает {'verdict': 'TABLE_KEEP'|'MOVED_KEEP'|'REVERT',
    'reasons': [...], 'new_blocks': N, 'moved_fragments': N,
    'checks': [подробности по фрагментам]}.

    Вердикт полю целиком (откат — тоже per-поле): один фрагмент без
    происхождения топит всё поле в REVERT.
    """
    old_c = canon_for_sweep(old_text)
    cur_c = canon_for_sweep(current_text)

    new_blocks = [b for b in ARRAY_RE.findall(cur_c) if b not in old_c]

    masked_cur = cur_c
    for b in new_blocks:
        masked_cur = masked_cur.replace(b, ' ', 1)

    sm = difflib.SequenceMatcher(None, old_c, masked_cur, autojunk=False)
    moved = []
    n = len(masked_cur)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('insert', 'replace'):
            # Посимвольный дифф режет слова и числа посередине («дходящие»,
            # «спис», «047,62» — реальные обрубки на этих данных): такой
            # огрызок не найдётся в фонде, и поле утонуло бы в REVERT
            # незаслуженно. Расширяем границы фрагмента до целого слова/
            # числа (включая ведущий «\» команды и десятичный разделитель).
            while j1 > 0 and (masked_cur[j1 - 1].isalnum()
                              or masked_cur[j1 - 1] in '\\.,'):
                j1 -= 1
            while j2 < n and (masked_cur[j2].isalnum()
                              or (masked_cur[j2] in '.,' and j2 + 1 < n
                                  and masked_cur[j2 + 1].isalnum())):
                j2 += 1
            chunk = masked_cur[j1:j2]
            if _looks_like_sentence(chunk):
                moved.append(chunk)

    reasons = []
    checks = []
    all_ok = True

    for b in new_blocks:
        res = _check_fragment(b, fund_nums, fund_words, require_all_words=True)
        checks.append({'kind': 'table', 'fragment': b[:400], **res})
        if not res['ok']:
            all_ok = False
            reasons.append('table_block_without_origin (missing_nums={}, '
                           'missing_words={})'.format(
                               res['missing_nums'][:10], res['missing_words'][:10]))

    for frag in moved:
        res = _check_fragment(frag, fund_nums, fund_words, require_all_words=False)
        checks.append({'kind': 'moved', 'fragment': frag[:400], **res})
        if not res['ok']:
            all_ok = False
            if res['missing_nums']:
                reasons.append('new_number_without_origin: {}'.format(
                    res['missing_nums'][:10]))
            else:
                reasons.append('word_coverage {:.0%} < {:.0%} (missing: {})'.format(
                    res['coverage'] or 0.0, MOVED_WORD_COVERAGE,
                    res['missing_words'][:10]))
        elif res['empty']:
            reasons.append('boundary: fragment_without_words_and_nums')
        elif res['coverage'] is None:
            reasons.append('boundary: fragment_without_words_judged_by_nums')

    if '|' in origin_normalize(' '.join(moved)):
        reasons.append('boundary: pipe_table_fragment (markdown-таблица '
                       'палочками, KaTeX её не рендерит — смотреть глазами)')

    if not new_blocks and not moved:
        reasons.append('boundary: no_new_fragments_on_recheck')

    if not all_ok:
        verdict = 'REVERT'
    elif new_blocks:
        verdict = 'TABLE_KEEP'
        if moved:
            reasons.append('boundary: table_plus_moved_text_in_one_field')
    else:
        verdict = 'MOVED_KEEP'

    return {'verdict': verdict, 'reasons': reasons,
            'new_blocks': len(new_blocks), 'moved_fragments': len(moved),
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
