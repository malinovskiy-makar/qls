"""
Уточнённый аудит мусора. Только чтение.

Исправления относительно detect_dirty_text:
  - truncated: двоеточие в конце считается обрывом ТОЛЬКО если нет ProblemPart.
  - Маркеры заголовков разбиты на категории:
      (а) echo_stub   — заголовок = обрубок начала условия (первые ~60 символов)
      (б) raw_latex   — содержит $, \\команду, ^, _, {, }
      (в) tail_stub   — кончается запятой, двоеточием или зависшим словом
      (г) junk        — пустой / прочерк / «Разное N»
      (д) other       — прочие (вероятная ложная тревога)

Выходные файлы (reports/dirty_text_audit/):
  refined_summary.md
  ids_echo_stub.txt
  ids_raw_latex.txt
  ids_tail_stub.txt
  ids_junk_title.txt
  ids_truncated_real.txt    — обрыв без подпунктов
  ids_footnote.txt
  ids_pseudo_quotes.txt
  ids_bare_latex_cmds.txt
  ids_unpaired_dollars.txt
  ids_latex_comment.txt
"""
from typing import Dict, List, Optional, Set, Tuple
import os
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from problems.models import Problem

REPORT_DIR = "reports/dirty_text_audit"

_HANGING_WORDS = frozenset({
    'и', 'или', 'а', 'но', 'да', 'же', 'то', 'бы', 'ли',
    'в', 'на', 'по', 'с', 'из', 'от', 'до', 'к', 'у', 'о', 'об',
    'за', 'при', 'без', 'для', 'над', 'под', 'про', 'через',
    'что', 'как', 'если', 'хотя', 'чтобы', 'когда', 'где',
})

_RU_VOWELS = frozenset('аеёиоуыьъэюяАЕЁИОУЫЬЪЭЮЯ')

_MATH_RE = re.compile(
    r'\$\$[\s\S]{0,3000}?\$\$'
    r'|\$[^\$\n]{0,400}?\$'
    r'|\\\([\s\S]{0,800}?\\\)'
    r'|\\\[[\s\S]{0,3000}?\\\]'
    r'|\\begin\{(?:equation|align|aligned|cases|gather|gathered|multline|array|tabular)\*?\}'
      r'[\s\S]{0,5000}?'
     r'\\end\{(?:equation|align|aligned|cases|gather|gathered|multline|array|tabular)\*?\}'
)

_BARE_CMDS_RE = re.compile(
    r'\\emph\{'
    r'|\\textbf\{'
    r'|\\textit\{'
    r'|\\underline\{'
    r'|\\text\{'
    r'|\\rule\{'
    r'|\\hline\b'
    r'|\\item\b'
    r'|\\begin\{enumerate\}'
    r'|\\begin\{itemize\}'
)

_TITLE_LATEX_RE = re.compile(r'\\\(|\\\)|\\frac\b|\\sqrt\b|\^|_\{|\$|\{|}')


def _strip_math(text):
    # type: (str) -> str
    return _MATH_RE.sub(lambda m: ' ' * len(m.group()), text)


def _norm(s):
    # type: (str) -> str
    return re.sub(r'\s+', ' ', (s or '')).strip()


# ── Маркеры условий ───────────────────────────────────────────────────────────

def has_footnote(text):
    # type: (str) -> bool
    return bool(re.search(r'\\footnote\{', text))


def has_latex_comment(text):
    # type: (str) -> bool
    return bool(re.search(r'(?m)^\s*%', text)) or bool(re.search(r'\}%\S', text))


def has_pseudo_quotes(text):
    # type: (str) -> bool
    stripped = _strip_math(text)
    return bool(re.search(r'<<|>>', stripped))


def has_bare_latex_cmds(text):
    # type: (str) -> bool
    stripped = _strip_math(text)
    return bool(_BARE_CMDS_RE.search(stripped))


def has_unpaired_dollars(text):
    # type: (str) -> bool
    cleaned = re.sub(r'\$\$', '\x00\x00', text)
    return cleaned.count('$') % 2 == 1


