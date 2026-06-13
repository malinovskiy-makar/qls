"""
Конвертация \\begin{tabular} с вариантами ответов и оборачивание
\\begin{cases}/\\begin{equation*} вне математики в $$...$$ (сессия E).

Главный брак (ручной аудит преподавателя): в Archive 3 (#14) тестовые задачи,
где варианты а)–д) свёрстаны таблицей \\begin{tabular}{...} а) ... & б) ...
\\end{tabular} — часто ВНУТРИ $$...$$. KaTeX tabular не поддерживает →
красная ошибка рендера.

Что делает (по полям statement/solution/answer задач и подпунктов):

1. tabular-блок (вне математики или занимающий весь $$...$$/$...$ спан):
   - содержимое — варианты ответов (≥2 маркеров а)/б)/в)… или a)–e),
     ≥60% ячеек начинаются с маркера) → блок заменяется простым текстом:
     каждый вариант с новой строки; & и \\\\ → переводы строк; спецификация
     колонок и \\hline удаляются; внутренности вариантов НЕ меняются;
     висячий % сразу после \\end{tabular} убирается;
   - содержимое — настоящая таблица данных (мало маркеров, либо есть
     \\multicolumn/\\multirow) → НЕ конвертируется, id задачи →
     reports/quality_audit/tabular_data_tables_ids.txt (под шлюз);
   - tabular в спане с другим содержимым (mixed) → не трогаем, в отчёт.

2. Блоки equation/equation*/align*/gather*/aligned/gathered/split/cases вне
   математики → оборачиваются в $$...$$ (KaTeX эти окружения в math mode
   умеет). Внутри блока убираются вложенные $...$ (доллар внутри математики —
   ошибка KaTeX). В cases без \\\\ строки-уравнения, разделённые пустыми
   строками, склеиваются через \\\\. Если уверенности нет (вложенное
   неподдерживаемое окружение, дисбаланс скобок, слишком длинный блок,
   нет якоря математики) → не трогаем, в отчёт.

Железные правила: content_hash не трогаем, непустые поля не перезаписываем
(только трансформация на месте), число задач не меняется.

Запуск:
    ./venv/bin/python manage.py fix_tabular_variants --dry-run --examples 20
    ./venv/bin/python manage.py fix_tabular_variants --source-id 14
    ./venv/bin/python manage.py fix_tabular_variants            # вся база
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/quality_audit'
DATA_TABLE_FILE = os.path.join(REPORT_DIR, 'tabular_data_tables_ids.txt')
CHANGED_FILE = os.path.join(REPORT_DIR, 'changed_ids_E.txt')

# Окружения, которые KaTeX поддерживает внутри математики
KATEX_MATH_ENVS = {
    'array', 'darray', 'matrix', 'matrix*', 'pmatrix', 'pmatrix*',
    'bmatrix', 'bmatrix*', 'Bmatrix', 'Bmatrix*', 'vmatrix', 'vmatrix*',
    'Vmatrix', 'Vmatrix*', 'smallmatrix', 'cases', 'dcases', 'rcases',
    'drcases', 'aligned', 'gathered', 'split', 'alignedat', 'CD',
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'alignat', 'alignat*',
}

# Что оборачиваем в $$...$$ (порядок важен: внешние окружения раньше cases)
WRAP_ENVS = ('equation*', 'equation', 'align*', 'align', 'gather*', 'gather',
             'aligned', 'gathered', 'split', 'cases', 'dcases')

MATH_SPAN_RE = re.compile(
    r'\\\[(.+?)\\\]|\\\((.+?)\\\)|\$\$(.+?)\$\$|\$([^$]+?)\$', re.DOTALL)

ENV_NAME_RE = re.compile(r'\\begin\{([a-zA-Z*]+)\}')

# Маркер варианта ответа в начале ячейки: а) б). (в) a) и т.п.
MARKER_RE = re.compile(r'^\(?\s*([а-еa-fА-ЕA-F])\s*[\)\.]')

# Якорь математики для guard'а оборачивания
MATH_ANCHOR_RE = re.compile(r'[=<>≤≥⩽⩾]|\\le\b|\\ge\b|\\frac|\\min|\\max|\\to\b')


def dollar_count(text):
    return text.replace('\\$', '').count('$')


def span_ranges(text):
    """Диапазоны мат-спанов (на маскированном тексте — длины совпадают)."""
    masked = text.replace('\\$', '␦␦')
    return [(m.start(), m.end()) for m in MATH_SPAN_RE.finditer(masked)]


def find_env_blocks(text, env):
    """[(start, end), ...] для \\begin{env}...\\end{env} (первое закрытие)."""
    out = []
    begin_tok = '\\begin{%s}' % env
    end_tok = '\\end{%s}' % env
    i = 0
    while True:
        s = text.find(begin_tok, i)
        if s < 0:
            break
        e = text.find(end_tok, s + len(begin_tok))
        if e < 0:
            break
        out.append((s, e + len(end_tok)))
        i = e + len(end_tok)
    return out


def strip_colspec(s):
    """Убирает [pos] и {colspec} (с вложенными скобками, напр. {p{18cm}})."""
    i, n = 0, len(s)
    while i < n and s[i].isspace():
        i += 1
    if i < n and s[i] == '[':
        j = s.find(']', i)
        if j >= 0:
            i = j + 1
        while i < n and s[i].isspace():
            i += 1
    if i < n and s[i] == '{':
        depth, j = 0, i
        while j < n:
            if s[j] == '{':
                depth += 1
            elif s[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
    return s[i:]


# Инлайн-маркер посреди ячейки: «а) Верно б) Неверно» в одной ячейке
INLINE_MARKER_RE = re.compile(r'\s+(?=\(?[а-еa-fА-ЕA-F]\s*[\)\.]\s)')


def split_cells(body):
    """Ячейки tabular: & и \\\\ → границы; \\hline удаляется; \\& защищён.
    Ячейка с несколькими маркерами режется по маркерам; в одноколоночной
    таблице (без &) строки-продолжения приклеиваются к предыдущему варианту."""
    single_col = '&' not in body.replace('\\&', '')
    b = body.replace('\\&', '␞')
    b = re.sub(r'\\hline|\\cline\{[^}]*\}', ' ', b)
    b = b.replace('\\\\', '\n').replace('&', '\n')
    b = b.replace('␞', '\\&')
    cells = [c.strip() for c in b.split('\n')]
    cells = [c for c in cells if c and c not in ('.', ',', ';', '-', '—')]

    # «а) Верно б) Неверно» одной ячейкой → отдельные варианты
    out = []
    for c in cells:
        if MARKER_RE.match(c) and len(INLINE_MARKER_RE.split(c)) > 1:
            out.extend(p.strip() for p in INLINE_MARKER_RE.split(c) if p.strip())
        else:
            out.append(c)
    cells = out

    # перенос длинного варианта на следующую строку (только без колонок)
    if single_col:
        merged = []
        for c in cells:
            if merged and not MARKER_RE.match(c) and MARKER_RE.match(merged[-1]):
                merged[-1] += ' ' + c
            else:
                merged.append(c)
        cells = merged
    return cells


def is_variants(cells):
    letters = [MARKER_RE.match(c).group(1).lower()
               for c in cells if MARKER_RE.match(c)]
    if len(letters) < 2 or len(set(letters)) < 2:
        return False
    return len(letters) / len(cells) >= 0.6


ROW_FIX_RE = re.compile(
    r'\\begin\{(cases|dcases|align\*?|aligned|gather\*?|gathered|split)\}'
    r'(.*?)\\end\{\1\}', re.DOTALL)


def fix_env_rows(block):
    """В многострочных окружениях без \\\\ строки, разделённые пустой строкой,
    склеиваются через \\\\ (импорт когда-то съел разделители строк)."""
    def repl(m):
        env, body = m.group(1), m.group(2)
        if '\\\\' in body:
            return m.group(0)
        chunks = [c.strip() for c in re.split(r'\n\s*\n', body) if c.strip()]
        if len(chunks) < 2:
            return m.group(0)
        return '\\begin{%s}\n%s\n\\end{%s}' % (env, ' \\\\\n'.join(chunks), env)
    return ROW_FIX_RE.sub(repl, block)


def wrap_math_block(block):
    """Оборачивает блок в $$...$$: убирает вложенные $, чинит разрыв строк."""
    inner = block.replace('\\$', '␦').replace('$', '').replace('␦', '\\$')
    inner = fix_env_rows(inner)
    return '$$\n' + inner.strip() + '\n$$'


def brace_balanced(s):
    t = s.replace('\\{', '').replace('\\}', '')
    return t.count('{') == t.count('}')


def process_field(text, report):
    """Возвращает новый текст или None. report — dict со счётчиками/метками."""
    if not text or '\\begin{' not in text:
        return None
    if dollar_count(text) % 2 == 1:
        report['odd_dollar_skip'] = True
        return None
    # $$$ или нечётное число «$$» — неоднозначный парсинг делимитеров
    masked = text.replace('\\$', '')
    if '$$$' in masked or masked.count('$$') % 2 == 1:
        report['odd_dollar_skip'] = True
        return None

    # ── фаза 1: tabular ──
    changes = []
    spans = span_ranges(text)

    def span_of(pos, ranges):
        for s, e in ranges:
            if s <= pos < e:
                return (s, e)
        return None

    for bs, be in find_env_blocks(text, 'tabular'):
        block = text[bs:be]
        inner = strip_colspec(block[len('\\begin{tabular}'):-len('\\end{tabular}')])
        if '\\multicolumn' in block or '\\multirow' in block \
                or '\\begin{tabular}' in inner:
            report['data_table'] = True
            continue
        cells = split_cells(inner)
        if not is_variants(cells):
            report['data_table'] = True
            continue
        conv = '\n'.join(cells)
        sp = span_of(bs, spans)
        if sp:
            s, e = sp
            rest = (text[s:bs] + text[be:e])
            # допускаем только делимитеры, пробелы и висячие % внутри спана
            rest_clean = rest.replace('$', '').replace('\\[', '') \
                             .replace('\\]', '').replace('\\(', '') \
                             .replace('\\)', '').replace('%', '').strip()
            if rest_clean:
                report['mixed_span'] = True
                continue
            changes.append((s, e, conv))
        else:
            e2 = be
            m = re.match(r'[ \t]*%', text[be:])
            if m:
                e2 = be + m.end()
            changes.append((bs, e2, conv))
        report['tabular_converted'] = report.get('tabular_converted', 0) + 1

    new = text
    for s, e, conv in sorted(changes, key=lambda c: -c[0]):
        new = new[:s] + conv + new[e:]

    # ── фаза 2: оборачивание мат-окружений вне математики ──
    spans2 = span_ranges(new)
    claimed = []
    changes2 = []
    # незакрытый \begin{equation*} и т.п. перед cases: токен поглощается,
    # «прицеп» (напр. «Q^*(P) = ») уходит внутрь $$
    UNCLOSED_PRE_RE = re.compile(
        r'\\begin\{(equation\*?|align\*?|gather\*?)\}'
        r'((?:[^\n]|\n(?![ \t]*\n)){0,100})$', re.DOTALL)

    for env in WRAP_ENVS:
        if ('\\begin{%s}' % env) not in new:
            continue
        for bs, be in find_env_blocks(new, env):
            if span_of(bs, spans2) or span_of(bs, claimed):
                continue
            block = new[bs:be]
            inner_envs = ENV_NAME_RE.findall(block)
            if any(e2 not in KATEX_MATH_ENVS for e2 in inner_envs) \
                    or '$$' in block.replace('\\$', ''):
                report['wrap_skipped'] = True
                claimed.append((bs, be))
                continue
            if not brace_balanced(block) or len(block) > 900 \
                    or not MATH_ANCHOR_RE.search(block):
                report['wrap_skipped'] = True
                claimed.append((bs, be))
                continue

            # для голых cases/dcases: поглощаем незакрытый \begin{equation*}
            # непосредственно перед блоком (вместе с прицепом-выражением)
            ws, prefix = bs, ''
            if env in ('cases', 'dcases'):
                m = UNCLOSED_PRE_RE.search(new[max(0, bs - 130):bs])
                if m:
                    open_env = m.group(1)
                    cand_start = max(0, bs - 130) + m.start()
                    # окружение действительно не закрыто до конца блока
                    if ('\\end{%s}' % open_env) not in new[cand_start:be] \
                            and not span_of(cand_start, spans2) \
                            and not span_of(cand_start, claimed):
                        ws = cand_start
                        prefix = m.group(2)

            changes2.append((ws, be, wrap_math_block(prefix + block)))
            claimed.append((ws, be))
            report['env_wrapped'] = report.get('env_wrapped', 0) + 1

    for s, e, conv in sorted(changes2, key=lambda c: -c[0]):
        new = new[:s] + conv + new[e:]

    if new == text:
        return None

    # ── инварианты поля ──
    if dollar_count(new) % 2 == 1:
        report['invariant_fail'] = True
        return None
    return new


class Command(BaseCommand):
    help = 'Конвертация tabular с вариантами и оборачивание cases/equation* в $$'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--examples', type=int, default=0,
                            help='Печать N примеров конвертации (для dry-run)')

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        dry = options['dry_run']
        n_examples = options['examples']

        qs = (Problem.objects.all().order_by('id')
              .prefetch_related('parts'))
        if options['source_id']:
            qs = qs.filter(
                source_references__source_id=options['source_id']).distinct()
        if options['limit']:
            qs = qs[:options['limit']]

        stats = {
            'problems_changed': 0, 'fields_changed': 0,
            'tabular_converted': 0, 'env_wrapped': 0,
            'data_tables': set(), 'mixed_spans': set(),
            'wrap_skipped': set(), 'invariant_fails': set(),
            'odd_dollar': set(),
        }
        changed_ids = []
        shown = 0

        for problem in qs.iterator(chunk_size=300):
            problem_changed = False

            # поля задачи
            for field in ('statement', 'solution', 'answer'):
                old = getattr(problem, field) or ''
                rep = {}
                new = process_field(old, rep)
                self._collect(rep, stats, problem.id)
                if new is not None:
                    stats['fields_changed'] += 1
                    stats['tabular_converted'] += rep.get('tabular_converted', 0)
                    stats['env_wrapped'] += rep.get('env_wrapped', 0)
                    if shown < n_examples:
                        shown += 1
                        self._show_example(problem.id, field, old, new)
                    if not dry:
                        setattr(problem, field, new)
                        problem.save(update_fields=[field])
                    problem_changed = True

            # поля подпунктов
            for part in problem.parts.all():
                part_changed = []
                for field in ('statement', 'solution', 'answer'):
                    old = getattr(part, field) or ''
                    rep = {}
                    new = process_field(old, rep)
                    self._collect(rep, stats, problem.id)
                    if new is not None:
                        stats['fields_changed'] += 1
                        stats['tabular_converted'] += rep.get('tabular_converted', 0)
                        stats['env_wrapped'] += rep.get('env_wrapped', 0)
                        if shown < n_examples:
                            shown += 1
                            self._show_example(
                                f'{problem.id}/part {part.label}', field, old, new)
                        if not dry:
                            setattr(part, field, new)
                        part_changed.append(field)
                        problem_changed = True
                if part_changed and not dry:
                    part.save(update_fields=part_changed)

            if problem_changed:
                stats['problems_changed'] += 1
                changed_ids.append(problem.id)

        # ── файлы-списки ──
        if not dry:
            with open(DATA_TABLE_FILE, 'w') as f:
                for pid in sorted(stats['data_tables']):
                    f.write(f'{pid}\n')
            with open(CHANGED_FILE, 'a') as f:
                for pid in changed_ids:
                    f.write(f'{pid}\n')

        mode = 'DRY-RUN' if dry else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'\n[{mode}] задач изменено: {stats["problems_changed"]}, '
            f'полей: {stats["fields_changed"]}, '
            f'tabular→текст: {stats["tabular_converted"]}, '
            f'окружений→$$: {stats["env_wrapped"]}'))
        self.stdout.write(
            f'  настоящих таблиц данных (в {DATA_TABLE_FILE}): '
            f'{len(stats["data_tables"])} задач\n'
            f'  mixed-спанов (пропущено): {len(stats["mixed_spans"])} задач\n'
            f'  wrap пропущен (нет уверенности): {len(stats["wrap_skipped"])} задач\n'
            f'  нечётные $ (поле пропущено): {len(stats["odd_dollar"])} задач\n'
            f'  invariant fail (отброшено): {len(stats["invariant_fails"])} задач')

    def _collect(self, rep, stats, pid):
        if rep.get('data_table'):
            stats['data_tables'].add(pid)
        if rep.get('mixed_span'):
            stats['mixed_spans'].add(pid)
        if rep.get('wrap_skipped'):
            stats['wrap_skipped'].add(pid)
        if rep.get('invariant_fail'):
            stats['invariant_fails'].add(pid)
        if rep.get('odd_dollar_skip'):
            stats['odd_dollar'].add(pid)

    def _show_example(self, pid, field, old, new):
        self.stdout.write(f'\n──── #{pid} [{field}] ────')
        self.stdout.write('ДО:  ' + repr(old[:400]))
        self.stdout.write('ПОСЛЕ: ' + repr(new[:400]))
