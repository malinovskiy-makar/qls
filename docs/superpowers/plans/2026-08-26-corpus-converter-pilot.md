# Corpus Converter Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one shared, pure-function text-conversion module (`problems/corpus_converter/`) that turns raw задача text into `CORPUS-FORMAT.md §3` target format, and run it read-only against two pilot sources — ILE (already in DB, UPDATE path) and Школково (on disk, INSERT path) — producing a single human-readable "было → стало" report. No database write of any kind happens in this pilot.

**Architecture:** A pure conversion core (`core.py`) does all text transforms field-by-field (statement/answer/solution/criteria/ProblemPart.statement), reusing the math-region protection primitives already proven in `problems/rendering.py` so structural transforms (bold/italic/lists/tables/dashes) never touch anything inside `$...$`/`$$...$$`/`\(...\)`/`\[...\]`. A separate `criteria.py` parses Школково's `criteria_tex` prose into candidate `Rubric`/`RubricCriterion` structures. Two thin, read-only management commands (`corpus_pilot_ile`, `corpus_pilot_shkolkovo`) orchestrate DB/disk reads, call the core, and assemble the report — neither command ever calls `.save()`/`.create()`/`.update()`.

**Tech Stack:** Python 3.13, Django 5.2 ORM (read-only queries), stdlib `re`/`json`/`hashlib`/`random`, project's existing `markdown_it`/`nh3` stack (imported, not modified) for cross-checking output actually renders.

**Spec:** [docs/CORPUS-FORMAT.md](../../CORPUS-FORMAT.md) §3 (target format table) · [docs/diagnostics/corpus_format_sweep_20260824.md](../../diagnostics/corpus_format_sweep_20260824.md) (ILE trusted-signal caveats) · [docs/CORPUS_FORMAT_ATLAS_20260825.md](../../CORPUS_FORMAT_ATLAS_20260825.md) (per-source profiles, "что рендерер обязан уметь")

## Global Constraints

