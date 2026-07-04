"""
Механическая чистка детерминированного LaTeX-мусора в условиях задач.

Чинит три паттерна в Problem.statement и ProblemPart.statement (published):

  1. \\footnote{...}  — удалить целиком (подсчёт вложенных скобок).
  2. <<метка>> в начале условия — удалить вместе с содержимым;
     << / >> в середине текста — заменить на «ёлочки» « и ».
  3. %слово — токен вида %<буква><слово> (слипшийся LaTeX-комментарий) —
     удалить. Не трогаем: 5%, \%, % перед цифрой, %  (пробел после %).

Защита: если после чистки текст < 50% исходного — пропустить задачу.

Без --confirm: HTML-предпросмотр
  reports/dirty_text_audit/junk_preview.html

С --confirm (на будущее): бэкап, запись в базу,
  reports/dirty_text_audit/junk_changed_ids.txt
"""
from typing import Dict, List, Optional, Set, Tuple
import html as html_lib
import os
import re
import shutil
from datetime import datetime

from django.core.management.base import BaseCommand
from problems.models import Problem, ProblemPart

REPORT_DIR = "reports/dirty_text_audit"


# ── Паттерн 1: \\footnote{...} ────────────────────────────────────────────────

def _remove_footnotes(text):
    # type: (str) -> str
    """Удаляет \\footnote{...} подсчётом вложенных {}."""
    result = []
    i = 0
    n = len(text)
    while i < n:
        m = re.search(r'\\footnote\{', text[i:])
        if not m:
            result.append(text[i:])
            break
        start = i + m.start()
        result.append(text[i:start])
        # ищем закрывающую } с учётом вложенности
        depth = 1
        j = start + len(m.group())
        while j < n and depth > 0:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            j += 1
        # j указывает за закрывающую скобку
        i = j
    return ''.join(result)


# ── Паттерн 2: псевдокавычки << >> ───────────────────────────────────────────

_LABEL_AT_START_RE = re.compile(
    r'^(\s*)<<[^>]{0,80}>>\s*',
    re.UNICODE,
)

_MATH_RE = re.compile(
    r'\$\$[\s\S]{0,3000}?\$\$'
    r'|\$[^\$\n]{0,400}?\$'
    r'|\\\([\s\S]{0,800}?\\\)'
    r'|\\\[[\s\S]{0,3000}?\\\]'
)


def _fix_pseudo_quotes(text):
    # type: (str) -> str
    # Сначала удаляем метку-лейбл в начале
    text = _LABEL_AT_START_RE.sub('', text)
    # Заменяем << >> вне математики на «ёлочки»
    # Строим маску «математических» позиций
    mask = [False] * len(text)
    for m in _MATH_RE.finditer(text):
        for k in range(m.start(), m.end()):
            mask[k] = True

    result = []
    i = 0
    n = len(text)
    while i < n:
        if i < n - 1 and text[i:i+2] == '<<' and not mask[i]:
            result.append('«')
            i += 2
        elif i < n - 1 and text[i:i+2] == '>>' and not mask[i]:
            result.append('»')
            i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


# ── Паттерн 3: %слово (слипшийся LaTeX-комментарий) ─────────────────────────

# %<кирилл. или лат. буква><возможно ещё буквы>
# НЕ трогаем: \% (экранированный), %<пробел>, %<цифра>, просто % в конце
_JUNK_COMMENT_RE = re.compile(r'(?<!\\)%([А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z]*)')


def _remove_junk_comments(text):
    # type: (str) -> str
    return _JUNK_COMMENT_RE.sub('', text)


# ── Постобработка ─────────────────────────────────────────────────────────────

def _normalize(text):
    # type: (str) -> str
    # Схлопнуть двойные пробелы, обрезать по краям
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


# ── Основная функция чистки ───────────────────────────────────────────────────

def clean_text(text):
    # type: (str) -> Tuple[str, List[str]]
    """Возвращает (очищенный текст, список применённых паттернов)."""
    original = text
    applied = []  # type: List[str]

    t1 = _remove_footnotes(text)
    if t1 != text:
        applied.append('footnote')
    text = t1

    t2 = _fix_pseudo_quotes(text)
    if t2 != text:
        applied.append('pseudo_quotes')
    text = t2

    t3 = _remove_junk_comments(text)
    if t3 != text:
        applied.append('junk_comment')
    text = t3

    text = _normalize(text)
    if text != original.strip():
        pass  # нормализация не считается отдельным паттерном
    return text, applied


def _check_idempotent(text):
    # type: (str) -> bool
    """True если повторный прогон не меняет текст."""
    cleaned, _ = clean_text(text)
    return cleaned == text


