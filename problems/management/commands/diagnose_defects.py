"""
Диагностика дефектов по 20 классам + детектор D1 KaTeX (только чтение, ничего не меняет).

Анализирует только видимые задачи: published, needs_quality_review=False.
Для каждой задачи проверяет: title, statement, solution, answer и все ProblemPart.

Классы дефектов:
  A1–A10 — LaTeX-артефакты вне математики
  B1–B7  — Структурные проблемы
  C1–C3  — Неисправимые / только шлюз
  D1     — KaTeX-эвристика (см. --only-render)

Детектор D1 (--only-render):
  Django test client выполняет Python/Django-код, но НЕ запускает JavaScript.
  KaTeX рендерит формулы в браузере — 'katex-error' спаны появляются только там.
  Мы вместо этого:
    1. Подтверждаем HTTP 200 для каждой страницы (валидация роутинга/view).
    2. Извлекаем LaTeX-спаны из HTML-ответа (html.unescape + MATH_SPAN_RE).
    3. Применяем эвристики, которые дают katex-error при throwOnError:false:
       - несбалансированные {} в мат-спане → ParseError: Expected '}'
       - \\begin{X} где X не поддерживается KaTeX → ParseError: unknown environment
       - команды \\mbox, \\usepackage, \\newcommand и т.п. → undefined control sequence

Запуск 20 классов:
    ./venv/bin/python manage.py diagnose_defects
    ./venv/bin/python manage.py diagnose_defects --source-id 14
    ./venv/bin/python manage.py diagnose_defects --source-id 2
    ./venv/bin/python manage.py diagnose_defects --source-id 13
    ./venv/bin/python manage.py diagnose_defects --limit 5000

Запуск D1:
    ./venv/bin/python manage.py diagnose_defects --only-render
    ./venv/bin/python manage.py diagnose_defects --only-render --sample-size 2000
    ./venv/bin/python manage.py diagnose_defects --only-render --source-id 14
"""

import os
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from problems.models import Problem, Source

REPORT_DIR = 'reports/quality_audit'
N_EXAMPLES = 5  # примеров на класс в итоговом отчёте

# ── извлечение текста «вне математики» ──────────────────────────────────────

MATH_SPAN_RE = re.compile(
    r'\\\[.+?\\\]'      # \[ ... \]
    r'|\\\(.+?\\\)'     # \( ... \)
    r'|\$\$.+?\$\$'     # $$ ... $$
    r'|\$[^$]+?\$',     # $ ... $
    re.DOTALL,
)


def outside_math(text):
    """Возвращает текст поля с вырезанными мат-спанами."""
    if not text:
        return ''
    # Маскируем \$ чтобы не считать за границу спана
    masked = text.replace('\\$', '\x00\x00')
    return MATH_SPAN_RE.sub(' ', masked)


def _snip(text, m, before=35, total=150):
    """Фрагмент текста вокруг совпадения m (или позиции m)."""
    pos = m.start() if hasattr(m, 'start') else m
    start = max(0, pos - before)
    return text[start:pos + total].replace('\n', ' ⏎ ').strip()[:total]


# ── регулярки класса A ───────────────────────────────────────────────────────

A1_RE = re.compile(r'\\footnote\{')

# Строка начинается с %, исключаем: \% (слэш перед %), %D0%B5-стиль URL
A2_RE = re.compile(r'(?m)^\s*%(?=[A-Za-zА-Яа-яЁё\\])')

A3_RE = re.compile(r'(?<!\\)&')          # & без экранирования
A4_RE = re.compile(r'p\{\d+(?:cm|mm)\}') # p{3cm} / p{15mm}
A5_RE = re.compile(r'\\%')               # \% вне математики
# -- вне математики; исключаем числа вида 1--2 (lookbehind/lookahead по \d)
A6_RE = re.compile(r'(?<!\d)--(?!\d)')
A7_RE = re.compile(r'\\(?:label|ref|cite)\{')
A8_RE = re.compile(r'\\(?:textcolor|fcolorbox)\{')
A9_RE = re.compile(r'^\s*\[\d{1,2}\]')   # [5] или [12] в начале title
A10_RE = re.compile(r'^\s*\d{4}\)')      # 2024) в начале title

# ── регулярки класса B ───────────────────────────────────────────────────────

TASK_VERB_RE = re.compile(
    r'\?|найди|определи|рассчита|вычисли|докажи|объясни|посчита|покажи'
    r'|find\b|calculat|determin|show\b|prove\b|compute\b',
    re.IGNORECASE,
)

