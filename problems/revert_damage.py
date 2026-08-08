"""Шлюз «не навреди» для уже применённых откатов Батча 2.

Зачем. 21 июля свип откатил 1 762 поля по признаку подмены цифр/знаков, исходя
из допущения «откат к авторскому тексту безопасен по построению». Решение
Notion 3abb11c92bc1814ba792d754a6095108 это допущение отменило: авторский текст
часто ХУЖЕ починенного — откат возвращает в каталог нерендерящиеся таблицы,
ошибки KaTeX, потерянные слеши и утёкшие решения. Здесь — измеритель того, что
натворил уже применённый откат. НИЧЕГО НЕ ЧИНИТ, только считает.

Семь признаков ухудшения (ДО отката = post-Sonnet, ПОСЛЕ = текущая база):
  1. bare_table_markup  — появились голые \\hline / & / \\\\ вне математики;
  2. raw_latex_noslash  — появились сырые LaTeX-команды без ведущего слеша;
  3. shrunk_15          — видимый текст стал короче более чем на 15%;
  4. bad_start          — поле стало начинаться не с начала слова/предложения;
  5. collapsed_to_stub  — поле стало короче 60 символов, хотя было абзацем;
  6. lost_list_header   — исчезла строка-заголовок перечня;
  7. katex_errors_up    — выросло число ошибок KaTeX (считается рендером, не здесь);
  8. katex_red_macro_up — появилась КРАСНАЯ неизвестная команда внутри
     разобравшейся формулы (\tesxt, \myarray): узла .katex-error KaTeX
     при этом НЕ создаёт, поэтому признак 7 к ней слеп. Считается тем же
     рендером (scripts/katex_damage.js).

Признаки 1–6 текстовые и считаются без браузера — они же служат ПРЕДФИЛЬТРОМ
для дорогого признака 7. Слепоту предфильтра проверяет контрольная выборка
неотмеченных полей (см. команду batch2_revert_damage_audit).
"""

import re
from typing import Dict, List

from problems.management.commands.glue_pdf_lines import build_shadow

# ── 1. Голая табличная разметка вне математики ──────────────────────────────
# \hline, & и \\ — разметка LaTeX-таблиц. Внутри $…$/\begin{array}… это норма
# (KaTeX их рисует), а вне математики ученик видит их сырым текстом. Считаем
# по «тени» (build_shadow заменяет всю математику на U+E000), поэтому
# содержимое формул в счёт не идёт ни при каких условиях.
_BARE_TABLE_RE = re.compile(r'\\hline|(?<!\\)&|\\\\')

# ── 2. Сырые LaTeX-команды без ведущего слеша ───────────────────────────────
# Классический след потерянного при чистке обратного слеша: «textbf{...}»,
# «begin{array}». Требуем следом { или пробел+{, иначе английское слово
# «begin» в обычном тексте давало бы ложное срабатывание.
_NOSLASH_CMDS = ('textbf', 'textit', 'begin', 'end', 'frac', 'hline',
                 'mathrm', 'text', 'left', 'right', 'includegraphics')
_RAW_LATEX_RE = re.compile(
    r'(?<![\\A-Za-z])(?:' + '|'.join(_NOSLASH_CMDS) + r')\s*\{')

# ── 3. Видимый текст ────────────────────────────────────────────────────────
# То, что реально видит ученик: без служебных команд и разделителей формул.
_CMD_RE = re.compile(r'\\[A-Za-z]+\*?')
_DELIM_RE = re.compile(r'\$\$|\$|\\\(|\\\)|\\\[|\\\]')
_BRACES_RE = re.compile(r'[{}]')
_WS_RE = re.compile(r'\s+')