def is_truncated(text, has_parts):
    # type: (str, bool) -> bool
    """Обрыв условия. Двоеточие в конце — обрыв только без подпунктов."""
    t = text.rstrip()
    if not t:
        return False
    if t[-1] == ',':
        return True
    if t[-1] == ':' and not has_parts:
        return True
    m = re.search(r'\b([а-яёА-ЯЁ]{1,6})\s*$', t, re.UNICODE)
    if m and m.group(1).lower() in _HANGING_WORDS:
        return True
    m = re.search(r'([а-яёА-ЯЁ]{4,})[^\w]*$', t, re.UNICODE)
    if m and not any(c in _RU_VOWELS for c in m.group(1)):
        return True
    return False


def has_forum_traces(text):
    # type: (str) -> bool
    return bool(re.search(
        r'помогите|подскажите|не уверен|спасибо заранее',
        text, re.IGNORECASE | re.UNICODE))


def has_spam_links(text):
    # type: (str) -> bool
    return bool(re.search(
        r'версия для печати|войдите или|t\.me/|vk\.com/',
        text, re.IGNORECASE | re.UNICODE))


# ── Категории заголовков ──────────────────────────────────────────────────────

def classify_title(title, statement):
    # type: (str, str) -> Optional[str]
    """Возвращает категорию или None если заголовок чистый."""
    t = (title or '').strip()
    s = statement or ''

    # (г) junk — пустой, прочерк, «Разное N»
    if not t or t in ('—', '-', '–', '−'):
        return 'junk'
    if re.match(r'^Разное\s*\d*$', t, re.UNICODE):
        return 'junk'

    # (а) echo_stub — совпадает с началом условия (первые 60 символов)
    t60 = _norm(t)[:60]
    s60 = _norm(s)[:60]
    if t60 and s60 and s60.startswith(t60):
        return 'echo_stub'

    # (б) raw_latex — содержит LaTeX
    if _TITLE_LATEX_RE.search(t):
        return 'raw_latex'

    # (в) tail_stub — кончается запятой, двоеточием или зависшим словом
    if t[-1] in (',', ':'):
        return 'tail_stub'
    m = re.search(r'\b([а-яёА-ЯЁ]{1,7})\s*$', t, re.UNICODE)
    if m and m.group(1).lower() in _HANGING_WORDS:
        return 'tail_stub'

    return None  # чистый заголовок