# Варианты слиты в одну строку: «а) ... б)» или «a) ... b)»
# Без re.DOTALL: точка не матчит \n → только одна строка
MERGED_CYR_RE = re.compile(r'[аА]\).{5,50}[бБ]\)', re.IGNORECASE)
MERGED_LAT_RE = re.compile(r'[aA]\).{5,50}[bB]\)', re.IGNORECASE)

# Маркеры вариантов для B6 (смешение алфавитов)
CYR_MARKER_RE = re.compile(r'(?<!\w)[аАбБвВгГдД]\)')
LAT_MARKER_RE = re.compile(r'(?<!\w)[aAbBcCdDeE]\)')

B7_RE = re.compile(r'Ответ\s*:|Answer\s*:', re.IGNORECASE)

# ── регулярки класса C ───────────────────────────────────────────────────────

FIGURE_RE = re.compile(
    r'in the figure|на рисунке|на графике|см\.\s*рис|see figure|see graph',
    re.IGNORECASE,
)

# Переход кириллица ↔ латиница без пробела — катастрофический сбой парсинга
CYRLAT_RE = re.compile(
    r'[А-Яа-яЁё]{5,}[A-Za-z]{5,}|[A-Za-z]{5,}[А-Яа-яЁё]{5,}',
)

# ── метаданные классов ───────────────────────────────────────────────────────

DEFECT_META = {
    'A1':  (r'\footnote{ в любом поле',                   'auto'),
    'A2':  (r'строка с % вне мат-спанов (комментарий)',   'auto'),
    'A3':  (r'& вне математики (tabular-остатки)',         'auto'),
    'A4':  (r'p{Ncm/mm} вне математики',                  'auto'),
    'A5':  (r'\% вне математики (видно как \%)',           'auto'),
    'A6':  (r'-- вне математики (не em-dash)',             'auto'),
    'A7':  (r'\label{/\ref{/\cite{',                       'auto'),
    'A8':  (r'\textcolor{/\fcolorbox{',                    'auto'),
    'A9':  (r'[N] в начале title (нумерация теста)',       'auto'),
    'A10': (r'YYYY) в начале title (нумерация сборника)',  'auto'),
    'B1':  (r'title < 15 символов (огрызок)',              'auto'),
    'B2':  (r'title > 200 символов (явно не заголовок)',   'auto'),
    'B3':  (r'statement без ?, найди, find и т.п. (>100)', 'review'),
    'B4':  (r'тест без подпунктов (варианты в statement)', 'review'),
    'B5':  (r'а)/б) слиты в одну строку',                 'auto'),
    'B6':  (r'смешение кир.+лат. маркеров в подпунктах',  'review'),
    'B7':  (r'"Ответ:" в statement/solution',              'auto'),
    'C1':  (r'ссылка на рисунок, нет прикреплённых файлов','gate'),
    'C2':  (r'statement < 40 символов (критический огрызок)','gate'),
    'C3':  (r'слипшиеся слова (кир↔лат переход)',          'gate'),
}

ALL_CLASSES = list(DEFECT_META.keys())


# ── основная проверка одной задачи ──────────────────────────────────────────

