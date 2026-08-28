# -*- coding: utf-8 -*-
"""`render_preflight_v2` — ЕДИНСТВЕННАЯ точка решения «можно ли ставить
`content_format='markdown'`». Шаг 5 архитектуры аудита 2026-08-27.

Почему НОВАЯ функция, а не правка `may_render_as_markdown()`. Старая
функция осталась дословно прежней и по-прежнему используется
`apply_matek_fixed.py` и `corpus_manual_review_queue.py`. Подменить её
семантику молча — ровно та ошибка, из-за которой прежний шлюз считал
себя готовым: он отвечал на вопрос «удалось ли конвертеру разобрать
структуру», а выдавался за ответ на вопрос «увидит ли ученик задачу
целой». Это разные вопросы, и теперь у них разные функции.

Что проверяет (дословно «Итоговый критерий готовности» аудита):

1. **Настоящий KaTeX** (`throwOnError=true`, `strict`, `trust=false`) на
   каждом math-фрагменте — ноль ошибок разбора. Не эвристика: «сломанная
   формула» это то, что решил KaTeX (`problems/management/commands/CLAUDE.md`).
2. **Ноль сырых** `\\begin/\\end`, TikZ/PGFPlots и документных
   LaTeX-команд в видимом тексте.
3. **Ноль `unicodeTextInMathMode`** сверх allowlist (allowlist пуст и это
   задокументировано в `katex_preflight.UNICODE_TEXT_ALLOWLIST`).
4. **Сбалансированные `begin/end`** — до HTML-рендера.
5. **Ни один непустой исходный блок не стал пустым** (живой #41924).
6. **Решение не подменяет условие** (`SOL-LEAK`, 47 задач Archive 3).

Коды дефектов — реестр аудита: `K-ERR`, `K-TEXT`, `K-STRICT`, `MACRO`,
`PLOT`, `R-ENV`, `R-CMD`, `ENV-BAL`, `EMPTY`, `EMPTY-SRC`, `SOL-LEAK`.

При провале карточка НЕ получает молчаливый PASS: она остаётся на
`plain` и уходит в очередь ручного разбора с машинным кодом причины.
"""
from __future__ import annotations

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.katex_preflight import summarize
from problems.corpus_converter.macros import apply_macro_fixes
from problems.corpus_converter.math_canon import canonicalize
from problems.corpus_converter.sol_leak import detect_solution_leak
from problems.corpus_converter.structure_guard import check_problem
from problems.corpus_converter.text_env import convert_text_environments
from problems.corpus_converter.tikz_render import MARKER_RE, extract_tikz_blocks
from problems.corpus_converter.tex_lexer import environment_balance
from problems.rendering import render_markdown


class GateVerdict:
    """`ok` — можно ли ставить markdown. `codes` — машинные причины отказа."""

    __slots__ = ('ok', 'codes', 'details')

    def __init__(self, ok, codes, details):
        self.ok = ok
        self.codes = codes
        self.details = details

    def __repr__(self):
        return f'GateVerdict(ok={self.ok}, codes={self.codes})'


def polish_field(text_md):
    r"""Фазы 4 → 5 → 1 поверх выхода `convert_text_field`.

    Порядок обязателен: сначала снимаются текстовые обёртки (иначе
    `\begin{quote}` мешает лексеру видеть настоящие границы), потом
    чинятся опечатки макросов (иначе `\Tilde` дойдёт до KaTeX
    неизвестной командой), и только потом канонизируется математика.

    TikZ сюда уже не попадает: он вырезан из СЫРОГО текста раньше, до
    стадии 1 (см. `convert_problem_v2`)."""
    text = convert_text_environments(text_md or '')
    text = apply_macro_fixes(text)
    return canonicalize(text)