# ── 4. Начало поля ──────────────────────────────────────────────────────────
# Обрезанное начало выдаёт себя строчной буквой или «продолжающей» пунктуацией
# в первой позиции. Маркер списка («а)», «1.», «•») началом НЕ считается —
# подпункты законно так и начинаются.
_LIST_START_RE = re.compile(r'^\s*(?:[•‣▪◦*–—-]|\(?[а-яa-z0-9]{1,3}[).]\s)')
_CONTINUATION_START = ',;:.)]}»”…!?%'

# ── 6. Строка-заголовок перечня ─────────────────────────────────────────────
_LIST_HEADER_RE = re.compile(
    r'^[ \t]*(?:варианты\s+ответа|варианты|вопросы|вопрос|ответы|'
    r'выберите|укажите\s+верные|задания|пункты)\s*:',
    re.IGNORECASE | re.MULTILINE)

# Порог «поле было полноценным абзацем» для признака 5. Ниже него короткое
# ПОСЛЕ не улика: подпункт «а) 5 руб.» законно короток и в ДО, и в ПОСЛЕ.
PARAGRAPH_MIN = 150
STUB_MAX = 60
SHRINK_LIMIT = 0.15


def visible_text(text: str) -> str:
    """Приближение видимого ученику текста: без команд, скобок и разделителей."""
    t = _DELIM_RE.sub(' ', text or '')
    t = _CMD_RE.sub(' ', t)
    t = _BRACES_RE.sub(' ', t)
    return _WS_RE.sub(' ', t).strip()


def _outside_math(text: str) -> str:
    shadow, _ = build_shadow(text or '')
    return shadow


def _starts_badly(text: str) -> bool:
    stripped = (text or '').lstrip()
    if not stripped:
        return False
    if _LIST_START_RE.match(stripped):
        return False
    first = stripped[0]
    if first in _CONTINUATION_START:
        return True
    # Строчная кириллица/латиница в самом начале — обрубленное начало фразы.
    return first.isalpha() and first.islower()


def compare_field(old_text: str, new_text: str) -> List[str]:
    """Шесть текстовых признаков ухудшения при переходе ДО → ПОСЛЕ.

    old_text — состояние ДО отката (post-Sonnet), new_text — текущее в базе.
    Возвращает список сработавших признаков (пустой = ухудшений не видно).
    """
    old_text = old_text or ''
    new_text = new_text or ''
    flags = []

    old_bare = _outside_math(old_text)
    new_bare = _outside_math(new_text)
    if len(_BARE_TABLE_RE.findall(new_bare)) > len(_BARE_TABLE_RE.findall(old_bare)):
        flags.append('bare_table_markup')

    if len(_RAW_LATEX_RE.findall(new_text)) > len(_RAW_LATEX_RE.findall(old_text)):
        flags.append('raw_latex_noslash')

    old_vis, new_vis = visible_text(old_text), visible_text(new_text)
    if old_vis and len(new_vis) < len(old_vis) * (1 - SHRINK_LIMIT):
        flags.append('shrunk_15')

    if _starts_badly(new_text) and not _starts_badly(old_text):
        flags.append('bad_start')

    if len(new_text.strip()) < STUB_MAX and len(old_text.strip()) >= PARAGRAPH_MIN:
        flags.append('collapsed_to_stub')

    if _LIST_HEADER_RE.search(old_text) and not _LIST_HEADER_RE.search(new_text):
        flags.append('lost_list_header')

    return flags


def flag_labels() -> Dict[str, str]:
    return {
        'bare_table_markup': 'голая табличная разметка (\\hline, &, \\\\) вне математики',
        'raw_latex_noslash': 'сырая LaTeX-команда без ведущего слеша',
        'shrunk_15': 'видимый текст короче более чем на 15%',
        'bad_start': 'поле начинается не с начала слова/предложения',
        'collapsed_to_stub': 'абзац схлопнулся короче 60 символов',
        'lost_list_header': 'исчезла строка-заголовок перечня',
        'katex_errors_up': 'выросло число ошибок KaTeX',
        'katex_red_macro_up': 'появилась красная неизвестная команда (.katex-error её НЕ создаёт)',
    }