def check_problem(problem, parts_list, files_prefetched):
    """
    Возвращает dict {cls: (triggered: bool, snippet: str)}.
    parts_list — уже загруженный список ProblemPart.
    files_prefetched — число файлов (int).
    """
    title = (problem.title or '').strip()
    stmt  = problem.solution_needs_review and (problem.statement or '') or (problem.statement or '')
    stmt  = problem.statement or ''
    sol   = problem.solution or ''
    ans   = problem.answer or ''

    # outside-math версии основных полей
    ost = outside_math(stmt)
    oss = outside_math(sol)
    osa = outside_math(ans)
    outside_main = ost + '\n' + oss + '\n' + osa

    # тексты подпунктов
    parts_texts = []
    parts_labels = []
    for p in parts_list:
        parts_texts.extend([p.statement or '', p.answer or '', p.solution or ''])
        parts_labels.append(p.label or '')
    parts_combined = '\n'.join(parts_texts)
    parts_outside  = outside_math(parts_combined)

    outside_full = outside_main + '\n' + parts_outside
    combined_all = stmt + '\n' + sol + '\n' + ans + '\n' + parts_combined

    r = {}

    # ── A1: \footnote{ ──────────────────────────────────────────────────────
    m = A1_RE.search(combined_all)
    r['A1'] = (bool(m), _snip(combined_all, m) if m else '')

    # ── A2: строка-комментарий % вне математики ────────────────────────────
    a2_found, a2_snip = False, ''
    for t in [ost, oss, osa, parts_outside]:
        m = A2_RE.search(t)
        if m:
            a2_found, a2_snip = True, _snip(t, m)
            break
    r['A2'] = (a2_found, a2_snip)

    # ── A3: & без экранирования вне математики ─────────────────────────────
    m = A3_RE.search(outside_full)
    r['A3'] = (bool(m), _snip(outside_full, m) if m else '')

    # ── A4: p{Ncm} / p{Nmm} вне математики ────────────────────────────────
    m = A4_RE.search(outside_full)
    r['A4'] = (bool(m), _snip(outside_full, m) if m else '')

    # ── A5: \% вне математики ──────────────────────────────────────────────
    m = A5_RE.search(outside_full)
    r['A5'] = (bool(m), _snip(outside_full, m) if m else '')

    # ── A6: -- вне математики (не между цифрами, не в URL) ─────────────────
    a6_found, a6_snip = False, ''
    for t in [ost, oss, osa, parts_outside]:
        for m in A6_RE.finditer(t):
            ctx = t[max(0, m.start() - 40): m.end() + 40]
            if 'http' in ctx or 'www.' in ctx:
                continue
            a6_found, a6_snip = True, _snip(t, m)
            break
        if a6_found:
            break
    r['A6'] = (a6_found, a6_snip)

    # ── A7: \label{, \ref{, \cite{ вне математики ───────────────────────────
    m = A7_RE.search(outside_full)
    r['A7'] = (bool(m), _snip(outside_full, m) if m else '')

    # ── A8: \textcolor{, \fcolorbox{ вне математики ─────────────────────────
    m = A8_RE.search(outside_full)
    r['A8'] = (bool(m), _snip(outside_full, m) if m else '')

    # ── A9: [N] в начале title ──────────────────────────────────────────────
    a9 = bool(A9_RE.match(title))
    r['A9'] = (a9, title[:100] if a9 else '')

    # ── A10: YYYY) в начале title ───────────────────────────────────────────
    a10 = bool(A10_RE.match(title))
    r['A10'] = (a10, title[:100] if a10 else '')

    # ── B1: title < 15 символов ─────────────────────────────────────────────
    b1 = bool(title) and len(title) < 15
    r['B1'] = (b1, title[:100] if b1 else '')

    # ── B2: title > 200 символов ────────────────────────────────────────────
    b2 = len(title) > 200
    r['B2'] = (b2, title[:200] if b2 else '')

    # ── B3: statement > 100, нет вопроса/глаголов, не тест ─────────────────
    ptype = (problem.problem_type or '').lower()
    is_test = ptype.startswith('тест:') or ptype.startswith('test_')
    b3 = (
        len(stmt) > 100
        and not TASK_VERB_RE.search(stmt)
        and not is_test
    )
    r['B3'] = (b3, stmt[-120:].strip() if b3 else '')

    # ── B4: тестовый тип без подпунктов ────────────────────────────────────
    b4 = is_test and len(parts_list) == 0
    r['B4'] = (b4, stmt[:100] if b4 else '')

    # ── B5: варианты слиты в одну строку ───────────────────────────────────
    b5c = MERGED_CYR_RE.search(stmt)
    b5l = MERGED_LAT_RE.search(stmt)
    b5m = b5c or b5l
    r['B5'] = (bool(b5m), _snip(stmt, b5m) if b5m else '')

    # ── B6: смешение кириллических и латинских маркеров ────────────────────
    label_pool = stmt + '\n' + '\n'.join(parts_labels)
    has_cyr = bool(CYR_MARKER_RE.search(label_pool))
    has_lat = bool(LAT_MARKER_RE.search(label_pool))
    if has_cyr and has_lat:
        mc = CYR_MARKER_RE.search(label_pool)
        ml = LAT_MARKER_RE.search(label_pool)
        r['B6'] = (True,
                   f'кирилл «{label_pool[mc.start():mc.end()]}» '
                   f'+ латин «{label_pool[ml.start():ml.end()]}»')
    else:
        r['B6'] = (False, '')

    # ── B7: "Ответ:" или "Answer:" в statement или solution ─────────────────
    b7_stmt = B7_RE.search(stmt)
    b7_sol  = B7_RE.search(sol)
    b7m = b7_stmt or b7_sol
    if b7m:
        src_t = stmt if b7_stmt else sol
        r['B7'] = (True, _snip(src_t, b7m))
    else:
        r['B7'] = (False, '')

    # ── C1: ссылка на рисунок, нет прикреплённых файлов ────────────────────
    fig_m = FIGURE_RE.search(stmt)
    c1 = bool(fig_m) and files_prefetched == 0
    r['C1'] = (c1, _snip(stmt, fig_m) if c1 else '')

    # ── C2: statement < 40 символов ────────────────────────────────────────
    stmt_stripped = stmt.strip()
    c2 = bool(stmt_stripped) and len(stmt_stripped) < 40
    r['C2'] = (c2, stmt_stripped[:100] if c2 else '')

    # ── C3: слипшиеся слова (переход кириллица ↔ латиница без пробела) ─────
    c3m = CYRLAT_RE.search(stmt)
    r['C3'] = (bool(c3m), _snip(stmt, c3m) if c3m else '')

    return r