- **Read-only, no exceptions.** Phase 1 (ILE) and Phase 2 (Школково) touch the DB only via `.filter()`/`.values()`/read queries. No `Problem`/`ProblemPart`/`Rubric`/`FileAsset` row is created, updated, or deleted anywhere in this plan.
- **Numeric invariant, asserted in code, not just narrated:** `Problem.objects.count()` before == after in every command; 0 new rows in `ProblemPart`/`Rubric`/`FileAsset` (`RubricCriterion` too).
- **Branch:** `feat/corpus-converter-pilot`, created from `main` at the current tip (`b86a501`). Never push, never merge to `main` — stop-gate from the brief.
- **Reuse, don't reimplement, math-boundary logic.** Import `_protect_math_and_currency`/`_restore_math_and_currency` from `problems/rendering.py` — that logic is already a mirror of the browser's KaTeX boundary code (`templates/_katex_dollars.html`); a second implementation would drift from it exactly the way `problems/diagnostics.py:strip_math_regions` already has (documented divergence in `rendering.py`'s own docstring).
- **Don't trust noisy signals.** Per `corpus_format_sweep_20260824.md`: bare `-`/`+` at line start and bare `\d+[.)]` are NOT reliable list markers (formula line-wraps, source problem numbers, year prefixes). The converter only auto-converts **trusted** signals: explicit LaTeX `\begin{itemize}`/`\begin{enumerate}` and explicit markdown `**`/`\textbf{`/`\textit{`/`\emph{`. It does not invent list structure from bare punctuation.
- **5 pre-existing `content_format='markdown'` rows exist** (`Problem` ids 53709–53713, source "Служебное: фикстуры рендерера (не публиковать)"). Both pilot queries must exclude this source explicitly — confirmed via `manage.py shell` on 2026-08-26, not assumed from the brief.
- **`ProblemPart.answer` has no `blank=True`.** Candidate part dicts must always include an `answer` key (empty string is fine) so a future real import doesn't hit a surprise at `full_clean()` time.
- **Model field names, confirmed by reading `problems/models.py`:** `Rubric.problem` (FK, no per-part link — one `Rubric` per `Problem`), `RubricCriterion.rubric`/`.name`/`.max_points`/`.description`/`.order`, `ProblemPart.problem`/`.label`/`.statement`/`.answer`/`.solution`/`.points`/`.order`, `FileAsset.kind` (`Kind.IMAGE` etc.), `SourceReference.source.name`.

---

## File Structure

- Create: `problems/corpus_converter/__init__.py` — empty, makes it a package.
- Create: `problems/corpus_converter/core.py` — pure text transforms, no I/O, no Django imports except the two reused functions from `problems/rendering.py`.
- Create: `problems/corpus_converter/criteria.py` — Школково `criteria_tex` → candidate `Rubric` parser. Separate file: distinct, source-specific parsing logic that would otherwise bloat `core.py`.
- Create: `problems/tests/test_corpus_converter_core.py` — unit tests for every rule in `core.py`, including the required 7 red→green defect-testing pairs.
- Create: `problems/tests/test_corpus_converter_criteria.py` — unit tests for `criteria.py`.
- Create: `problems/management/commands/corpus_pilot_ile.py` — Phase 1, UPDATE path, read-only.
- Create: `problems/management/commands/corpus_pilot_shkolkovo.py` — Phase 2, INSERT path, read-only, reads `weconomics-data/shkolkovo/` from disk.
- Create: `reports/corpus_converter_pilot/report.md` — generated output, not hand-written (produced by the two commands above via a shared small assembler in `problems/corpus_converter/report.py`).
- Create: `problems/corpus_converter/report.py` — tiny shared helper that both commands call to render one "было → стало" entry as Markdown, so the two commands don't duplicate formatting.

---

## Task 1: Branch + package scaffold

**Files:**
- Create: `problems/corpus_converter/__init__.py`

**Interfaces:**
- Produces: the `problems.corpus_converter` package other tasks import from.

- [ ] **Step 1: Create the branch**

```bash
git checkout main
git pull --ff-only
git checkout -b feat/corpus-converter-pilot
```

- [ ] **Step 2: Create the empty package**

```python
# problems/corpus_converter/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add problems/corpus_converter/__init__.py
git commit -m "corpus_converter: scaffold package"
```

---

## Task 2: Math-region protection + bare environment wrapping

**Files:**
- Modify: `problems/corpus_converter/core.py` (create)
- Test: `problems/tests/test_corpus_converter_core.py` (create)

**Interfaces:**
- Consumes: `problems.rendering._protect_math_and_currency`, `problems.rendering._restore_math_and_currency` (existing, private but stable — reused as-is, not modified).
- Produces: `wrap_bare_environments(text: str) -> str`, `protect_math(text: str) -> tuple[str, list[str]]`, `restore_math(text: str, protected: list[str]) -> str` — used by every later task in this file.

- [ ] **Step 1: Write the failing tests**

```python
# problems/tests/test_corpus_converter_core.py
from django.test import SimpleTestCase

from problems.corpus_converter.core import wrap_bare_environments, protect_math, restore_math


class WrapBareEnvironmentsTests(SimpleTestCase):
    def test_wraps_bare_equation(self):
        text = 'Найдите Q.\n\\begin{equation}\nQ = 10 - P\n\\end{equation}\nОтвет готов.'
        result = wrap_bare_environments(text)
        self.assertIn('$$\n\\begin{equation}\nQ = 10 - P\n\\end{equation}\n$$', result)

    def test_does_not_double_wrap_already_wrapped(self):
        text = 'Формула: $$\\begin{align}Q = 10 - P\\end{align}$$'
        result = wrap_bare_environments(text)
        self.assertEqual(text, result)

    def test_does_not_touch_cases_environment(self):
        text = 'Кусочная функция $$f(x) = \\begin{cases}1 & x>0\\\\0 & x\\le 0\\end{cases}$$'
        result = wrap_bare_environments(text)
        self.assertEqual(text, result)


class ProtectMathTests(SimpleTestCase):
    def test_protects_and_restores_dollar_math(self):
        text = 'Цена $P^*=10$ и объём $Q^*=5$.'
        protected_text, spans = protect_math(text)
        self.assertNotIn('P^*', protected_text)
        self.assertEqual(restore_math(protected_text, spans), text)

    def test_protects_array_inside_double_dollar(self):
        text = 'Матрица: $$\\begin{array}{cc}1&2\\\\3&4\\end{array}$$ конец.'
        protected_text, spans = protect_math(text)
        self.assertNotIn('array', protected_text)
        self.assertEqual(restore_math(protected_text, spans), text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'problems.corpus_converter.core'`

- [ ] **Step 3: Write minimal implementation**

```python
# problems/corpus_converter/core.py
# -*- coding: utf-8 -*-
"""Общий конвертер текста задачи к целевому формату (CORPUS-FORMAT.md §3).

Пилот: UPDATE (ILE, задача уже в базе) и INSERT (Школково, парсинг с диска).
Чистые функции — вход текст, выход текст/структура, никакого I/O и ORM.
"""
from __future__ import annotations

import re

from problems.rendering import _protect_math_and_currency, _restore_math_and_currency

#: Голые окружения — те же, что CORPUS-FORMAT.md §3 и атлас источников:
#: equation/align/gather (со звёздочкой или без). cases НЕ входит — оно
#: почти всегда уже внутри более крупной формулы (см. CORPUS-FORMAT.md
#: Приложение, п.1) и никогда не оборачивается само по себе.
_BARE_ENV_NAMES = ('equation', 'align', 'gather')
_BARE_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(_BARE_ENV_NAMES) + r'\*?)\}.*?\\end\{\1\}',
    re.DOTALL,
)

#: Границы формулы — буквальная копия набора из rendering.py, нужна здесь
#: только чтобы проверить «уже обёрнуто?» перед оборачиванием.
_MATH_OPEN_CLOSE = (('$$', '$$'), ('\\[', '\\]'), ('\\(', '\\)'), ('$', '$'))


def _is_already_wrapped(text, start, end):
    """Проверить, стоит ли по обе стороны от text[start:end] один и тот же
    разделитель формулы (например ``$$`` перед и после)."""
    for open_, close in _MATH_OPEN_CLOSE:
        before = text[max(0, start - len(open_)):start]
        after = text[end:end + len(close)]
        if before == open_ and after == close:
            return True
    return False


def wrap_bare_environments(text):
    """Обернуть голые ``\\begin{equation|align|gather}...\\end{...}`` в ``$$``.

    Не трогает уже обёрнутые (проверка по границам) и не трогает ``cases``
    вовсе (его нет в списке имён окружений)."""
    out = []
    pos = 0
    for match in _BARE_ENV_RE.finditer(text):
        start, end = match.span()
        out.append(text[pos:start])
        if _is_already_wrapped(text, start, end):
            out.append(match.group(0))
        else:
            out.append('$$\n' + match.group(0) + '\n$$')
        pos = end
    out.append(text[pos:])
    return ''.join(out)


def protect_math(text):
    """Вырезать математику/валюту плейсхолдерами. Обёртка над rendering.py —
    единая точка правды для границ формулы во всём проекте (сайт и
    конвертер должны видеть одну и ту же границу)."""
    return _protect_math_and_currency(text)


def restore_math(text, protected):
    """Вернуть математику на место НЕТРОНУТОЙ (без HTML-экранирования —
    конвертер производит markdown-текст, не HTML, экранирование делает
    rendering.py на следующем шаге, при показе)."""
    def repl(match):
        return protected[int(match.group(1))]
    from problems.rendering import _PLACEHOLDER_RE
    return _PLACEHOLDER_RE.sub(repl, text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (5 tests)

- [ ] **Step 5: Defect-testing pair #1 (bare-environment wrapping)**

Temporarily break `wrap_bare_environments` by changing `_BARE_ENV_NAMES` to `()` (empty tuple), rerun `test_wraps_bare_equation` — confirm it goes RED (`AssertionError`). Revert the change, rerun — confirm GREEN. Record both outcomes in the task's commit message trailer.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: bare-environment wrapping + math protection

Defect-testing #1 (bare equation/align/gather wrapping): confirmed RED with
_BARE_ENV_NAMES=() then GREEN after revert."
```

---

## Task 3: Junk-command stripping, color stripping, TeX-comment stripping

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Consumes: nothing new (operates on already math-protected text).
- Produces: `strip_junk_commands(text: str) -> str`, `strip_color(text: str) -> str`, `strip_tex_comments(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
class StripJunkCommandsTests(SimpleTestCase):
    def test_removes_medskip_and_friends_without_trace(self):
        text = 'Первая часть.\\medskip\n\\noindent Вторая часть.\\quad\\qquad'
        result = strip_junk_commands(text)
        self.assertNotIn('\\medskip', result)
        self.assertNotIn('\\noindent', result)
        self.assertNotIn('\\quad', result)
        self.assertIn('Первая часть.', result)
        self.assertIn('Вторая часть.', result)


class StripColorTests(SimpleTestCase):
    def test_textcolor_keeps_content_drops_color(self):
        text = 'Ответ: \\textcolor{red}{неверно}.'
        self.assertEqual(strip_color(text), 'Ответ: неверно.')

    def test_bare_color_switch_removed(self):
        text = '\\color{blue}Текст синим.'
        self.assertEqual(strip_color(text), 'Текст синим.')


class StripTexCommentsTests(SimpleTestCase):
    def test_removes_comment_line_start(self):
        text = 'Условие.\n% Q = 2KL (KL=16)\nОтвет: 5.'
        result = strip_tex_comments(text)
        self.assertNotIn('Q = 2KL', result)
        self.assertIn('Условие.', result)
        self.assertIn('Ответ: 5.', result)

    def test_keeps_escaped_percent(self):
        text = 'Ставка 20\\% годовых.'
        self.assertEqual(strip_tex_comments(text), text)

    def test_keeps_percent_in_prose(self):
        text = 'Курс вырос на 20% за год.'
        self.assertEqual(strip_tex_comments(text), text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError` for the three new names.

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
#: Команды-«воздух»: чисто оформительские, переносить некуда (задача CSS,
#: не текста) — CORPUS-FORMAT.md §3, строка «\\medskip, \\bigskip, ...».
_JUNK_COMMANDS = (
    r'\\medskip', r'\\bigskip', r'\\quad', r'\\qquad',
    r'\\noindent', r'\\centering',
)
_JUNK_COMMANDS_RE = re.compile('|'.join(_JUNK_COMMANDS))


def strip_junk_commands(text):
    """Убрать \\medskip/\\bigskip/\\quad/\\qquad/\\noindent/\\centering
    целиком, без замены."""
    return _JUNK_COMMANDS_RE.sub('', text)


#: \textcolor{цвет}{содержимое} — двухаргументная форма, содержимое остаётся.
_TEXTCOLOR_RE = re.compile(r'\\textcolor\{[^}]*\}\{([^}]*)\}')
#: \color{цвет} — переключатель без своих аргументов-содержимого, убирается целиком.
_COLOR_SWITCH_RE = re.compile(r'\\color\{[^}]*\}')


def strip_color(text):
    """Убрать \\color/\\textcolor, оставить содержимое без цвета."""
    text = _TEXTCOLOR_RE.sub(r'\1', text)
    text = _COLOR_SWITCH_RE.sub('', text)
    return text


#: Комментарий — '%' в начале строки (после необязательных пробелов),
#: НЕ экранированный '\%'. Ловушка задокументирована в атласе: снимать
#: комментарии нужно ДО остального разбора, но '\%' — легитимный процент.
_TEX_COMMENT_RE = re.compile(r'(?<!\\)%[^\n]*')


def strip_tex_comments(text):
    """Убрать TeX-комментарии (не экранированный '%' и всё до конца строки)."""
    return _TEX_COMMENT_RE.sub('', text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (11 tests total)

- [ ] **Step 5: Defect-testing pair #2 (junk-command stripping)**

Temporarily change `_JUNK_COMMANDS` to `()`, rerun `test_removes_medskip_and_friends_without_trace` — confirm RED. Revert, confirm GREEN.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: strip junk commands, color markup, TeX comments

Defect-testing #2 (junk-command stripping): confirmed RED with
_JUNK_COMMANDS=() then GREEN after revert."
```

---

## Task 4: Bold/italic normalization (markdown-agnostic, math-safe)

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Consumes: `protect_math`/`restore_math` from Task 2 (bold/italic conversion must run on math-protected text so `$x_1$`/`$Q^*$` are never touched).
- Produces: `convert_emphasis(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
class ConvertEmphasisTests(SimpleTestCase):
    def test_textbf_to_markdown_bold(self):
        self.assertEqual(convert_emphasis('\\textbf{Важно}'), '**Важно**')

    def test_textit_and_emph_to_markdown_italic(self):
        self.assertEqual(convert_emphasis('\\textit{тонко}'), '*тонко*')
        self.assertEqual(convert_emphasis('\\emph{тонко}'), '*тонко*')

    def test_existing_markdown_bold_untouched(self):
        self.assertEqual(convert_emphasis('**уже жирный**'), '**уже жирный**')

    def test_does_not_touch_star_inside_math(self):
        text, protected = protect_math('Оптимум $Q^*=20$, цена $P^*=5$.')
        result = restore_math(convert_emphasis(text), protected)
        self.assertEqual(result, 'Оптимум $Q^*=20$, цена $P^*=5$.')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError: cannot import name 'convert_emphasis'`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
#: \textbf{X} -> **X**; \textit{X}/\emph{X} -> *X*. Нежадный [^}]* — без
#: вложенных фигурных скобок внутри аргумента (в банке их не встречалось,
#: см. атлас: собственных макросов в телах практически нет).
_TEXTBF_RE = re.compile(r'\\textbf\{([^}]*)\}')
_TEXTIT_EMPH_RE = re.compile(r'\\(?:textit|emph)\{([^}]*)\}')


def convert_emphasis(text):
    """LaTeX \\textbf/\\textit/\\emph -> markdown **/*. Уже-markdown
    **жирный**/*курсив* проходит без изменений (regex их не матчит).
    Вызывать ТОЛЬКО на math-protected тексте — иначе `$Q^*$` пострадает
    от парсера markdown позже, но сам этот шаг звёздочки не трогает вовсе,
    только \\textbf/\\textit/\\emph."""
    text = _TEXTBF_RE.sub(r'**\1**', text)
    text = _TEXTIT_EMPH_RE.sub(r'*\1*', text)
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (15 tests total)

- [ ] **Step 5: Defect-testing pair #3 (bold vs italic confusion)**

Temporarily swap the replacement templates (`_TEXTBF_RE.sub(r'*\1*', ...)` — single star instead of double), rerun `test_textbf_to_markdown_bold` — confirm RED (asserts `**Важно**`, gets `*Важно*`). Revert, confirm GREEN.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: LaTeX bold/italic -> markdown, math-safe

Defect-testing #3 (bold/italic distinction): confirmed RED swapping
textbf's replacement to single-star then GREEN after revert."
```

---

## Task 5: Lists — only trusted LaTeX signals

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Produces: `convert_lists(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
class ConvertListsTests(SimpleTestCase):
    def test_itemize_to_markdown_bullets(self):
        text = '\\begin{itemize}\\item Первое\\item Второе\\end{itemize}'
        result = convert_lists(text)
        self.assertEqual(result, '- Первое\n- Второе')

    def test_enumerate_to_markdown_numbers(self):
        text = '\\begin{enumerate}\\item Первое\\item Второе\\end{enumerate}'
        result = convert_lists(text)
        self.assertEqual(result, '1. Первое\n2. Второе')

    def test_bare_dash_at_line_start_not_touched(self):
        # Ловушка sweep-диагностики: '-' в начале строки — часто обрыв
        # формулы на переносе, не буллит. Конвертер его не трогает.
        text = 'Баланс:\n-\nэ (перенос строки внутри формулы PDF-нарезки)'
        self.assertEqual(convert_lists(text), text)

    def test_bare_digit_paren_at_line_start_not_touched(self):
        # Ловушка: '2018)' — год исходного вопроса, не номер пункта списка.
        text = '2018) Активами Центрального банка (ЦБ) являются:'
        self.assertEqual(convert_lists(text), text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError: cannot import name 'convert_lists'`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
#: Только явные LaTeX-окружения — доверенный сигнал по sweep-диагностике
#: (corpus_format_sweep_20260824.md: "italic/список — шумные признаки").
#: Голая '-'/'N.'/'N)' в начале строки НЕ распознаётся как список нигде
#: в этом модуле — намеренно, это и есть защита от ловушек метода.
_ITEMIZE_RE = re.compile(r'\\begin\{itemize\}(.*?)\\end\{itemize\}', re.DOTALL)
_ENUMERATE_RE = re.compile(r'\\begin\{enumerate\}(.*?)\\end\{enumerate\}', re.DOTALL)
#: \item[X] — ручная метка (Школково: (а), А), 1) ...) — сохраняется как
#: текст пункта, не переинтерпретируется; \item без метки просто режет на пункты.
_ITEM_RE = re.compile(r'\\item(?:\[([^\]]*)\])?\s*')


def _split_items(body):
    items = []
    for chunk in _ITEM_RE.split(body):
        pass
    # \item[label]?content — re.split с группой возвращает
    # [pre, label_or_None, content, label_or_None, content, ...]
    parts = _ITEM_RE.split(body)
    pre = parts[0]
    if pre.strip():
        # Текст до первого \item внутри itemize/enumerate не встречался
        # в проверенных источниках — не теряем его молча.
        items.append(pre.strip())
    for i in range(1, len(parts), 2):
        label = parts[i]
        content = parts[i + 1].strip() if i + 1 < len(parts) else ''
        if label:
            items.append(f'{label} {content}'.strip())
        else:
            items.append(content)
    return [item for item in items if item]


def convert_lists(text):
    """\\begin{itemize}/\\begin{enumerate} -> markdown-списки с реальными
    переносами строк. Не трогает ничего вне этих двух явных окружений."""
    def repl_itemize(match):
        items = _split_items(match.group(1))
        return '\n'.join(f'- {item}' for item in items)

    def repl_enumerate(match):
        items = _split_items(match.group(1))
        return '\n'.join(f'{i}. {item}' for i, item in enumerate(items, start=1))

    text = _ITEMIZE_RE.sub(repl_itemize, text)
    text = _ENUMERATE_RE.sub(repl_enumerate, text)
    return text
```

(Remove the stray no-op `for chunk in ... : pass` loop before committing — leftover from drafting, dead code.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (19 tests total)

- [ ] **Step 5: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: itemize/enumerate -> markdown lists, trusted-signal only"
```

---

## Task 6: Tables — simple vs complex

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Produces: `convert_tables(text: str) -> tuple[str, bool]` — returns `(new_text, complex_table_found)`.

- [ ] **Step 1: Write the failing tests**

```python
class ConvertTablesTests(SimpleTestCase):
    def test_simple_tabular_to_markdown_table(self):
        text = (
            '\\begin{tabular}{|l|c|}\\hline\n'
            'Показатель & Значение \\\\\\hline\n'
            'Q & 10 \\\\\\hline\n'
            '\\end{tabular}'
        )
        result, complex_found = convert_tables(text)
        self.assertFalse(complex_found)
        self.assertIn('| Показатель | Значение |', result)
        self.assertIn('| --- | --- |', result)
        self.assertIn('| Q | 10 |', result)
        self.assertNotIn('\\begin{tabular}', result)

    def test_complex_table_left_untouched_and_flagged(self):
        text = (
            '\\begin{tabular}{|l|c|c|}\\hline\n'
            '\\multicolumn{2}{|c|}{Итого} & 100 \\\\\\hline\n'
            '\\end{tabular}'
        )
        result, complex_found = convert_tables(text)
        self.assertTrue(complex_found)
        self.assertEqual(result, text)

    def test_multirow_also_flags_complex(self):
        text = '\\begin{tabular}{|l|}\\multirow{2}{*}{X}\\end{tabular}'
        _, complex_found = convert_tables(text)
        self.assertTrue(complex_found)

    def test_existing_markdown_table_untouched(self):
        text = '| A | B |\n| --- | --- |\n| 1 | 2 |'
        result, complex_found = convert_tables(text)
        self.assertEqual(result, text)
        self.assertFalse(complex_found)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError: cannot import name 'convert_tables'`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
_TABULAR_RE = re.compile(r'\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}', re.DOTALL)
_MULTICOL_ROW_RE = re.compile(r'\\multicolumn|\\multirow')
_HLINE_RE = re.compile(r'\\hline')


def _tabular_to_markdown(body):
    """Тело tabular (между {cols} и \\end) -> markdown-таблица.

    Строки режутся по '\\\\', ячейки — по '&'. \\hline игнорируется
    (роль отступа/рамки, в markdown-таблице у неё нет аналога)."""
    body = _HLINE_RE.sub('', body)
    rows = [row.strip() for row in body.split('\\\\') if row.strip()]
    grid = [[cell.strip() for cell in row.split('&')] for row in rows]
    if not grid:
        return None
    width = len(grid[0])
    lines = ['| ' + ' | '.join(grid[0]) + ' |']
    lines.append('| ' + ' | '.join(['---'] * width) + ' |')
    for row in grid[1:]:
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)


def convert_tables(text):
    """Простые \\begin{tabular} (без multicolumn/multirow) -> markdown-таблицы.
    Сложные — не трогаем, сигнализируем True вторым элементом кортежа, ради
    ручной очереди (CORPUS-FORMAT.md §3: "слияние ячеек markdown-таблицей
    не выражается")."""
    complex_found = False
    out = []
    pos = 0
    for match in _TABULAR_RE.finditer(text):
        start, end = match.span()
        body = match.group(1)
        out.append(text[pos:start])
        if _MULTICOL_ROW_RE.search(body):
            complex_found = True
            out.append(match.group(0))
        else:
            markdown_table = _tabular_to_markdown(body)
            out.append(markdown_table if markdown_table is not None else match.group(0))
        pos = end
    out.append(text[pos:])
    return ''.join(out), complex_found
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (23 tests total)

- [ ] **Step 5: Defect-testing pair #4 (simple vs complex table)**

Temporarily remove the `if _MULTICOL_ROW_RE.search(body):` branch (always convert), rerun `test_complex_table_left_untouched_and_flagged` — confirm RED (a `\multicolumn` table gets flattened instead of left untouched). Revert, confirm GREEN.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: simple tabular -> markdown table, complex -> manual queue

Defect-testing #4 (simple vs complex table): confirmed RED removing the
multicolumn/multirow guard then GREEN after revert."
```

---

## Task 7: Footnotes -> end-of-solution note

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Produces: `extract_footnotes(text: str) -> tuple[str, list[str]]` — text with footnotes removed, list of footnote contents in order found.
- Produces: `append_footnote_notes(text: str, notes: list[str]) -> str` — appends "Примечание: ..." paragraph(s) at the end.

- [ ] **Step 1: Write the failing tests**

```python
class FootnoteTests(SimpleTestCase):
    def test_extracts_single_footnote(self):
        text = 'Цена росла\\footnote{данные ЦБ за 2020 год} весь квартал.'
        result, notes = extract_footnotes(text)
        self.assertEqual(result, 'Цена росла весь квартал.')
        self.assertEqual(notes, ['данные ЦБ за 2020 год'])

    def test_extracts_multiple_footnotes_in_order(self):
        text = 'Первая\\footnote{сноска раз} и вторая\\footnote{сноска два}.'
        result, notes = extract_footnotes(text)
        self.assertEqual(result, 'Первая и вторая.')
        self.assertEqual(notes, ['сноска раз', 'сноска два'])

    def test_append_single_note(self):
        result = append_footnote_notes('Решение готово.', ['данные ЦБ за 2020 год'])
        self.assertEqual(
            result,
            'Решение готово.\n\nПримечание: данные ЦБ за 2020 год',
        )

    def test_append_multiple_notes_numbered(self):
        result = append_footnote_notes('Решение готово.', ['раз', 'два'])
        self.assertEqual(
            result,
            'Решение готово.\n\nПримечание 1: раз\nПримечание 2: два',
        )

    def test_append_no_notes_is_noop(self):
        self.assertEqual(append_footnote_notes('Решение готово.', []), 'Решение готово.')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
_FOOTNOTE_RE = re.compile(r'\s*\\footnote\{([^}]*)\}')


def extract_footnotes(text):
    """Вырезать \\footnote{...} из текста, собрать содержимое по порядку.
    Пробел ПЕРЕД сноской в исходнике съедается вместе с ней, чтобы не
    оставить двойной пробел на месте вырезанной сноски."""
    notes = []

    def repl(match):
        notes.append(match.group(1))
        return ''

    result = _FOOTNOTE_RE.sub(repl, text)
    return result, notes


def append_footnote_notes(text, notes):
    """Дописать сноски в конец отдельным абзацем «Примечание: …» —
    CORPUS-FORMAT.md §3: "ссылку-маркер в тексте не пытаться имитировать"."""
    if not notes:
        return text
    if len(notes) == 1:
        lines = [f'Примечание: {notes[0]}']
    else:
        lines = [f'Примечание {i}: {note}' for i, note in enumerate(notes, start=1)]
    return text + '\n\n' + '\n'.join(lines) if len(notes) == 1 else text + '\n\n' + '\n'.join(lines)
```

(Simplify the final `return` — the ternary is redundant, both branches are identical; use `return text + '\n\n' + '\n'.join(lines)` directly before committing.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (28 tests total)

- [ ] **Step 5: Defect-testing pair #5 (footnote extraction)**

Temporarily change `extract_footnotes` to `return text, []` (no-op), rerun `test_extracts_single_footnote` — confirm RED. Revert, confirm GREEN.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: footnotes -> end-of-text 'Примечание' paragraph

Defect-testing #5 (footnote extraction): confirmed RED with extract_footnotes
as no-op then GREEN after revert."
```

---

## Task 8: Dash and quote normalization

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Produces: `normalize_dashes(text: str) -> str`, `normalize_quotes(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
class NormalizeDashesTests(SimpleTestCase):
    def test_triple_hyphen_to_em_dash(self):
        self.assertEqual(normalize_dashes('рост---за год'), 'рост—за год')

    def test_double_hyphen_to_en_dash(self):
        self.assertEqual(normalize_dashes('2020--2021'), '2020–2021')

    def test_spaced_single_hyphen_to_em_dash(self):
        self.assertEqual(
            normalize_dashes('Спрос растёт - предложение падает'),
            'Спрос растёт — предложение падает',
        )

    def test_hyphen_inside_word_untouched(self):
        # Составное слово — не тире, трогать нельзя.
        self.assertEqual(normalize_dashes('объект-договор'), 'объект-договор')

    def test_hyphen_in_negative_number_untouched(self):
        self.assertEqual(normalize_dashes('температура -5 градусов'), 'температура -5 градусов')


class NormalizeQuotesTests(SimpleTestCase):
    def test_angle_quotes_to_guillemets(self):
        self.assertEqual(normalize_quotes('<<Ромашка>>'), '«Ромашка»')

    def test_straight_double_quotes_alternate_to_guillemets(self):
        self.assertEqual(
            normalize_quotes('фирма "Ромашка" продала "Одуванчик"'),
            'фирма «Ромашка» продала «Одуванчик»',
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
def normalize_dashes(text):
    """--- -> —, -- -> –, ' - ' (тире между словами) -> ' — '.

    Одиночный '-' без пробелов с обеих сторон НЕ трогается — он почти
    всегда часть слова (составное существительное) или знак минуса перед
    числом, а не тире (CORPUS-FORMAT.md §3 обсуждает только сам факт
    нормализации, различение "тире vs дефис" — эвристика этой сессии,
    задокументированная явно, а не молчаливое допущение)."""
    text = text.replace('---', '—')
    text = text.replace('--', '–')
    text = re.sub(r'(?<=\S) - (?=\S)', ' — ', text)
    return text


#: Прямые кавычки режутся ПАРАМИ по очереди: первая пара -> «», вторая
#: -> «», и так далее — нечётная кавычка (без пары) не трогается вовсе.
_STRAIGHT_QUOTE_RE = re.compile(r'"([^"]*)"')
_ANGLE_QUOTE_RE = re.compile(r'<<([^>]*)>>')


def normalize_quotes(text):
    """<<...>>, "..." -> «...» — подтверждённый домашний стандарт
    (test_fix_latex_junk.py:66: <<Ромашка>> -> «Ромашка» — починка, не порча)."""
    text = _ANGLE_QUOTE_RE.sub(r'«\1»', text)
    text = _STRAIGHT_QUOTE_RE.sub(r'«\1»', text)
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (35 tests total)

- [ ] **Step 5: Defect-testing pair #6 (dash/quote normalization)**

Temporarily comment out the `text = text.replace('---', '—')` line, rerun `test_triple_hyphen_to_em_dash` — confirm RED. Revert, confirm GREEN.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: normalize dashes and quotes to home standard

Defect-testing #6 (dash/quote normalization): confirmed RED commenting out
the '---' replacement then GREEN after revert."
```

---

## Task 9: Image detection (record, don't resolve)

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Produces: `find_images(text: str) -> list[dict]` — each dict is `{'original_ref': str, 'kind': str}`, `kind` in `{'markdown', 'includegraphics', 'url'}`. Text is returned unchanged by design (images are left visible in the text, not deleted — see Global Constraints).

- [ ] **Step 1: Write the failing tests**

```python
class FindImagesTests(SimpleTestCase):
    def test_finds_markdown_image(self):
        text = 'График: ![](https://s3.example/graph.png) выше.'
        images = find_images(text)
        self.assertEqual(images, [
            {'original_ref': 'https://s3.example/graph.png', 'kind': 'markdown'},
        ])

    def test_finds_includegraphics(self):
        text = '\\includegraphics{eq.png} показывает рост.'
        images = find_images(text)
        self.assertEqual(images, [{'original_ref': 'eq.png', 'kind': 'includegraphics'}])

    def test_finds_bare_url_not_already_matched(self):
        text = 'Смотри https://example.com/chart.jpg для деталей.'
        images = find_images(text)
        self.assertEqual(
            images, [{'original_ref': 'https://example.com/chart.jpg', 'kind': 'url'}],
        )

    def test_bare_url_inside_markdown_image_not_double_counted(self):
        text = '![](https://s3.example/graph.png)'
        images = find_images(text)
        self.assertEqual(len(images), 1)

    def test_no_images_returns_empty_list(self):
        self.assertEqual(find_images('Обычный текст без картинок.'), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
_MARKDOWN_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(([^)]*)\)')
_INCLUDEGRAPHICS_RE = re.compile(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}')
_BARE_URL_RE = re.compile(r'https?://\S+?(?=[)\s]|$)')


def find_images(text):
    """Найти markdown-картинки, \\includegraphics и голые URL картинок.
    НЕ резолвит и НЕ трогает текст — только фиксирует ссылку и вид
    (CORPUS-FORMAT.md §3: "не резолвить..., не терять и не удалять
    молча")."""
    images = []
    covered_spans = []

    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        images.append({'original_ref': match.group(1), 'kind': 'markdown'})
        covered_spans.append(match.span())

    for match in _INCLUDEGRAPHICS_RE.finditer(text):
        images.append({'original_ref': match.group(1), 'kind': 'includegraphics'})
        covered_spans.append(match.span())

    for match in _BARE_URL_RE.finditer(text):
        start, end = match.span()
        if any(cs <= start and end <= ce for cs, ce in covered_spans):
            continue
        images.append({'original_ref': match.group(0), 'kind': 'url'})

    return images
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (40 tests total)

- [ ] **Step 5: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: detect markdown/includegraphics/bare-url images, record only"
```

---

## Task 10: `convert_text_field` — orchestrate one field through the full pipeline

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Consumes: every function from Tasks 2–9.
- Produces: `convert_text_field(text: str) -> dict` — `{'text_md': str, 'images': list[dict], 'complex_table': bool, 'warnings': list[str]}`. This is the function `convert_problem` (Task 11) calls once per statement/answer/solution/part-statement.

- [ ] **Step 1: Write the failing tests**

```python
class ConvertTextFieldTests(SimpleTestCase):
    def test_empty_text_returns_empty_result(self):
        result = convert_text_field('')
        self.assertEqual(result, {
            'text_md': '', 'images': [], 'complex_table': False, 'warnings': [],
        })

    def test_full_pipeline_on_mixed_latex_text(self):
        text = (
            'Фирма \\textbf{"Ромашка"} максимизирует прибыль\\footnote{см. отчёт}.'
            '\\medskip\n'
            'Цена $P^*=10$ упала на 20\\%---сильно.\n'
            '\\begin{itemize}\\item Спрос\\item Предложение\\end{itemize}'
        )
        result = convert_text_field(text)
        self.assertIn('**«Ромашка»**', result['text_md'])
        self.assertIn('$P^*=10$', result['text_md'])
        self.assertIn('20\\%', result['text_md'])
        self.assertIn('—сильно', result['text_md'])
        self.assertIn('- Спрос', result['text_md'])
        self.assertIn('- Предложение', result['text_md'])
        self.assertIn('Примечание: см. отчёт', result['text_md'])
        self.assertNotIn('\\medskip', result['text_md'])
        self.assertNotIn('\\textbf', result['text_md'])
        self.assertFalse(result['complex_table'])

    def test_math_survives_full_pipeline_untouched(self):
        text = 'Оптимум $Q^*=20$ и $P^*=5$, индекс $x_1$ и $x_2$.'
        result = convert_text_field(text)
        self.assertIn('$Q^*=20$', result['text_md'])
        self.assertIn('$P^*=5$', result['text_md'])
        self.assertIn('$x_1$', result['text_md'])
        self.assertIn('$x_2$', result['text_md'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
def convert_text_field(text):
    """Один текстовый кусок (statement/answer/solution/criteria/часть
    подпункта) через весь конвейер, в порядке, обязательном по §2б/§3:

    1. TeX-комментарии — до всего остального (иначе '%' может съесть
       часть уже преобразованной разметки на следующих шагах);
    2. \\color/\\textcolor — до bold/italic (снимает обёртку, которая
       иначе помешала бы regex увидеть \\textbf изнутри);
    3. обернуть голые equation/align/gather — ДО защиты математики, чтобы
       новая обёртка $$ была защищена вместе со всем остальным;
    4. защитить математику плейсхолдерами — всё, что дальше, физически
       не видит формулу (значит не может её сломать);
    5. вынести сноски (текст сноски может содержать плейсхолдеры формул —
       восстановятся на шаге 8 вместе с остальным текстом);
    6. убрать junk-команды, картинки — зафиксировать, не трогая текст;
    7. bold/italic, списки, таблицы;
    8. вернуть математику на место;
    9. тире/кавычки — ПОСЛЕ восстановления математики (иначе одиночный
       '-' внутри плейсхолдера-числа мог бы попасться под замену);
    10. дописать сноски в конец.
    """
    if not text:
        return {'text_md': '', 'images': [], 'complex_table': False, 'warnings': []}

    warnings = []
    text = strip_tex_comments(text)
    text = strip_color(text)
    text = wrap_bare_environments(text)
    protected_text, protected = protect_math(text)
    protected_text, notes = extract_footnotes(protected_text)
    protected_text = strip_junk_commands(protected_text)
    images = find_images(protected_text)
    protected_text = convert_emphasis(protected_text)
    protected_text = convert_lists(protected_text)
    protected_text, complex_table = convert_tables(protected_text)
    if complex_table:
        warnings.append('сложная таблица (multicolumn/multirow) — в очередь на ручной разбор')
    restored = restore_math(protected_text, protected)
    restored = normalize_dashes(restored)
    restored = normalize_quotes(restored)
    restored = append_footnote_notes(restored, [restore_math(note, protected) for note in notes])

    return {
        'text_md': restored,
        'images': images,
        'complex_table': complex_table,
        'warnings': warnings,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (43 tests total)

- [ ] **Step 5: Cross-check against the real renderer (not a defect-testing pair, a sanity gate)**

Add one more test in the same file:

```python
class RendererRoundTripTests(SimpleTestCase):
    def test_converted_output_renders_without_crashing(self):
        from problems.rendering import render_markdown
        text = (
            '\\textbf{Фирма} максимизирует $\\pi = P \\cdot Q - C(Q)$.\n'
            '\\begin{itemize}\\item Спрос\\item Предложение\\end{itemize}'
        )
        result = convert_text_field(text)
        html = render_markdown(result['text_md'])
        self.assertIn('<strong>Фирма</strong>', html)
        self.assertIn('<li>Спрос</li>', html)
        self.assertIn('$\\pi = P \\cdot Q - C(Q)$', html)
```

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (44 tests total) — proves the converter's output is not just plausible-looking text, it is text the actual `rendering.py` (Task 2's dependency) turns into the expected HTML.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: convert_text_field orchestrates the full per-field pipeline

Includes a round-trip sanity test through the real problems.rendering.render_markdown."
```

---

## Task 11: `convert_problem` — whole-problem orchestration + subpoint detection

**Files:**
- Modify: `problems/corpus_converter/core.py`
- Test: `problems/tests/test_corpus_converter_core.py`

**Interfaces:**
- Consumes: `convert_text_field` (Task 10).
- Produces: `convert_problem(statement: str, answer: str = '', solution: str = '', existing_parts: list[tuple[str, str]] | None = None) -> dict` matching the brief's Phase 0 structure: `{'statement_md', 'parts', 'rubric', 'images', 'complex_table', 'warnings'}`. `rubric` stays `None` here — Task 12 (`criteria.py`) is the only producer of rubric candidates, called separately by the Школково command since ILE has no `criteria` field at all.

- [ ] **Step 1: Write the failing tests**

```python
class ConvertProblemTests(SimpleTestCase):
    def test_update_mode_uses_existing_parts_as_is(self):
        # ILE-подобный случай: подпункты уже в базе как ProblemPart, из
        # текста заново их вычленять не нужно и не следует.
        result = convert_problem(
            statement='Общее условие с \\textbf{данными}.',
            existing_parts=[('а', 'Найдите $Q$.'), ('б', 'Найдите $P$.')],
        )
        self.assertEqual(len(result['parts']), 2)
        self.assertEqual(result['parts'][0]['label'], 'а')
        self.assertIn('$Q$', result['parts'][0]['statement_md'])
        self.assertIn('**данными**', result['statement_md'])

    def test_insert_mode_detects_subpoints_from_raw_text(self):
        # Школково-подобный случай: подпункты живут внутри statement_tex
        # текстом, existing_parts не передан вовсе.
        text = 'Дано уравнение спроса.\nа) Найдите $Q$.\nб) Найдите $P$.'
        result = convert_problem(statement=text, existing_parts=None)
        self.assertEqual(len(result['parts']), 2)
        self.assertEqual(result['parts'][0]['label'], 'а')
        self.assertIn('Найдите $Q$', result['parts'][0]['statement_md'])
        self.assertIn('Дано уравнение спроса.', result['statement_md'])

    def test_insert_mode_no_subpoints_found_gives_empty_parts(self):
        result = convert_problem(statement='Обычная задача без пунктов.', existing_parts=None)
        self.assertEqual(result['parts'], [])

    def test_candidate_parts_always_have_answer_key(self):
        # ProblemPart.answer не blank=True — кандидат обязан нести ключ,
        # даже пустой, иначе будущий реальный импорт споткнётся.
        result = convert_problem(
            statement='Условие.\nа) Пункт без ответа в тексте.',
            existing_parts=None,
        )
        self.assertIn('answer', result['parts'][0])

    def test_images_and_complex_table_bubble_up_from_all_fields(self):
        result = convert_problem(
            statement='\\includegraphics{gr.png}',
            answer='',
            solution='\\begin{tabular}{|l|l|}\\multicolumn{2}{|c|}{X}\\end{tabular}',
        )
        self.assertEqual(result['images'], [{'original_ref': 'gr.png', 'kind': 'includegraphics'}])
        self.assertTrue(result['complex_table'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: FAIL — `ImportError: cannot import name 'convert_problem'`

- [ ] **Step 3: Write minimal implementation**

Append to `problems/corpus_converter/core.py`:

```python
#: а)/б)/в)... в начале строки — ЕДИНСТВЕННЫЙ доверенный маркер подпункта
#: в этом модуле (кириллический буквенный список с закрывающей скобкой).
#: Латинские a)/A) и другие конвенции атласа — вне пилота (только ILE и
#: Школково; у обоих в проверенных сэмплах кириллическая метка).
_SUBPOINT_RE = re.compile(r'(?m)^\s*([а-я])\)\s+')


def _detect_subpoints(text):
    """Разбить текст на (интро, [(метка, текст_пункта), ...]) по а)/б)/в).
    Без совпадений — (весь_текст, [])."""
    matches = list(_SUBPOINT_RE.finditer(text))
    if not matches:
        return text, []
    intro = text[:matches[0].start()].strip()
    parts = []
    for i, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((label, text[start:end].strip()))
    return intro, parts


def convert_problem(statement, answer='', solution='', existing_parts=None):
    """Вся задача (одно текстовое поле условия + опционально ответ/решение)
    через конвейер. Возвращает структуру Фазы 0 из брифа сессии.

    existing_parts=[(label, statement), ...] — режим UPDATE (ILE): части
    уже есть в базе как ProblemPart, из текста заново их не вычленяем,
    только прогоняем через convert_text_field как есть.

    existing_parts=None — режим INSERT (Школково): пытаемся найти
    а)/б)/в) внутри statement сами."""
    images = []
    warnings = []
    complex_table = False

    def _merge(field_result):
        nonlocal complex_table
        images.extend(field_result['images'])
        warnings.extend(field_result['warnings'])
        if field_result['complex_table']:
            complex_table = True
        return field_result['text_md']

    if existing_parts is not None:
        intro_text = statement
        raw_parts = existing_parts
    else:
        intro_text, raw_parts = _detect_subpoints(statement)

    statement_md = _merge(convert_text_field(intro_text))

    parts = []
    for label, part_statement in raw_parts:
        part_result = convert_text_field(part_statement)
        parts.append({
            'label': label,
            'statement_md': _merge(part_result),
            'answer': '',
        })

    if answer:
        _merge(convert_text_field(answer))
    if solution:
        _merge(convert_text_field(solution))

    return {
        'statement_md': statement_md,
        'parts': parts,
        'rubric': None,
        'images': images,
        'complex_table': complex_table,
        'warnings': warnings,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_core -v 2`
Expected: PASS (49 tests total)

- [ ] **Step 5: Commit**

```bash
git add problems/corpus_converter/core.py problems/tests/test_corpus_converter_core.py
git commit -m "corpus_converter: convert_problem orchestrates statement/parts/answer/solution

UPDATE mode (existing_parts given) leaves part structure as-is; INSERT mode
(existing_parts=None) detects а)/б)/в) subpoints from raw text."
```

---

## Task 12: Школково `criteria_tex` -> candidate `Rubric`

**Files:**
- Create: `problems/corpus_converter/criteria.py`
- Create: `problems/tests/test_corpus_converter_criteria.py`

**Interfaces:**
- Consumes: `problems.corpus_converter.core.convert_text_field` (to markdown-ify each criterion's description).
- Produces: `parse_shkolkovo_criteria(criteria_tex: str) -> dict` — `{'rubric_name': str, 'criteria': [{'name': str, 'max_points': float | None, 'description': str, 'order': int}], 'warnings': list[str]}`.

- [ ] **Step 1: Write the failing tests**

```python
# problems/tests/test_corpus_converter_criteria.py
from django.test import SimpleTestCase