def convert_problem_v2(statement, answer='', solution='', existing_parts=None):
    """Полный конвейер: стадия 1 (`core.convert_problem`) + Фазы 4/5/1.

    Стадия 1 не тронута — у неё свои живые регрессии (#41612, #26337,
    #47127, #41824), и они обязаны продолжать проходить."""
    figures = []

    def cut_figures(raw_text, source_field, part_label=None):
        """Вырезать TikZ из СЫРОГО текста, до стадии 1.

        ⚠️ Порядок выяснен прогоном компиляции, а не рассуждением.
        Сначала извлечение стояло ПОСЛЕ стадии 1 — и картинки не
        собирались: `normalize_dashes` в `core.py` успевала превратить
        `--` в `–`, а ` - ` в ` — ` ВНУТРИ кода картинки, и latex падал
        на `\\draw (0,1.5) – (4.5,1.5);` и `{52 — 0.5*x^2}` (живые
        #43955, #30164, #30172). TikZ — не проза, и через
        типографскую нормализацию проходить не должен вовсе.

        Маркер `[[FIGURE:<hex>]]` стадию 1 переживает без изменений:
        в нём нет ни дефисов, ни `%`, ни математики."""
        out, blocks = extract_tikz_blocks(raw_text or '')
        for digest, source in blocks:
            if not any(f['hash'] == digest for f in figures):
                figures.append({'hash': digest, 'source': source,
                                'field': source_field, 'part': part_label})
        return out

    statement = cut_figures(statement, 'statement')
    answer = cut_figures(answer, 'answer')
    solution = cut_figures(solution, 'solution')
    if existing_parts is not None:
        existing_parts = [(label, cut_figures(text, 'part', label))
                          for label, text in existing_parts]

    result = convert_problem(
        statement=statement, answer=answer, solution=solution,
        existing_parts=existing_parts,
    )
    result['statement_md'] = polish_field(result['statement_md'])
    for part in result['parts']:
        part['statement_md'] = polish_field(part['statement_md'])
    result['answer_md'] = polish_field(result['answer_md'])
    result['solution_md'] = polish_field(result['solution_md'])
    #: Блоки TikZ, которые надо скомпилировать в ProblemFigure. Сам
    #: конвертер в базу не пишет — это делает corpus_build_figures.
    result['figures'] = figures
    return result


def build_blocks(raw_statement, raw_parts, raw_answer, raw_solution, result):
    """Пары «исходник → канонизированный markdown» в порядке показа.

    Порядок повторяет `catalog/templates/catalog/problem_detail.html`:
    каждое поле рендерится ОТДЕЛЬНЫМ вызовом `render_markdown`, общего
    склеенного текста задачи не существует нигде."""
    blocks = [('Условие', raw_statement, result['statement_md'])]
    for (label, raw_part), converted in zip(raw_parts, result['parts']):
        blocks.append((f'Часть {label}', raw_part, converted['statement_md']))
    if raw_answer or result['answer_md']:
        blocks.append(('Ответ', raw_answer, result['answer_md']))
    if raw_solution or result['solution_md']:
        blocks.append(('Решение', raw_solution, result['solution_md']))
    return blocks


def render_preflight_v2(blocks, checker, raw_statement='',
                        available_figures=None):
    """Вердикт шлюза по одной задаче.

    `blocks` — список `(имя, исходный_текст, канонизированный_md)`.
    `checker` — открытый `KatexPreflight` (браузер поднимается один раз
    на весь корпус, не на задачу).
    """
    codes, details = [], []

    def add(code, detail):
        if code not in codes:
            codes.append(code)
        details.append(detail)

    # --- 6. решение вместо условия -------------------------------------
    leaked, why = detect_solution_leak(raw_statement)
    if leaked:
        add('SOL-LEAK', why)

    # --- 5. сохранность содержимого ------------------------------------
    part_names = [name for name, _r, _c in blocks if name.startswith('Часть ')]
    lost, needs_content = check_problem(blocks, part_names=part_names)
    if lost:
        add('EMPTY', f'непустой исходный блок стал пустым на экране: {lost}')
    if needs_content:
        add('EMPTY-SRC', 'у задачи нет содержимого ни в одном блоке — '
                         'дефект материала, не конвертера')

    # --- 6б. маркер картинки без готовой картинки -----------------------
    # Маркер, для которого нет строки ProblemFigure, на экране просто
    # исчезает (см. problems/figures.py) — то есть график молча пропал бы.
    # Это такой же дефект показа, как сырой ddplot, и пропускать его
    # нельзя. Проверка включается только когда вызывающая сторона знает
    # список готовых картинок (передала available_figures).
    if available_figures is not None:
        missing = sorted({
            match.group(1)[:12]
            for _name, _raw, canonical in blocks
            for match in MARKER_RE.finditer(canonical or '')
            if match.group(1) not in available_figures
        })
        if missing:
            add('FIGURE-MISSING',
                f'картинка не собрана для маркеров: {missing}')

    # --- 4. баланс окружений (до HTML-рендера) --------------------------
    for name, _raw, canonical in blocks:
        balanced, unclosed, unopened = environment_balance(canonical or '')
        if not balanced:
            add('ENV-BAL', f'{name}: незакрытые {unclosed or []}, '
                           f'лишние \\end {unopened or []}')

    # --- 1-3. настоящий рендер ------------------------------------------
    # Все блоки задачи уходят в браузер ОДНИМ вызовом: на корпусе в
    # 16 804 задачи поблочный round-trip стоил бы втрое дороже.
    htmls = [render_markdown(canonical or '') for _name, _raw, canonical in blocks]
    reports = checker.check_many(htmls)
    for (name, _raw, _canonical), report in zip(blocks, reports):
        ok, block_codes, block_details = summarize(report)
        if ok:
            continue
        for code, detail in zip(block_codes, block_details):
            add(code, f'{name}: {detail}')
        for code in block_codes[len(block_details):]:
            add(code, name)

    return GateVerdict(not codes, codes, details)
