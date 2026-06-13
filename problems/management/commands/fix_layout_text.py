"""
Вычистка команд вёрстки из видимого текста (сессия E, этап 3).

По полям statement/solution/answer задач и подпунктов, ВНЕ мат-спанов
($...$, $$...$$, \\(...\\), \\[...\\]):

  - \\textcolor{x}{y}   → y
  - \\fcolorbox{a}{b}{y} → y
  - \\colorbox{a}{y}    → y
  - \\hrulefill          → удаляется
  - строки-комментарии, начинающиеся с % (кроме \\% и %XX hex-кодов URL),
    удаляются целиком — в т.ч. закомментированные дубли задач из Overleaf

Внутри мат-спанов ничего не трогаем (часть команд KaTeX в математике умеет).

Инварианты на поле: чётность $ сохраняется; баланс \\begin/\\end по каждому
окружению не ухудшается (иначе поле откатывается и попадает в отчёт).

Запуск:
    ./venv/bin/python manage.py fix_layout_text --dry-run --examples 20
    ./venv/bin/python manage.py fix_layout_text --source-id 14
    ./venv/bin/python manage.py fix_layout_text             # вся база
"""

import os
import re
from collections import Counter

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/quality_audit'
CHANGED_FILE = os.path.join(REPORT_DIR, 'changed_ids_E.txt')

MATH_SPAN_RE = re.compile(
    r'\\\[(.+?)\\\]|\\\((.+?)\\\)|\$\$(.+?)\$\$|\$([^$]+?)\$', re.DOTALL)

ENV_NAME_RE = re.compile(r'\\(begin|end)\{([a-zA-Z*]+)\}')

# Команды с одним «содержательным» аргументом в конце
UNWRAP_CMDS = (
    ('\\textcolor', 2),   # \textcolor{цвет}{текст} → текст
    ('\\fcolorbox', 3),   # \fcolorbox{рамка}{фон}{текст} → текст
    ('\\colorbox', 2),    # \colorbox{фон}{текст} → текст
)

# Защита от URL-фрагментов: %XX%XX... (hex-пара сразу за hex-парой с %);
# обычные комментарии «%600-3P-t» под защиту не попадают.
# «%∆Q» — нотация процентного изменения (математика), не комментарий.
COMMENT_LINE_RE = re.compile(r'^[ \t]*%(?![0-9A-Fa-f]{2}%)(?!\s*[∆Δ])')

# Спасение ответов из комментариев (только в пустой answer):
# «%Ответ: 80» в любом месте statement; голое число или буквы-варианты —
# только если это ПОСЛЕДНЯЯ строка statement
SALVAGE_ANS_RE = re.compile(r'^\s*%\s*[Оо]твет[:.,\s]*(\S.*?)\s*$', re.MULTILINE)
SALVAGE_NUM_RE = re.compile(r'^%\s*([0-9][^\n]{0,28})$')
SALVAGE_LET_RE = re.compile(r'^%\s*([a-eа-дA-EА-Д][a-eа-дA-EА-Д,;\s]{0,8})$')


def salvage_answer(statement):
    """Текст ответа из %-комментариев statement или None."""
    val = None
    m = SALVAGE_ANS_RE.search(statement)
    if m:
        val = m.group(1)
    else:
        last = statement.rstrip().split('\n')[-1].strip()
        m = SALVAGE_NUM_RE.match(last) or SALVAGE_LET_RE.match(last)
        if m:
            val = m.group(1).strip()
    # непарные $ в спасённом ответе → убираем доллары (читаемый плейн-текст)
    if val and val.replace('\\$', '').count('$') % 2 == 1:
        val = val.replace('$', '')
    return val


def dollar_count(text):
    return text.replace('\\$', '').count('$')


def span_ranges(text):
    masked = text.replace('\\$', '␦␦')
    return [(m.start(), m.end()) for m in MATH_SPAN_RE.finditer(masked)]


def in_span(pos, ranges):
    return any(s <= pos < e for s, e in ranges)


def read_brace_arg(text, i):
    """text[i] == '{' → (содержимое, индекс после закрывающей скобки) | None."""
    if i >= len(text) or text[i] != '{':
        return None
    depth, j = 0, i
    while j < len(text):
        c = text[j]
        if c == '{' and (j == 0 or text[j - 1] != '\\'):
            depth += 1
        elif c == '}' and text[j - 1] != '\\':
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return None


def env_balance(text):
    """Counter: имя окружения → (число begin − число end)."""
    c = Counter()
    for m in ENV_NAME_RE.finditer(text):
        c[m.group(2)] += 1 if m.group(1) == 'begin' else -1
    return c