class Command(BaseCommand):
    help = ('Механическая чистка LaTeX-мусора в условиях задач. '
            'Без --confirm — только предпросмотр.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Записать изменения в базу.')

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        os.makedirs(REPORT_DIR, exist_ok=True)
        os.makedirs('backups', exist_ok=True)

        self.stdout.write('Загружаем published-задачи с подпунктами...')
        qs = (Problem.objects
              .filter(status='published')
              .prefetch_related('parts')
              .order_by('id'))
        total_pub = qs.count()
        self.stdout.write('  published: {:,}'.format(total_pub))

        # (pid, field, old_text, new_text, patterns_applied, part_id_or_none)
        hits = []   # type: List[Tuple[int, str, str, str, List[str], Optional[int]]]
        skipped_too_short = []  # type: List[Tuple[int, str]]  # (pid, field)
        pattern_counts = {'footnote': 0, 'pseudo_quotes': 0, 'junk_comment': 0}
        non_idempotent = []  # type: List[Tuple[int, str]]

        for p in qs:
            pid = p.id

            # Проверяем statement
            stmt = p.statement or ''
            if stmt:
                cleaned, applied = clean_text(stmt)
                if cleaned != stmt:
                    if len(cleaned) < 0.5 * len(stmt):
                        skipped_too_short.append((pid, 'statement'))
                    else:
                        for pat in applied:
                            pattern_counts[pat] = pattern_counts.get(pat, 0) + 1
                        hits.append((pid, 'statement', stmt, cleaned, applied, None))
                        if not _check_idempotent(cleaned):
                            non_idempotent.append((pid, 'statement'))

            # Проверяем подпункты
            for part in p.parts.all():
                ps = part.statement or ''
                if not ps:
                    continue
                cleaned, applied = clean_text(ps)
                if cleaned != ps:
                    if len(cleaned) < 0.5 * len(ps):
                        skipped_too_short.append((pid, 'part:{}'.format(part.label)))
                    else:
                        for pat in applied:
                            pattern_counts[pat] = pattern_counts.get(pat, 0) + 1
                        hits.append(
                            (pid, 'part:{}'.format(part.label), ps, cleaned, applied, part.id))
                        if not _check_idempotent(cleaned):
                            non_idempotent.append((pid, 'part:{}'.format(part.label)))

        problems_touched = len({h[0] for h in hits})

        self.stdout.write('')
        self.stdout.write('Затронуто задач: {:,}'.format(problems_touched))
        self.stdout.write('  Полей (statement+parts): {:,}'.format(len(hits)))
        self.stdout.write('По паттернам:')
        for pat, cnt in sorted(pattern_counts.items()):
            self.stdout.write('  {}: {:,}'.format(pat, cnt))
        self.stdout.write('Пропущено (< 50% исходного): {:,}'.format(len(skipped_too_short)))
        self.stdout.write('Идемпотентность: {} НЕ прошли'.format(len(non_idempotent)))
        if non_idempotent:
            for pid, field in non_idempotent[:5]:
                self.stdout.write('  WARN не идемпотентно: #{} {}'.format(pid, field))

        # ── HTML-предпросмотр ─────────────────────────────────────────────────
        html_path = os.path.join(REPORT_DIR, 'junk_preview.html')
        self._write_html(html_path, hits, skipped_too_short, non_idempotent,
                         pattern_counts, total_pub)
        self.stdout.write('\nПредпросмотр → {} ({} строк)'.format(
            html_path, len(hits)))

        if not confirm:
            self.stdout.write('Режим предпросмотра. Для записи добавьте --confirm.')
            return

        # ── Запись ───────────────────────────────────────────────────────────
        db_path = 'db.sqlite3'
        if os.path.exists(db_path):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            bk = os.path.join('backups', 'before_junk_fix_{}.sqlite3'.format(ts))
            shutil.copy2(db_path, bk)
            self.stdout.write('Бэкап → {}'.format(bk))

        stmt_updates = []  # type: List[Problem]
        part_updates = []  # type: List[ProblemPart]
        changed_pids = set()  # type: Set[int]

        stmt_map = {h[0]: h[3] for h in hits if h[1] == 'statement'}
        part_map = {h[5]: h[3] for h in hits if h[5] is not None}

        if stmt_map:
            for p in Problem.objects.filter(id__in=list(stmt_map.keys())):
                p.statement = stmt_map[p.id]
                stmt_updates.append(p)
                changed_pids.add(p.id)
            Problem.objects.bulk_update(stmt_updates, ['statement'])
            self.stdout.write('  Обновлено statement: {:,}'.format(len(stmt_updates)))

        if part_map:
            for part in ProblemPart.objects.filter(id__in=list(part_map.keys())):
                part.statement = part_map[part.id]
                part_updates.append(part)
                changed_pids.add(part.problem_id)
            ProblemPart.objects.bulk_update(part_updates, ['statement'])
            self.stdout.write('  Обновлено parts: {:,}'.format(len(part_updates)))

        ids_path = os.path.join(REPORT_DIR, 'junk_changed_ids.txt')
        with open(ids_path, 'w', encoding='utf-8') as f:
            for pid in sorted(changed_pids):
                f.write('{}\n'.format(pid))
        self.stdout.write('Изменено задач: {:,}. Список → {}'.format(
            len(changed_pids), ids_path))

    def _write_html(self, path, hits, skipped_too_short, non_idempotent,
                    pattern_counts, total_pub):
        # type: (str, list, list, list, dict, int) -> None
        problems_touched = len({h[0] for h in hits})
        non_idem_set = {(pid, fld) for pid, fld in non_idempotent}

        def _diff_html(old, new):
            # type: (str, str) -> str
            """Подсвечивает удалённые фрагменты (до 2000 символов каждого)."""
            old_e = html_lib.escape(old[:2000])
            new_e = html_lib.escape(new[:2000])
            return ('<div class="before">' + old_e + '</div>'
                    '<div class="after">' + new_e + '</div>')

        rows_html = []
        for (pid, field, old_t, new_t, patterns, part_id) in hits:
            idem_warn = ' ⚠️ не идемпотентно' if (pid, field) in non_idem_set else ''
            rows_html.append(
                '<tr>'
                '<td><a href="http://127.0.0.1:8000/catalog/{pid}/" target="_blank">#{pid}</a></td>'
                '<td class="field">{field}{idem}</td>'
                '<td class="pats">{pats}</td>'
                '<td class="diff">{diff}</td>'
                '</tr>'.format(
                    pid=pid,
                    field=html_lib.escape(field),
                    idem=html_lib.escape(idem_warn),
                    pats=html_lib.escape(', '.join(patterns)),
                    diff=_diff_html(old_t, new_t),
                )
            )

        skip_rows = ''.join(
            '<li>#{} поле {}</li>'.format(pid, html_lib.escape(fld))
            for pid, fld in skipped_too_short
        )

        idem_result = ('✅ Все прошли идемпотентность'
                       if not non_idempotent
                       else '⚠️ {} НЕ прошли'.format(len(non_idempotent)))

        html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Предпросмотр: чистка LaTeX-мусора</title>