class Command(BaseCommand):
    help = 'Уточнённый аудит мусора. Только чтение. Создаёт refined_summary.md и txt-списки id.'

    def handle(self, *args, **opts):
        os.makedirs(REPORT_DIR, exist_ok=True)

        self.stdout.write('Загружаем published-задачи с подпунктами...')
        qs = (Problem.objects
              .filter(status='published')
              .prefetch_related('parts')
              .order_by('id'))
        total_pub = qs.count()
        self.stdout.write('  published: {:,}'.format(total_pub))

        # Наборы id по категориям
        ids_echo_stub = set()       # type: Set[int]
        ids_raw_latex = set()       # type: Set[int]
        ids_tail_stub = set()       # type: Set[int]
        ids_junk = set()            # type: Set[int]
        ids_truncated = set()       # type: Set[int]
        ids_footnote = set()        # type: Set[int]
        ids_pseudo_quotes = set()   # type: Set[int]
        ids_bare_latex = set()      # type: Set[int]
        ids_unpaired = set()        # type: Set[int]
        ids_latex_comment = set()   # type: Set[int]
        ids_forum = set()           # type: Set[int]
        ids_spam = set()            # type: Set[int]

        problems_with_any = 0

        for p in qs:
            pid = p.id
            title = p.title or ''
            stmt = p.statement or ''
            has_parts = p.parts.all().exists()
            triggered = False

            # Проверяем statement + подпункты
            texts = [stmt]
            for part in p.parts.all():
                ps = (part.statement or '').strip()
                if ps:
                    texts.append(ps)

            for text in texts:
                if has_footnote(text):
                    ids_footnote.add(pid); triggered = True
                if has_latex_comment(text):
                    ids_latex_comment.add(pid); triggered = True
                if has_pseudo_quotes(text):
                    ids_pseudo_quotes.add(pid); triggered = True
                if has_bare_latex_cmds(text):
                    ids_bare_latex.add(pid); triggered = True
                if has_unpaired_dollars(text):
                    ids_unpaired.add(pid); triggered = True
                if has_forum_traces(text):
                    ids_forum.add(pid); triggered = True
                if has_spam_links(text):
                    ids_spam.add(pid); triggered = True

            # truncated — только главное условие, учитывая подпункты
            if is_truncated(stmt, has_parts):
                ids_truncated.add(pid); triggered = True

            # Заголовок
            cat = classify_title(title, stmt)
            if cat == 'echo_stub':
                ids_echo_stub.add(pid); triggered = True
            elif cat == 'raw_latex':
                ids_raw_latex.add(pid); triggered = True
            elif cat == 'tail_stub':
                ids_tail_stub.add(pid); triggered = True
            elif cat == 'junk':
                ids_junk.add(pid); triggered = True

            if triggered:
                problems_with_any += 1

        # ── Сводка в консоль ─────────────────────────────────────────────────
        W = 64
        self.stdout.write('')
        self.stdout.write('=' * W)

        def _row(label, ids_set):
            # type: (str, Set[int]) -> None
            cnt = len(ids_set)
            pct = 100.0 * cnt / total_pub if total_pub else 0
            self.stdout.write('{:<34} {:>7,}  {:>5.1f}%'.format(label, cnt, pct))

        self.stdout.write('МАРКЕРЫ УСЛОВИЙ')
        _row('footnote (\\footnote{)', ids_footnote)
        _row('latex_comment (% в начале строки)', ids_latex_comment)
        _row('pseudo_quotes (<< или >>)', ids_pseudo_quotes)
        _row('bare_latex_cmds (\\emph, \\item и т.д.)', ids_bare_latex)
        _row('unpaired_dollars (нечётное $)', ids_unpaired)
        _row('truncated (обрыв, БЕЗ подпунктов)', ids_truncated)
        _row('forum_traces (помогите/подскажите)', ids_forum)
        _row('spam_links (t.me/, vk.com/ и т.п.)', ids_spam)

        self.stdout.write('')
        self.stdout.write('КАТЕГОРИИ ЗАГОЛОВКОВ')
        _row('(а) echo_stub (заголовок = начало условия)', ids_echo_stub)
        _row('(б) raw_latex (LaTeX в заголовке)', ids_raw_latex)
        _row('(в) tail_stub (обрубок по хвосту)', ids_tail_stub)
        _row('(г) junk (пусто/прочерк/Разное N)', ids_junk)

        all_title_bad = ids_echo_stub | ids_raw_latex | ids_tail_stub | ids_junk
        self.stdout.write('')
        _row('Итого заголовки (а+б+в+г)', all_title_bad)

        pct_any = 100.0 * problems_with_any / total_pub if total_pub else 0
        self.stdout.write('=' * W)
        self.stdout.write(
            'Всего published с хотя бы одним маркером: {:,} ({:.1f}%)'.format(
                problems_with_any, pct_any))
        self.stdout.write('')

        # ── Записываем txt-списки id ─────────────────────────────────────────
        def _save_ids(filename, ids_set):
            # type: (str, Set[int]) -> None
            path = os.path.join(REPORT_DIR, filename)
            with open(path, 'w', encoding='utf-8') as f:
                for pid in sorted(ids_set):
                    f.write('{}\n'.format(pid))
            self.stdout.write('  {} → {:,} id'.format(filename, len(ids_set)))

        self.stdout.write('Записываем txt-списки id...')
        _save_ids('ids_echo_stub.txt', ids_echo_stub)
        _save_ids('ids_raw_latex_title.txt', ids_raw_latex)
        _save_ids('ids_tail_stub.txt', ids_tail_stub)
        _save_ids('ids_junk_title.txt', ids_junk)
        _save_ids('ids_truncated_real.txt', ids_truncated)
        _save_ids('ids_footnote.txt', ids_footnote)
        _save_ids('ids_pseudo_quotes.txt', ids_pseudo_quotes)
        _save_ids('ids_bare_latex_cmds.txt', ids_bare_latex)
        _save_ids('ids_unpaired_dollars.txt', ids_unpaired)
        _save_ids('ids_latex_comment.txt', ids_latex_comment)

        # ── Markdown-отчёт ───────────────────────────────────────────────────
        pct = lambda s: 100.0 * len(s) / total_pub if total_pub else 0
        md = [
            '# Уточнённый аудит мусора в published-задачах',
            '',
            'Всего published: {:,}'.format(total_pub),
            'С хотя бы одним маркером: **{:,}** ({:.1f}%)'.format(
                problems_with_any, pct_any),
            '',
            '## Маркеры условий (statement + подпункты)',
            '',
            '| Маркер | Задач | % |',
            '|---|---:|---:|',
            '| footnote | {:,} | {:.1f}% |'.format(len(ids_footnote), pct(ids_footnote)),
            '| latex_comment | {:,} | {:.1f}% |'.format(len(ids_latex_comment), pct(ids_latex_comment)),
            '| pseudo_quotes | {:,} | {:.1f}% |'.format(len(ids_pseudo_quotes), pct(ids_pseudo_quotes)),
            '| bare_latex_cmds | {:,} | {:.1f}% |'.format(len(ids_bare_latex), pct(ids_bare_latex)),
            '| unpaired_dollars | {:,} | {:.1f}% |'.format(len(ids_unpaired), pct(ids_unpaired)),
            '| truncated (без подпунктов) | {:,} | {:.1f}% |'.format(len(ids_truncated), pct(ids_truncated)),
            '| forum_traces | {:,} | {:.1f}% |'.format(len(ids_forum), pct(ids_forum)),
            '| spam_links | {:,} | {:.1f}% |'.format(len(ids_spam), pct(ids_spam)),
            '',
            '## Категории заголовков',
            '',
            '| Категория | Задач | % | Файл id |',
            '|---|---:|---:|---|',
            '| (а) echo_stub — начало условия | {:,} | {:.1f}% | ids_echo_stub.txt |'.format(
                len(ids_echo_stub), pct(ids_echo_stub)),
            '| (б) raw_latex — LaTeX в заголовке | {:,} | {:.1f}% | ids_raw_latex_title.txt |'.format(
                len(ids_raw_latex), pct(ids_raw_latex)),
            '| (в) tail_stub — обрубок по хвосту | {:,} | {:.1f}% | ids_tail_stub.txt |'.format(
                len(ids_tail_stub), pct(ids_tail_stub)),
            '| (г) junk — пусто/прочерк/Разное N | {:,} | {:.1f}% | ids_junk_title.txt |'.format(
                len(ids_junk), pct(ids_junk)),
            '| **Итого заголовки (а+б+в+г)** | **{:,}** | **{:.1f}%** | — |'.format(
                len(all_title_bad), pct(all_title_bad)),
            '',
            '## Исправление маркера truncated',
            '',
            'Раньше: двоеточие в конце условия = обрыв (всегда).',
            'Теперь: двоеточие = обрыв ТОЛЬКО если нет ProblemPart. '
            'Двоеточие + подпункты = нормальный ввод к вариантам ответа.',
            '',
            'Реальных обрывов (без подпунктов): {:,} ({:.1f}%)'.format(
                len(ids_truncated), pct(ids_truncated)),
            '',
        ]

        md_path = os.path.join(REPORT_DIR, 'refined_summary.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md))
        self.stdout.write('\nМаркдаун → {}'.format(md_path))