def process_field(text, report):
    """Новый текст или None."""
    if not text:
        return None
    if not ('%' in text or '\\textcolor' in text or '\\colorbox' in text
            or '\\fcolorbox' in text or '\\hrulefill' in text):
        return None
    if dollar_count(text) % 2 == 1:
        report['odd_dollar_skip'] = True
        return None

    new = text

    # ── 1. строки-комментарии (вне мат-спанов), до неподвижной точки:
    # удаление строк с $$/$ внутри меняет границы спанов и может открыть
    # новые комментарии для удаления ──
    while '%' in new:
        spans = span_ranges(new)
        out_lines = []
        pos = 0
        for line in new.split('\n'):
            keep = True
            if COMMENT_LINE_RE.match(line) and '\\%' not in line.split('%')[0] \
                    and not in_span(pos + len(line) - len(line.lstrip()), spans):
                keep = False
            if keep:
                out_lines.append(line)
            pos += len(line) + 1
        candidate = '\n'.join(out_lines)
        # схлопываем тройные пустые строки, появившиеся после удаления
        candidate = re.sub(r'\n{3,}', '\n\n', candidate)
        if candidate == new:
            break
        new = candidate

    # ── 2. \hrulefill вне мат-спанов ──
    if '\\hrulefill' in new:
        spans = span_ranges(new)
        out, last = [], 0
        for m in re.finditer(r'\\hrulefill[ \t]*', new):
            if in_span(m.start(), spans):
                continue
            out.append(new[last:m.start()])
            last = m.end()
        out.append(new[last:])
        new = ''.join(out)

    # ── 3. \textcolor / \fcolorbox / \colorbox вне мат-спанов ──
    for cmd, n_args in UNWRAP_CMDS:
        while cmd + '{' in new:
            spans = span_ranges(new)
            idx = new.find(cmd + '{')
            replaced = False
            while idx >= 0:
                if not in_span(idx, spans):
                    i = idx + len(cmd)
                    args = []
                    ok = True
                    for _ in range(n_args):
                        got = read_brace_arg(new, i)
                        if got is None:
                            ok = False
                            break
                        args.append(got[0])
                        i = got[1]
                    if ok:
                        new = new[:idx] + args[-1] + new[i:]
                        replaced = True
                        break
                    report['unwrap_fail'] = True
                idx = new.find(cmd + '{', idx + 1)
            if not replaced:
                break

    if new == text:
        return None

    # ── инварианты ──
    # непустое поле не должно опустеть (правило «непустые не перезаписывать»)
    if text.strip() and not new.strip():
        report['invariant_fail'] = True
        return None
    if dollar_count(new) % 2 == 1:
        report['invariant_fail'] = True
        return None
    bal_old, bal_new = env_balance(text), env_balance(new)
    for env, v in bal_new.items():
        if v != 0 and bal_old.get(env, 0) == 0:
            report['invariant_fail'] = True
            return None
    return new


class Command(BaseCommand):
    help = 'Вычистка \\textcolor/\\colorbox/%-комментариев/\\hrulefill из текста'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--examples', type=int, default=0)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        dry = options['dry_run']
        n_examples = options['examples']

        qs = Problem.objects.all().order_by('id').prefetch_related('parts')
        if options['source_id']:
            qs = qs.filter(
                source_references__source_id=options['source_id']).distinct()
        if options['limit']:
            qs = qs[:options['limit']]

        stats = {'problems': 0, 'fields': 0, 'salvaged': 0,
                 'invariant_fails': set(), 'odd_dollar': set(),
                 'unwrap_fail': set()}
        changed_ids = []
        shown = 0

        for problem in qs.iterator(chunk_size=300):
            changed = False
            for field in ('statement', 'solution', 'answer'):
                old = getattr(problem, field) or ''
                rep = {}
                new = process_field(old, rep)
                self._collect(rep, stats, problem.id)
                if new is not None:
                    # спасаем ответ из комментариев ДО их удаления
                    if field == 'statement' and not (problem.answer or '').strip():
                        salv = salvage_answer(old)
                        if salv:
                            stats['salvaged'] += 1
                            if not dry:
                                problem.answer = salv
                                problem.save(update_fields=['answer'])
                    stats['fields'] += 1
                    if shown < n_examples:
                        shown += 1
                        self._show(problem.id, field, old, new)
                    if not dry:
                        setattr(problem, field, new)
                        problem.save(update_fields=[field])
                    changed = True
            for part in problem.parts.all():
                upd = []
                for field in ('statement', 'solution', 'answer'):
                    old = getattr(part, field) or ''
                    rep = {}
                    new = process_field(old, rep)
                    self._collect(rep, stats, problem.id)
                    if new is not None:
                        if field == 'statement' and not (part.answer or '').strip():
                            salv = salvage_answer(old)
                            if salv:
                                stats['salvaged'] += 1
                                if not dry:
                                    part.answer = salv
                                    upd.append('answer')
                        stats['fields'] += 1
                        if shown < n_examples:
                            shown += 1
                            self._show(f'{problem.id}/part {part.label}',
                                       field, old, new)
                        if not dry:
                            setattr(part, field, new)
                        upd.append(field)
                        changed = True
                if upd and not dry:
                    part.save(update_fields=upd)
            if changed:
                stats['problems'] += 1
                changed_ids.append(problem.id)

        if not dry:
            with open(CHANGED_FILE, 'a') as f:
                for pid in changed_ids:
                    f.write(f'{pid}\n')

        mode = 'DRY-RUN' if dry else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'\n[{mode}] задач изменено: {stats["problems"]}, '
            f'полей: {stats["fields"]}, '
            f'спасено ответов из %-комментариев: {stats["salvaged"]}'))
        self.stdout.write(
            f'  нечётные $ (пропущено): {len(stats["odd_dollar"])}\n'
            f'  invariant fail (откат поля): {len(stats["invariant_fails"])}\n'
            f'  unwrap fail (битые скобки): {len(stats["unwrap_fail"])}')

    def _collect(self, rep, stats, pid):
        if rep.get('invariant_fail'):
            stats['invariant_fails'].add(pid)
        if rep.get('odd_dollar_skip'):
            stats['odd_dollar'].add(pid)
        if rep.get('unwrap_fail'):
            stats['unwrap_fail'].add(pid)

    def _show(self, pid, field, old, new):
        i = 0
        while i < min(len(old), len(new)) and old[i] == new[i]:
            i += 1
        self.stdout.write(f'\n──── #{pid} [{field}] ────')
        self.stdout.write('ДО:   ' + repr(old[max(0, i - 60):i + 240]))
        self.stdout.write('ПОСЛЕ: ' + repr(new[max(0, i - 60):i + 240]))