<style>
body{{font-family:monospace;font-size:12px;margin:20px;background:#f9fafb;color:#111}}
h1{{font-size:15px}}h2{{font-size:12px;margin-top:24px;color:#374151}}
table{{border-collapse:collapse;width:100%;background:#fff;border-radius:4px}}
th{{background:#e5e7eb;padding:5px 8px;text-align:left;font-size:11px}}
td{{padding:4px 8px;border-top:1px solid #f3f4f6;vertical-align:top}}
td.field{{color:#6b7280;white-space:nowrap;font-size:11px}}
td.pats{{color:#1d4ed8;white-space:nowrap;font-size:11px}}
td.diff{{max-width:60vw}}
.before{{background:#fee2e2;padding:4px 6px;border-radius:3px;
         white-space:pre-wrap;word-break:break-all;margin-bottom:3px}}
.after{{background:#dcfce7;padding:4px 6px;border-radius:3px;
        white-space:pre-wrap;word-break:break-all}}
a{{color:#1d4ed8;text-decoration:none;font-weight:700}}
</style>
</head>
<body>
<h1>Предпросмотр чистки LaTeX-мусора</h1>
<p>Всего published: {pub:,}. Затронуто задач: <b>{touched:,}</b> (полей: {fields:,}).</p>
<p>По паттернам: {pat_summary}.</p>
<p>Идемпотентность: <b>{idem}</b>.</p>
<p>Пропущено (&lt;50% исходного): {skip_n}</p>
{skip_list}
<h2>Все затронутые поля (было → стало)</h2>
<table>
<thead><tr><th>ID</th><th>Поле</th><th>Паттерны</th><th>Было → Стало</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>""".format(
            pub=total_pub,
            touched=problems_touched,
            fields=len(hits),
            pat_summary=', '.join(
                '{}: {:,}'.format(k, v) for k, v in sorted(pattern_counts.items())),
            idem=idem_result,
            skip_n=len(skipped_too_short),
            skip_list='<ul>{}</ul>'.format(skip_rows) if skipped_too_short else '',
            rows='\n'.join(rows_html),
        )

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