# ── вспомогательные утилиты форматирования ──────────────────────────────────

def fmt_pct(n, total):
    if total == 0:
        return '0.0%'
    return f'{n / total * 100:.1f}%'


def _bar(label, count, label_width=30):
    return f'{label:<{label_width}} {count:>5}'


# ── D1: KaTeX-эвристики ─────────────────────────────────────────────────────
#
# Django test client НЕ выполняет JavaScript, поэтому 'katex-error' спаны из
# auto-render.min.js в серверном HTML не появятся.  Вместо этого:
# 1) проверяем HTTP-коды (валидация роутинга);
# 2) извлекаем LaTeX-спаны из HTML-ответа (html.unescape + MATH_SPAN_RE);
# 3) применяем три эвристики, которые на 100% дают KaTeX ParseError
#    при throwOnError:false.

# Окружения, поддерживаемые KaTeX внутри math-режима
KATEX_MATH_ENVS = {
    'array', 'darray', 'matrix', 'matrix*', 'pmatrix', 'pmatrix*',
    'bmatrix', 'bmatrix*', 'Bmatrix', 'Bmatrix*', 'vmatrix', 'vmatrix*',
    'Vmatrix', 'Vmatrix*', 'smallmatrix', 'cases', 'dcases', 'rcases',
    'drcases', 'aligned', 'gathered', 'split', 'alignedat', 'CD',
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'alignat', 'alignat*',
}

# Убираем <script> и <style> перед поиском мат-спанов в HTML-ответе
STRIP_TAGS_RE = re.compile(
    r'<(script|style)[^>]*>.*?</(script|style)>',
    re.DOTALL | re.IGNORECASE,
)
# Все прочие HTML-теги — заменяем пробелом, чтобы мат-спаны не "перескакивали"
# через границы элементов (иначе $Q_{ из <p> спаривается с $ из <div class="...">)
HTML_ANY_TAG_RE = re.compile(r'<[^>]+>', re.DOTALL)
# Маркер начала блока «похожие задачи» — именно открывающий тег, а не CSS-класс.
# Всё от него до конца страницы отбрасываем: truncatechars рвёт $...$ посередине.
SIMILAR_BLOCK_START = b'<div class="similar-block"'

# Команды, гарантированно вызывающие ParseError «undefined control sequence»
KATEX_BAD_CMDS_RE = re.compile(
    r'\\(?:mbox|hbox|vbox|usepackage|documentclass|newcommand|renewcommand'
    r'|DeclareMathOperator|newenvironment)\b',
)

# \begin{EnvName} внутри мат-спана — проверяем EnvName против KATEX_MATH_ENVS
D1_BEGIN_ENV_RE = re.compile(r'\\begin\{([a-zA-Z*]+)\}')


def _brace_depth(body):
    """Баланс {} в теле мат-спана (\\{ и \\} не считаются)."""
    s = body.replace('\\{', '').replace('\\}', '')
    return s.count('{') - s.count('}')


def katex_span_issues(body):
    """Эвристика: возвращает список строк-причин KaTeX ParseError (или [] если OK)."""
    issues = []
    d = _brace_depth(body)
    if d != 0:
        issues.append(f'brace:{d:+d}')
    for m in D1_BEGIN_ENV_RE.finditer(body):
        env = m.group(1)
        if env not in KATEX_MATH_ENVS:
            issues.append(f'bad_env:{env}')
    bm = KATEX_BAD_CMDS_RE.search(body)
    if bm:
        issues.append(f'bad_cmd:{bm.group(0)[:20]}')
    return issues