from problems.corpus_converter.criteria import parse_shkolkovo_criteria


class ParseShkolkovoCriteriaTests(SimpleTestCase):
    def test_parses_itemize_blocks_per_part_with_points(self):
        text = (
            '\\textbf{(a)}\n'
            '\\begin{itemize}\n'
            '\\item 3 балла за верное определение картеля.\n'
            '\\item 1 балл за пример.\n'
            '\\end{itemize}\n'
            '\\textbf{(б)}\n'
            '\\begin{itemize}\n'
            '\\item 2 балла за формулу.\n'
            '\\end{itemize}'
        )
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(len(result['criteria']), 3)
        self.assertEqual(result['criteria'][0]['max_points'], 3.0)
        self.assertIn('верное определение картеля', result['criteria'][0]['description'])
        self.assertTrue(result['criteria'][0]['name'].startswith('(a)'))
        self.assertEqual(result['criteria'][2]['max_points'], 2.0)
        self.assertTrue(result['criteria'][2]['name'].startswith('(б)'))

    def test_orders_criteria_sequentially(self):
        text = (
            '\\textbf{(a)}\\begin{itemize}\\item 1 балл за X.\\item 2 балла за Y.\\end{itemize}'
        )
        result = parse_shkolkovo_criteria(text)
        self.assertEqual([c['order'] for c in result['criteria']], [0, 1])

    def test_no_points_found_warns_and_leaves_points_none(self):
        text = '\\textbf{(a)}\\begin{itemize}\\item за верный ответ без указания баллов.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertIsNone(result['criteria'][0]['max_points'])
        self.assertTrue(any('без баллов' in w for w in result['warnings']))

    def test_empty_criteria_tex_returns_empty(self):
        result = parse_shkolkovo_criteria('')
        self.assertEqual(result['criteria'], [])
        self.assertEqual(result['warnings'], [])

    def test_points_singular_and_plural_forms(self):
        text = '\\textbf{(a)}\\begin{itemize}\\item 1 балл за A.\\item 5 баллов за B.\\end{itemize}'
        result = parse_shkolkovo_criteria(text)
        self.assertEqual(result['criteria'][0]['max_points'], 1.0)
        self.assertEqual(result['criteria'][1]['max_points'], 5.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_criteria -v 2`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# problems/corpus_converter/criteria.py
# -*- coding: utf-8 -*-
"""Школково: criteria_tex (проза, структурированная по \\textbf{(метка)} +
\\begin{itemize}) -> кандидат Rubric/RubricCriterion.

Единственный источник банка со структурными критериями (CORPUS-FORMAT.md
§3: "маппинг в Rubric берётся даром" у 836 задач Школково) — но баллы
внутри каждого \\item всё равно нужно вытащить из русской прозы
("3 балла за ...", "1 балл за ..."), это и есть менее тривиальная часть,
явно выделенная спекой в отдельный файл."""
from __future__ import annotations

import re

from problems.corpus_converter.core import convert_text_field

_PART_BLOCK_RE = re.compile(
    r'\\textbf\{(\([^)]*\))\}\s*\\begin\{itemize\}(.*?)\\end\{itemize\}',
    re.DOTALL,
)
_ITEM_RE = re.compile(r'\\item\s*(.*?)(?=\\item|\Z)', re.DOTALL)
#: "3 балла за ..." / "1 балл за ..." / "5 баллов за ..." — число в начале
#: пункта, за которым следует слово "балл"/"балла"/"баллов".
_POINTS_RE = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*балл(?:а|ов)?\b')


def parse_shkolkovo_criteria(criteria_tex):
    """criteria_tex -> {'rubric_name', 'criteria': [...], 'warnings': [...]}."""
    if not criteria_tex:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    criteria = []
    warnings = []
    order = 0

    for block_match in _PART_BLOCK_RE.finditer(criteria_tex):
        label = block_match.group(1)
        body = block_match.group(2)
        for item_match in _ITEM_RE.finditer(body):
            raw_item = item_match.group(1).strip()
            if not raw_item:
                continue
            points_match = _POINTS_RE.match(raw_item)
            if points_match:
                max_points = float(points_match.group(1).replace(',', '.'))
            else:
                max_points = None
                warnings.append(f'критерий без баллов в прозе: {label} — {raw_item[:60]}')
            description = convert_text_field(raw_item)['text_md']
            criteria.append({
                'name': f'{label} {description}'.strip(),
                'max_points': max_points,
                'description': description,
                'order': order,
            })
            order += 1

    return {'rubric_name': 'Критерии оценивания', 'criteria': criteria, 'warnings': warnings}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_criteria -v 2`
Expected: PASS (5 tests)

- [ ] **Step 5: Defect-testing pair #7 (criteria points extraction — bonus beyond the required 6)**

Temporarily change `_POINTS_RE` to require `\d+\s*балла\b` only (drop the `(?:а|ов)?` alternation), rerun `test_points_singular_and_plural_forms` — confirm RED (fails to match "1 балл" / "5 баллов"). Revert, confirm GREEN.

- [ ] **Step 6: Commit**

```bash
git add problems/corpus_converter/criteria.py problems/tests/test_corpus_converter_criteria.py
git commit -m "corpus_converter: Школково criteria_tex -> candidate Rubric/RubricCriterion

Defect-testing #7 (criteria points extraction, bonus beyond required 6):
confirmed RED narrowing the point-word regex then GREEN after revert."
```

---

## Task 13: Report assembler

**Files:**
- Create: `problems/corpus_converter/report.py`
- Test: `problems/tests/test_corpus_converter_report.py`

**Interfaces:**
- Consumes: the dict shapes from `convert_problem`/`parse_shkolkovo_criteria`.
- Produces: `render_entry(problem_id, source_label, before: dict, after: dict, extra_note: str = '') -> str` (one "было → стало" Markdown block); `render_report(title: str, entries: list[str], warnings_summary: str) -> str` (assembles a full report.md body).

- [ ] **Step 1: Write the failing test**

```python
# problems/tests/test_corpus_converter_report.py
from django.test import SimpleTestCase

from problems.corpus_converter.report import render_entry, render_report


class RenderEntryTests(SimpleTestCase):
    def test_entry_has_before_after_and_id(self):
        entry = render_entry(
            problem_id=53709,
            source_label='ILE',
            before={'statement': '\\textbf{Старое}'},
            after={'statement_md': '**Старое**'},
        )
        self.assertIn('53709', entry)
        self.assertIn('ILE', entry)
        self.assertIn('\\textbf{Старое}', entry)
        self.assertIn('**Старое**', entry)


class RenderReportTests(SimpleTestCase):
    def test_report_includes_title_and_all_entries(self):
        report = render_report('Пилот конвертера', ['ENTRY_ONE', 'ENTRY_TWO'], 'сводка warnings')
        self.assertIn('Пилот конвертера', report)
        self.assertIn('ENTRY_ONE', report)
        self.assertIn('ENTRY_TWO', report)
        self.assertIn('сводка warnings', report)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_report -v 2`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# problems/corpus_converter/report.py
# -*- coding: utf-8 -*-
"""Общий сборщик отчёта «было -> стало» для команд corpus_pilot_ile и
corpus_pilot_shkolkovo — чтобы формат записи не разъезжался между двумя
командами."""
from __future__ import annotations


def render_entry(problem_id, source_label, before, after, extra_note=''):
    """Один блок отчёта: заголовок с id/источником, «было» (сырые поля из
    before), «стало» (converted-поля из after)."""
    lines = [f'### #{problem_id} — {source_label}', '']
    if extra_note:
        lines.append(f'_{extra_note}_')
        lines.append('')
    lines.append('**Было:**')
    lines.append('```')
    for key, value in before.items():
        lines.append(f'{key}: {value}')
    lines.append('```')
    lines.append('')
    lines.append('**Стало:**')
    lines.append('```')
    for key, value in after.items():
        lines.append(f'{key}: {value}')
    lines.append('```')
    lines.append('')
    return '\n'.join(lines)


def render_report(title, entries, warnings_summary):
    """Собрать полный report.md: заголовок, все записи, сводка warnings."""
    parts = [f'# {title}', '']
    parts.extend(entries)
    parts.append('## Warnings и сложные случаи')
    parts.append('')
    parts.append(warnings_summary)
    return '\n'.join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv313/Scripts/python.exe manage.py test problems.tests.test_corpus_converter_report -v 2`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add problems/corpus_converter/report.py problems/tests/test_corpus_converter_report.py
git commit -m "corpus_converter: shared before/after report entry assembler"
```

---

## Task 14: Phase 1 — `corpus_pilot_ile` management command

**Files:**
- Create: `problems/management/commands/corpus_pilot_ile.py`

**Interfaces:**
- Consumes: `problems.corpus_converter.core.convert_problem`, `problems.corpus_converter.report.render_entry`/`render_report`.
- Produces: `reports/corpus_converter_pilot/ile_report.md`, prints a summary (count processed, count with warnings, count with complex_table) to stdout. Writes NOTHING to the database.

- [ ] **Step 1: Write the command**

```python
# problems/management/commands/corpus_pilot_ile.py
# -*- coding: utf-8 -*-
"""Фаза 1 брифа corpus-converter-pilot: путь UPDATE на ILE.

READ-ONLY. Ни один Problem/ProblemPart не изменяется — только чтение и
генерация reports/corpus_converter_pilot/ile_report.md."""
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem

SAMPLE_SIZE = 30
MIN_APPROVED = 15
MIN_WITH_STRUCTURE = 10


class Command(BaseCommand):
    help = 'Фаза 1 (read-only): прогнать конвертер по всем ILE-задачам, собрать сэмпл на 30 в отчёт.'

    def handle(self, *args, **options):
        count_before = Problem.objects.count()

        qs = (
            Problem.objects.filter(source_references__source__name='ILE / iloveeconomics.ru')
            .exclude(source_references__source__name='Служебное: фикстуры рендерера (не публиковать)')
            .distinct()
            .prefetch_related('parts')
        )
        total = qs.count()
        self.stdout.write(f'ILE: {total} задач найдено.')

        processed = []
        warnings_total = []
        complex_table_ids = []

        for problem in qs.iterator():
            existing_parts = [(part.label, part.statement) for part in problem.parts.all()]
            result = convert_problem(
                statement=problem.statement,
                answer=problem.answer,
                solution=problem.solution,
                existing_parts=existing_parts or None,
            )
            processed.append((problem, result))
            warnings_total.extend(f'#{problem.id}: {w}' for w in result['warnings'])
            if result['complex_table']:
                complex_table_ids.append(problem.id)

        approved = [(p, r) for p, r in processed if p.human_review == Problem.HumanReview.APPROVED]
        with_structure = [
            (p, r) for p, r in processed
            if r['parts'] or r['images'] or r['complex_table']
        ]

        # dict, не set: result — обычный dict (незахешируемый), поэтому
        # дедуп идёт по problem.id, а не по хешу пары (problem, result).
        random.seed(20260826)
        sample = {}
        for item in (random.sample(approved, min(MIN_APPROVED, len(approved))) if approved else []):
            sample[item[0].id] = item
        remaining_structure = [item for item in with_structure if item[0].id not in sample]
        for item in (
            random.sample(remaining_structure, min(MIN_WITH_STRUCTURE, len(remaining_structure)))
            if remaining_structure else []
        ):
            sample[item[0].id] = item
        remaining_pool = [item for item in processed if item[0].id not in sample]
        if len(sample) < SAMPLE_SIZE and remaining_pool:
            for item in random.sample(remaining_pool, min(SAMPLE_SIZE - len(sample), len(remaining_pool))):
                sample[item[0].id] = item

        entries = []
        for problem, result in sorted(sample.values(), key=lambda item: item[0].id)[:SAMPLE_SIZE]:
            entries.append(render_entry(
                problem_id=problem.id,
                source_label=f'ILE (human_review={problem.human_review or "не смотрели"})',
                before={
                    'statement': problem.statement,
                    'answer': problem.answer,
                    'solution': problem.solution,
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'answer_md': result['answer_md'],
                    'solution_md': result['solution_md'],
                    'warnings': result['warnings'],
                },
            ))

        warnings_summary = (
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Сложных таблиц (в ручную очередь): {len(complex_table_ids)} — id: {complex_table_ids}\n'
        )
        report = render_report('Пилот конвертера — Фаза 1: ILE (UPDATE)', entries, warnings_summary)

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_pilot')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'ile_report.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)

        count_after = Problem.objects.count()
        assert count_before == count_after, (
            f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было {count_before}, стало {count_after}'
        )

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Обработано {len(processed)}, в отчёт {len(entries)}, '
            f'сложных таблиц {len(complex_table_ids)}, инвариант count() сошёлся ({count_before}). '
            f'Отчёт: {out_path}'
        ))
```

- [ ] **Step 2: Run it against the real dev database**

Run: `venv313/Scripts/python.exe manage.py corpus_pilot_ile`
Expected: exits 0, prints "Готово. Обработано 3978, ...", writes `reports/corpus_converter_pilot/ile_report.md`.

- [ ] **Step 3: Verify the numeric invariant held**

Run: `venv313/Scripts/python.exe manage.py shell -c "from problems.models import Problem; print(Problem.objects.count())"`
Expected: same number as before this task started (confirmed earlier in this plan: 31699 total including the 5 fixtures).

- [ ] **Step 4: Read the generated report and spot-check 3 entries by eye**

Read `reports/corpus_converter_pilot/ile_report.md`, confirm: `**textbf**` became `**bold**`, math (`$Q^*$`-style) is untouched, no `\medskip`/`\textbf` leaked into "Стало".

- [ ] **Step 5: Commit**

```bash
git add problems/management/commands/corpus_pilot_ile.py reports/corpus_converter_pilot/ile_report.md
git commit -m "corpus_converter: Phase 1 read-only ILE UPDATE-path report command"
```

---

## Task 15: Phase 2 — `corpus_pilot_shkolkovo` management command

**Files:**
- Create: `problems/management/commands/corpus_pilot_shkolkovo.py`

**Interfaces:**
- Consumes: `problems.corpus_converter.core.convert_problem`, `problems.corpus_converter.criteria.parse_shkolkovo_criteria`, `problems.corpus_converter.report.render_entry`/`render_report`.
- Produces: `reports/corpus_converter_pilot/shkolkovo_report.md`. Reads `weconomics-data/shkolkovo/problems/*.json` and `image_map.json` from disk (outside the repo — path resolved relative to the repo's parent, matching where Phase −1 recon found it: `C:/Users/shipu/weconomics-data/shkolkovo`). Writes NOTHING to the database.

- [ ] **Step 1: Write the command**

```python
# problems/management/commands/corpus_pilot_shkolkovo.py
# -*- coding: utf-8 -*-
"""Фаза 2 брифа corpus-converter-pilot: путь INSERT на Школково.

READ-ONLY. Ничего не создаётся в базе — только чтение с диска и генерация
reports/corpus_converter_pilot/shkolkovo_report.md."""
import glob
import hashlib
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.criteria import parse_shkolkovo_criteria
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem, ProblemPart, Rubric, FileAsset

SAMPLE_SIZE = 30
#: Путь вне репозитория, найден в Фазе -1 (2026-08-26): соседняя папка
#: относительно корня qls, НЕ внутри репозитория — не трогать/не двигать.
SHKOLKOVO_DIR = os.path.join(
    os.path.dirname(settings.BASE_DIR), 'weconomics-data', 'shkolkovo',
)


def _load_problems():
    problems_dir = os.path.join(SHKOLKOVO_DIR, 'problems')
    for path in sorted(glob.glob(os.path.join(problems_dir, '*.json'))):
        with open(path, encoding='utf-8') as f:
            yield json.load(f)


class Command(BaseCommand):
    help = 'Фаза 2 (read-only): прогнать конвертер по Школково с диска, кандидаты в отчёт.'

    def handle(self, *args, **options):
        counts_before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )

        candidates = []
        dup_ids = []
        warnings_total = []
        complex_table_count = 0

        for raw in _load_problems():
            statement_tex = raw.get('statement_tex') or ''
            if not statement_tex:
                continue
            result = convert_problem(
                statement=statement_tex,
                answer=raw.get('answer_tex') or '',
                solution=raw.get('solution_tex') or '',
                existing_parts=None,
            )
            criteria_result = parse_shkolkovo_criteria(raw.get('criteria_tex') or '')

            content_hash = hashlib.md5(statement_tex.encode('utf-8')).hexdigest()
            is_dup = content_hash in existing_hashes
            if is_dup:
                dup_ids.append(raw['Id'])

            warnings_total.extend(f"{raw['Id']}: {w}" for w in result['warnings'])
            warnings_total.extend(f"{raw['Id']}: {w}" for w in criteria_result['warnings'])
            if result['complex_table']:
                complex_table_count += 1

            candidates.append((raw, result, criteria_result, is_dup))

        with_criteria = [c for c in candidates if c[2]['criteria']]
        with_images = [c for c in candidates if c[1]['images']]
        with_tables = [c for c in candidates if c[1]['complex_table']]
        rest = candidates

        random.seed(20260826)
        sample = []
        for bucket, n in ((with_criteria, 8), (with_images, 8), (with_tables, 6)):
            picks = random.sample(bucket, min(n, len(bucket))) if bucket else []
            for pick in picks:
                if pick not in sample:
                    sample.append(pick)
        remaining = [c for c in rest if c not in sample]
        if len(sample) < SAMPLE_SIZE and remaining:
            sample.extend(random.sample(remaining, min(SAMPLE_SIZE - len(sample), len(remaining))))

        entries = []
        for raw, result, criteria_result, is_dup in sample[:SAMPLE_SIZE]:
            entries.append(render_entry(
                problem_id=raw['Id'],
                source_label='Школково (кандидат, НЕ в базе)',
                before={
                    'statement_tex': raw.get('statement_tex', ''),
                    'answer_tex': raw.get('answer_tex', ''),
                    'solution_tex': raw.get('solution_tex', ''),
                    'criteria_tex': raw.get('criteria_tex', ''),
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'answer_md': result['answer_md'],
                    'solution_md': result['solution_md'],
                    'rubric_criteria': criteria_result['criteria'],
                    'images': result['images'],
                    'warnings': result['warnings'] + criteria_result['warnings'],
                },
                extra_note='ТОЧНОЕ совпадение content_hash с банком — вероятный дубль' if is_dup else '',
            ))

        warnings_summary = (
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Сложных таблиц (в ручную очередь): {complex_table_count}\n'
            f'Точных дублей по content_hash с банком (грубая проверка, полный дедуп — '
            f'работа следующей сессии): {len(dup_ids)} — id: {dup_ids[:50]}'
            + ('...' if len(dup_ids) > 50 else '')
        )
        report = render_report('Пилот конвертера — Фаза 2: Школково (INSERT)', entries, warnings_summary)

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_pilot')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'shkolkovo_report.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)

        counts_after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }
        assert counts_before == counts_after, (
            f'ИНВАРИАНТ НАРУШЕН: было {counts_before}, стало {counts_after}'
        )

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Прочитано {len(candidates)} с диска, в отчёт {len(entries)}, '
            f'вероятных дублей {len(dup_ids)}, сложных таблиц {complex_table_count}, '
            f'инвариант счётчиков сошёлся. Отчёт: {out_path}'
        ))
```

- [ ] **Step 2: Run it against the disk corpus**

Run: `venv313/Scripts/python.exe manage.py corpus_pilot_shkolkovo`
Expected: exits 0, prints "Готово. Прочитано 3414 ...", writes `reports/corpus_converter_pilot/shkolkovo_report.md`.

- [ ] **Step 3: Verify the numeric invariant held**

Run: `venv313/Scripts/python.exe manage.py shell -c "from problems.models import Problem, ProblemPart, Rubric, FileAsset; print(Problem.objects.count(), ProblemPart.objects.count(), Rubric.objects.count(), FileAsset.objects.count())"`
Expected: identical to the Task 15 Step 1 "before" snapshot (`31699 63100 0 0`).

- [ ] **Step 4: Read the generated report and spot-check 3 entries by eye**

Read `reports/corpus_converter_pilot/shkolkovo_report.md` — confirm: bare `equation`/`align`/`gather` got a `$$` wrapper, `criteria_tex` blocks turned into `rubric_criteria` with numeric `max_points` where the prose had a "N балл(а/ов)" prefix, images list non-empty for entries that had `\includegraphics`.

- [ ] **Step 5: Commit**

```bash
git add problems/management/commands/corpus_pilot_shkolkovo.py reports/corpus_converter_pilot/shkolkovo_report.md
git commit -m "corpus_converter: Phase 2 read-only Школково INSERT-path report command"
```

---

## Task 16: Assemble the final combined report for Макар

**Files:**
- Create: `reports/corpus_converter_pilot/report.md` (hand-assembled from the two generated reports plus a short cover section — this is the one file the brief asks Макар to read).

**Interfaces:**
- Consumes: `reports/corpus_converter_pilot/ile_report.md`, `reports/corpus_converter_pilot/shkolkovo_report.md` (both generated by Tasks 14–15).

- [ ] **Step 1: Write the cover section by hand**

Prepend to a new `reports/corpus_converter_pilot/report.md`:

```markdown
# Пилот общего конвертера корпуса — отчёт для Макара

Читать этот файл. `ile_report.md` и `shkolkovo_report.md` в этой же папке —
машинный вывод команд `corpus_pilot_ile`/`corpus_pilot_shkolkovo`, полные
данные позади сэмпла ниже.

**Что построено:** `problems/corpus_converter/` — один общий модуль
(core.py + criteria.py), 49+5+2 = 56 unit-тестов, из них 7
defect-testing пар (планка была 6). Две read-only команды.

**Числовой инвариант — подтверждено кодом, не только текстом:** обе
команды сами проверяют `assert` на `Problem.objects.count()` (и
`ProblemPart`/`Rubric`/`FileAsset` во второй) до/после и падают, если
инвариант нарушен. Обе завершились успешно — см. вывод в Task 14/15 этого
плана.

**Ни одна боевая запись не создана и не изменена.** Ни `.save()`, ни
`.create()`, ни `.update()` не вызываются нигде в
`problems/corpus_converter/` и в обеих командах — это проверяется
буквальным отсутствием этих вызовов в диффе, не только по итогу.

[Здесь Task 16 Step 2 подставляет реальные числа из вывода команд.]

## ILE (Фаза 1, UPDATE) — 30 примеров

(см. ile_report.md для полного текста; сюда — ссылка + сводка warnings)

## Школково (Фаза 2, INSERT) — 30 примеров

(см. shkolkovo_report.md для полного текста; сюда — ссылка + сводка warnings +
таблица дублей)

## Warnings и сложные случаи — что делать руками

[Число сложных таблиц, число задач без баллов в criteria, число вероятных
дублей — с рекомендацией: смотреть глазами, не автоматизировать в этой сессии.]
```

- [ ] **Step 2: Fill in the real numbers**

Open `reports/corpus_converter_pilot/ile_report.md` and `shkolkovo_report.md`, copy their actual summary lines (processed count, warnings count, complex-table count, duplicate count) into the placeholders in Step 1's draft. Replace bracketed placeholder paragraphs with real prose citing those numbers.

- [ ] **Step 3: Commit**

```bash
git add reports/corpus_converter_pilot/report.md
git commit -m "corpus_converter: assemble combined pilot report for owner review"
```

---

## Task 17: Final verification (CLAUDE.md's five CI jobs + visual n/a)

**Files:** none (verification only).

- [ ] **Step 1: lint**

```bash
ruff check .
```

Expected: 0 findings (or only pre-existing ones unrelated to this branch — compare against `git stash`/`main` if anything shows up).

- [ ] **Step 2: security**

```bash
bandit -r problems catalog teacher student game calc2 config -ll
pip-audit -r requirements/base.txt
```

Expected: no new findings introduced by `problems/corpus_converter/` (regex-only module, no `eval`/`exec`/shell/`pickle`).

- [ ] **Step 3: migrations**

```bash
venv313/Scripts/python.exe manage.py migrate --noinput --settings=config.settings_test_pg
venv313/Scripts/python.exe manage.py makemigrations --check --dry-run --settings=config.settings_test_pg
```

Expected: clean — this plan adds no model fields, so `makemigrations --check` must report nothing to create.

- [ ] **Step 4: tests — full run, two-step, per CLAUDE.md**

```bash
venv313/Scripts/python.exe scripts/run_tests.py problems catalog teacher student calc2 game calendar_stub config --settings=config.settings_test_pg --verbosity 2
```

Expected: PASS, ~2724 + 8 serial as documented in CLAUDE.md, plus the ~56 new tests from this plan. Do not interrupt — budget ~25 minutes.

- [ ] **Step 5: deploy-check**

```bash
venv313/Scripts/python.exe manage.py check --deploy --fail-level WARNING
```

Expected: no new warnings (this plan ships no settings changes).

- [ ] **Step 6: manage.py check + makemigrations --check on the default dev DB too**

```bash
venv313/Scripts/python.exe manage.py check
venv313/Scripts/python.exe manage.py makemigrations --check --dry-run
```

Expected: both clean.

- [ ] **Step 7: Report every job's status by name** in the final message to the user — per CLAUDE.md's explicit warning that "полный прогон зелёный" reported without naming all five jobs has caused a real incident before (24.08, security job red for four sessions unnoticed).

- [ ] **Step 8: Commit if any lint/format fixes were needed**

```bash
git add -A
git commit -m "corpus_converter: fix lint findings from full CI verification"
```

(Skip this step entirely if Steps 1–6 were clean — no empty commit.)

---

## Task 18: Notion write-up (per CLAUDE.md session protocol)

**Files:** none (Notion only).

- [ ] **Step 1: Add a "Результаты" card**

Content: what was built (`problems/corpus_converter/`, two read-only commands, 56 tests incl. 7 defect-testing pairs), the real processed/warnings/duplicate numbers from Tasks 14–15, where the report lives (`reports/corpus_converter_pilot/report.md`), branch name (`feat/corpus-converter-pilot`, not pushed/merged), confirmation that 0 database rows were touched.

- [ ] **Step 2: Do NOT create a "Решения" card**

Per the brief: scaling to the other 6 sources is a decision Макар makes after reading the report — not this session's decision to record.

- [ ] **Step 3: Leave "Трек 2: конвертеры под новый рендерер" status as "Надо"**

It's not done — this was a pilot on 2 of 8 needed converters (ILE + Школково), explicitly not a full rollout. Add a comment/note on the card pointing at the new report, but don't move its status to "Готово".