def extract_math_from_html(html_bytes):
    """Вернуть список мат-спанов из HTML-ответа сервера.

    Порядок:
    1. Срезаем всё с блока «похожие задачи» — там truncatechars рвёт $...$
       → ложные кросс-блочные спаны.
    2. Убираем <script>/<style>.
    3. Заменяем все прочие HTML-теги пробелом (чтобы $Q_{D}$ не склеивался
       с $ из следующего абзаца через границу элементов).
    4. html.unescape + маскировка \\$.
    """
    import html as html_module
    # 1) обрезать похожие задачи (последний блок страницы)
    idx = html_bytes.find(SIMILAR_BLOCK_START)
    if idx != -1:
        html_bytes = html_bytes[:idx]
    text = html_bytes.decode('utf-8', errors='replace')
    text = STRIP_TAGS_RE.sub('', text)       # <script>/<style> → убрать
    text = HTML_ANY_TAG_RE.sub(' ', text)    # <div class="..."> → пробел
    text = html_module.unescape(text)
    text = text.replace('\\$', '\x00\x00')
    return [m.group(0) for m in MATH_SPAN_RE.finditer(text)]


# ── команда ─────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Диагностика дефектов по 20 классам (только чтение, ничего не меняет)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-id', type=int, default=None,
            help='Анализировать только один источник (по id)',
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Максимальное число анализируемых задач (default: все видимые)',
        )
        parser.add_argument(
            '--only-render', action='store_true', default=False,
            help='Запустить только детектор D1 (KaTeX-эвристика через test client)',
        )
        parser.add_argument(
            '--sample-size', type=int, default=1000,
            help='Размер выборки для --only-render (default: 1000)',
        )

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        if options['only_render']:
            source_names = {s.id: s.name for s in Source.objects.all()}
            source_names[0] = '(без источника)'
            self._handle_d1(options, source_names)
            return

        # ── подготовка имён источников ──────────────────────────────────────
        source_names = {s.id: s.name for s in Source.objects.all()}
        source_names[0] = '(без источника)'

        # ── базовый queryset: только видимые задачи ──────────────────────────
        qs = (
            Problem.objects
            .filter(status='published', needs_quality_review=False)
            .prefetch_related('parts', 'source_references', 'files')
            .order_by('id')
        )
        if options['source_id']:
            qs = qs.filter(
                source_references__source_id=options['source_id']
            ).distinct()
        if options['limit']:
            qs = qs[:options['limit']]

        # ── счётчики ────────────────────────────────────────────────────────
        # per-class: count, examples[(id, snip)]
        cls_count   = defaultdict(int)
        cls_examples = defaultdict(list)  # список (problem_id, snippet)

        # per-source: {src_id: {cls: count}}
        src_cls = defaultdict(lambda: defaultdict(int))
        src_total = defaultdict(int)

        total = 0

        for problem in qs.iterator(chunk_size=400):
            total += 1

            # источник
            refs = list(problem.source_references.all())
            sid = refs[0].source_id if refs else 0
            src_total[sid] += 1

            # число файлов (prefetch_related уже загрузил)
            files_count = len(problem.files.all())

            parts_list = list(problem.parts.all())

            checks = check_problem(problem, parts_list, files_count)

            for cls in ALL_CLASSES:
                triggered, snip = checks[cls]
                if triggered:
                    cls_count[cls] += 1
                    src_cls[sid][cls] += 1
                    if len(cls_examples[cls]) < N_EXAMPLES:
                        cls_examples[cls].append((problem.id, snip))

            if total % 5000 == 0:
                self.stdout.write(f'  ...обработано {total} задач')

        # ── формирование отчёта ──────────────────────────────────────────────
        lines = []
        lines.append(f'# Диагностика дефектов')
        lines.append('')
        lines.append(f'Проанализировано задач: **{total}** (published, без флага шлюза)')
        if options['source_id']:
            sid_filter = options['source_id']
            lines.append(f'Источник: #{sid_filter} — {source_names.get(sid_filter, "?")}')
        lines.append('')

        # ── сводная таблица ──────────────────────────────────────────────────
        lines.append('## Сводная таблица')
        lines.append('')
        lines.append(
            f'{"КЛАСС":<6} {"ОПИСАНИЕ":<50} {"ЗАДАЧ":>6} {"% всех":>7}  '
            f'{"ПРИМЕРЫ ID"}'
        )
        lines.append('-' * 110)

        sorted_classes = sorted(ALL_CLASSES, key=lambda c: -cls_count[c])

        for cls in ALL_CLASSES:
            label, strategy = DEFECT_META[cls]
            cnt = cls_count[cls]
            pct = fmt_pct(cnt, total)
            ex_ids = ', '.join(f'#{i}' for i, _ in cls_examples[cls][:5])
            lines.append(
                f'{cls:<6} {label:<50} {cnt:>6} {pct:>7}  {ex_ids}'
            )

        lines.append('')

        # ── по источникам ────────────────────────────────────────────────────
        lines.append('## По источникам (топ-3 класса)')
        lines.append('')
        lines.append(f'{"ИСТОЧНИК":<55} {"ЗАДАЧ":>6}  {"ТОП-3 КЛАССА (N задач)"}')
        lines.append('-' * 100)

        for sid in sorted(src_total.keys(), key=lambda s: -src_total[s]):
            sname = source_names.get(sid, f'Source #{sid}')
            stotal = src_total[sid]
            top3 = sorted(src_cls[sid].items(), key=lambda x: -x[1])[:3]
            top3_str = ', '.join(f'{c} ({n})' for c, n in top3)
            label_short = (f'#{sid} {sname}')[:54]
            lines.append(f'{label_short:<55} {stotal:>6}  {top3_str}')

        lines.append('')

        # ── примеры для каждого класса ───────────────────────────────────────
        lines.append('## Примеры дефектов (до 5 на класс)')
        lines.append('')

        for cls in ALL_CLASSES:
            label, strategy = DEFECT_META[cls]
            cnt = cls_count[cls]
            examples = cls_examples[cls]
            strategy_tag = {'auto': '🔧 авто', 'review': '👁 ревью', 'gate': '🚧 шлюз'}[strategy]
            lines.append(f'### {cls} — {label}  [{strategy_tag}]')
            lines.append(f'Задач: **{cnt}** ({fmt_pct(cnt, total)})')
            if examples:
                for pid, snip in examples:
                    snip_clean = snip.replace('\n', ' ').strip()
                    lines.append(f'  `#{pid}`: {snip_clean}')
            else:
                lines.append('  *(дефект не обнаружен)*')
            lines.append('')

        # ── итоговые рекомендации ────────────────────────────────────────────
        lines.append('## Рекомендации')
        lines.append('')
        top5 = sorted(ALL_CLASSES, key=lambda c: -cls_count[c])[:5]
        lines.append('**Топ-5 классов по числу задач:**')
        for cls in top5:
            label, strategy = DEFECT_META[cls]
            cnt = cls_count[cls]
            lines.append(f'- {cls}: {cnt} ({fmt_pct(cnt, total)}) — {label}')
        lines.append('')
        lines.append('**Стратегии:**')
        lines.append('')

        auto_classes = [c for c in sorted_classes if DEFECT_META[c][1] == 'auto' and cls_count[c] > 0]
        review_classes = [c for c in sorted_classes if DEFECT_META[c][1] == 'review' and cls_count[c] > 0]
        gate_classes = [c for c in sorted_classes if DEFECT_META[c][1] == 'gate' and cls_count[c] > 0]

        if auto_classes:
            lines.append('🔧 **Чинить автоматически (новая команда fix_*):**')
            for c in auto_classes:
                lines.append(f'  - {c}: {cls_count[c]} задач — {DEFECT_META[c][0]}')
            lines.append('')
        if review_classes:
            lines.append('👁 **Требуют ревью / частичной автоматизации:**')
            for c in review_classes:
                lines.append(f'  - {c}: {cls_count[c]} задач — {DEFECT_META[c][0]}')
            lines.append('')
        if gate_classes:
            lines.append('🚧 **Закрыть шлюзом (автоматическое исправление невозможно):**')
            for c in gate_classes:
                lines.append(f'  - {c}: {cls_count[c]} задач — {DEFECT_META[c][0]}')
            lines.append('')

        # ── сохранение отчёта ────────────────────────────────────────────────
        src_suffix = f'_source{options["source_id"]}' if options['source_id'] else ''
        report_path = os.path.join(REPORT_DIR, f'defect_diagnosis{src_suffix}.md')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        # ── вывод на экран ───────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Проанализировано задач: {total} (published, без флага шлюза)'
            )
        )
        self.stdout.write('')
        self.stdout.write(
            f'{"КЛАСС":<6} {"ОПИСАНИЕ":<48} {"ЗАДАЧ":>6} {"% всех":>7}'
        )
        self.stdout.write('-' * 75)
        for cls in ALL_CLASSES:
            label, _ = DEFECT_META[cls]
            cnt = cls_count[cls]
            pct = fmt_pct(cnt, total)
            marker = '  ←' if cnt > 0 else ''
            self.stdout.write(f'{cls:<6} {label:<48} {cnt:>6} {pct:>7}{marker}')
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Топ-5 по числу задач: '
                + ', '.join(
                    f'{c}={cls_count[c]}' for c in top5
                )
            )
        )
        self.stdout.write('')
        self.stdout.write(f'Отчёт сохранён: {report_path}')
        self.stdout.write('')

    # ────────────────────────────────────────────────────────────────────────
    def _handle_d1(self, options, source_names):
        """Детектор D1: KaTeX-эвристика через Django test client.

        Примечание о подходе: Django test client НЕ выполняет JS.
        Поэтому 'katex-error' в серверном HTML не появится — это клиентский рендер.
        Мы валидируем HTTP 200 и применяем эвристики на LaTeX-спанах из HTML-ответа.
        """
        import random
        from django.test import Client
        from django.contrib.auth import get_user_model
        from problems.models import SourceReference

        User = get_user_model()
        user = (
            User.objects.filter(is_staff=True).first()
            or User.objects.filter(is_active=True).first()
        )
        if not user:
            self.stderr.write('Нет пользователей для авторизации. Прервано.')
            return

        client = Client()
        client.force_login(user)

        source_id = options.get('source_id')
        sample_size = options.get('sample_size', 1000)

        qs = Problem.objects.filter(status='published', needs_quality_review=False)
        if source_id:
            qs = qs.filter(source_references__source_id=source_id).distinct()

        ids = list(qs.values_list('id', flat=True))
        if not ids:
            self.stderr.write('Нет задач для выборки.')
            return

        random.seed(42)
        sample = random.sample(ids, min(sample_size, len(ids)))
        random.seed(None)

        # предзагружаем source_id для задач выборки
        id_to_src = {
            r.problem_id: r.source_id
            for r in SourceReference.objects.filter(problem_id__in=sample)
        }

        # накопители
        errors      = []   # {id, sid, spans_checked, issues_found: [(body80, [issue_str])]}
        http_errors = []   # {id, status}
        no_katex    = []   # id без 'katex' в HTML (не должно быть при нормальном шаблоне)
        total_spans = 0

        from collections import defaultdict as _dd
        src_stats = _dd(lambda: {'total': 0, 'with_issues': 0, 'spans': 0})

        self.stdout.write(
            f'D1: выборка {len(sample)} задач (seed=42), авторизация как «{user.username}»'
        )
        self.stdout.write(
            '    ВАЖНО: KaTeX — клиентский JS; katex-error в серверном HTML отсутствует.'
        )
        self.stdout.write(
            '    Применяем эвристики: несбалансированные {}, bad_env, bad_cmd.\n'
        )

        for i, pid in enumerate(sample):
            sid = id_to_src.get(pid, 0)
            src_stats[sid]['total'] += 1

            response = client.get(
                f'/catalog/problem/{pid}/',
                SERVER_NAME='localhost',
            )

            if response.status_code != 200:
                http_errors.append({'id': pid, 'status': response.status_code})
                if (i + 1) % 200 == 0:
                    self.stdout.write(f'  ...D1 {i+1}/{len(sample)}')
                continue

            raw = response.content
            if b'katex' not in raw.lower():
                no_katex.append(pid)

            spans = extract_math_from_html(raw)
            total_spans += len(spans)
            src_stats[sid]['spans'] += len(spans)

            problem_issues = []
            for span in spans:
                issues = katex_span_issues(span)
                if issues:
                    problem_issues.append((span[:80].replace('\n', ' '), issues))

            if problem_issues:
                errors.append({
                    'id':   pid,
                    'sid':  sid,
                    'n_spans': len(spans),
                    'issues': problem_issues[:3],
                })
                src_stats[sid]['with_issues'] += 1

            if (i + 1) % 200 == 0:
                self.stdout.write(
                    f'  ...D1: {i+1}/{len(sample)} задач, '
                    f'{len(errors)} с потенц. ошибками KaTeX'
                )

        # ── формирование отчёта ──────────────────────────────────────────────
        checked   = len(sample) - len(http_errors)
        err_pct   = fmt_pct(len(errors), checked) if checked else '—'
        http_pct  = fmt_pct(len(http_errors), len(sample))

        lines = []
        lines.append('# D1: KaTeX-эвристика через Django test client')
        lines.append('')
        lines.append(
            '> **Примечание:** Django test client не выполняет JavaScript.  '
        )
        lines.append(
            '> `katex-error` спаны появляются только в браузере после JS-рендера.  '
        )
        lines.append(
            '> Здесь применяются эвристики: дисбаланс `{}`, '
            'неподдерживаемые `\\begin{X}`, неизвестные команды.'
        )
        lines.append('')
        lines.append(f'## Сводка')
        lines.append('')
        lines.append(f'| Метрика | Значение |')
        lines.append(f'|---------|---------|')
        lines.append(f'| Выборка (seed=42) | {len(sample)} |')
        lines.append(f'| Всего в базе (published, не зафлагованы) | {len(ids)} |')
        lines.append(f'| HTTP 200 | {checked} ({fmt_pct(checked, len(sample))}) |')
        lines.append(f'| HTTP ≠ 200 | {len(http_errors)} ({http_pct}) |')
        lines.append(f'| Без KaTeX в HTML | {len(no_katex)} |')
        lines.append(f'| Мат-спанов извлечено | {total_spans} |')
        lines.append(f'| Задач с потенц. KaTeX-ошибкой | **{len(errors)}** ({err_pct}) |')
        lines.append('')

        if http_errors:
            lines.append('### HTTP-ошибки')
            for e in http_errors[:20]:
                lines.append(f'  `#{e["id"]}` → HTTP {e["status"]}')
            lines.append('')

        # топ-10 примеров
        lines.append('## Топ примеров (до 10)')
        lines.append('')
        lines.append(
            '_(Задачи с наибольшим числом проблемных мат-спанов)_'
        )
        lines.append('')
        sorted_errors = sorted(errors, key=lambda e: -len(e['issues']))
        for e in sorted_errors[:10]:
            sname = source_names.get(e['sid'], f'src#{e["sid"]}')
            lines.append(f'### #{e["id"]} — {sname}')
            lines.append(f'  Мат-спанов: {e["n_spans"]}, проблемных: {len(e["issues"])}')
            for body, issues in e['issues']:
                lines.append(f'  - `{", ".join(issues)}` в `{body}`')
            lines.append('')

        # по источникам
        lines.append('## По источникам (топ-5 по % задач с ошибками)')
        lines.append('')
        lines.append(
            f'| Источник | Задач | Ошибок | % | Спанов |'
        )
        lines.append(f'|---------|------:|------:|------:|------:|')

        src_list = [
            (sid, d) for sid, d in src_stats.items() if d['total'] > 0
        ]
        src_list.sort(
            key=lambda x: -(x[1]['with_issues'] / x[1]['total'] if x[1]['total'] else 0)
        )
        for sid, d in src_list[:5]:
            sname = source_names.get(sid, f'#{sid}')[:40]
            pct = fmt_pct(d['with_issues'], d['total'])
            lines.append(
                f'| #{sid} {sname} | {d["total"]} | {d["with_issues"]} | {pct} | {d["spans"]} |'
            )
        lines.append('')

        lines.append('## Распределение типов ошибок')
        lines.append('')
        issue_types = _dd(int)
        for e in errors:
            for _, issues in e['issues']:
                for issue in issues:
                    key = issue.split(':')[0]
                    issue_types[key] += 1
        for k, v in sorted(issue_types.items(), key=lambda x: -x[1]):
            lines.append(f'- `{k}`: {v} спанов')
        lines.append('')

        # сохранение
        src_suffix = f'_source{source_id}' if source_id else ''
        report_path = os.path.join(
            REPORT_DIR, f'defect_diagnosis_katex{src_suffix}.md'
        )
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        # вывод на экран
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'D1 результат: {len(errors)}/{checked} задач с потенц. KaTeX-ошибками ({err_pct})'
        ))
        if http_errors:
            self.stdout.write(
                self.style.WARNING(f'  HTTP-ошибок: {len(http_errors)}')
            )
        if no_katex:
            self.stdout.write(
                self.style.WARNING(f'  Без KaTeX в HTML: {len(no_katex)}')
            )
        self.stdout.write('')
        self.stdout.write('Топ источников по % ошибок:')
        for sid, d in src_list[:5]:
            sname = source_names.get(sid, f'#{sid}')[:35]
            pct = fmt_pct(d['with_issues'], d['total'])
            self.stdout.write(
                f'  #{sid} {sname}: {d["with_issues"]}/{d["total"]} ({pct})'
            )
        self.stdout.write('')
        self.stdout.write(f'Отчёт сохранён: {report_path}')
        self.stdout.write('')
