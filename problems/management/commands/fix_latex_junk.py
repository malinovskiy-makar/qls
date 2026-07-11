"""
Механическая чистка детерминированного LaTeX-мусора в условиях задач.

Чинит в Problem.statement и ProblemPart.statement (published):

  1. \\footnote{...}  — удалить целиком (подсчёт вложенных скобок).
     ВЫКЛЮЧЕН ПО УМОЛЧАНИЮ (см. сессию «корректировка по итогам ревью») — по
     dry-run выяснилось, что почти все сноски в этой базе содержат не мусор,
     а содержательные учебные подсказки («Hint: возьмите производную…»,
     определения терминов). Удалять их целиком нельзя — сначала нужен
     отдельный перенос текста сноски в скобки рядом с местом сноски. Включить
     можно флагом --include-footnote (для будущей доработки).
  2. <<метка>> в начале условия — удалить вместе с содержимым;
     << / >> в середине текста — заменить на «ёлочки» « и ».
  3. %слово — токен вида %<буква><слово> (слипшийся LaTeX-комментарий).
     Правило (переписано по итогам ревью): если после % до конца текста есть
     перевод строки — вырезается всё от % до этого \n (граница
     LaTeX-комментария однозначна). Если \n после % нет — граница
     неопределима, весь текст этим паттерном НЕ трогается, задача уходит на
     ручной разбор (список собирает preview_fix_latex_junk).
  4. inline_bullet — маркер « • », слипшийся с предыдущим предложением (не в
     начале строки), — перед ним вставляется \n (пробелы/табы перед маркером
     схлопываются). Сам маркер и текст после не трогаем. Уже стоящие в начале
     строки « • » (после \n) не трогаем — идемпотентно.

Защита от математики: паттерны 2 и 3 (<<>> и %слово) не трогают совпадения
внутри $...$ / $$...$$ / \(...\) / \[...\] — там << и % почти всегда часть
содержательной формулы (условие неравенства, знак процента в вычислении), а
не мусор. Общая маска — _math_mask().

Нормализация пробелов ТОЧЕЧНАЯ (по итогам ревью): раньше был безусловный
общий проход _normalize() по всему тексту, который менял текст ДАЖЕ когда ни
один паттерн не сработал (схлопывал пробелы, где угодно, включая
псевдотаблицы с пробелами-отступами — см. #50125 в отчёте ревью). Теперь
общего прохода нет вообще: если ни один паттерн не сработал — текст
возвращается байт-в-байт таким же, каким пришёл. Пробел, оставшийся ровно на
месте вырезания (двойной пробел на стыке), схлопывает сам вырезающий паттерн
локально, только у себя на границе.

Защита: если после чистки текст < 50% исходного — пропустить задачу
(SKIP_SHRINK_RATIO).

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

# Защита от перечистки: если после чистки текст короче этой доли исходного —
# поле пропускается целиком (не считается изменённым). Вынесено в константу,
# чтобы другие команды (preview_fix_latex_junk) могли воспроизвести ту же
# логику для точного совпадения счётчиков с dry-run этой команды.
SKIP_SHRINK_RATIO = 0.5


# ── Паттерн 1: \\footnote{...} ────────────────────────────────────────────────

_FOOTNOTE_START_RE = re.compile(r'\\footnote\{')


def has_footnote(text):
    # type: (str) -> bool
    """Есть ли в тексте \\footnote{...} — независимо от того, включён ли
    паттерн (include_footnote). Используется для очереди «отложено на
    перенос в скобки» (footnote_deferred_ids.txt), которую собирают по всей
    базе, даже когда сам паттерн выключен."""
    return bool(_FOOTNOTE_START_RE.search(text))


def _remove_footnotes(text):
    # type: (str) -> str
    """Удаляет \\footnote{...} подсчётом вложенных {}. Точечно схлопывает
    двойной пробел, если он образовался ровно на месте вырезания (пробел
    был и до \\footnote, и сразу после закрывающей скобки) — только на этом
    стыке, остальной текст не трогается."""
    result = []
    i = 0
    n = len(text)
    while i < n:
        m = _FOOTNOTE_START_RE.search(text[i:])
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
        # точечная чистка стыка: пробел до и после вырезанного — оставляем один
        if result and result[-1].endswith(' ') and j < n and text[j] == ' ':
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


def _math_mask(text):
    # type: (str) -> List[bool]
    """Булева маска по индексам символов: True — позиция внутри формулы
    ($...$, $$...$$, \\(...\\), \\[...\\]). Используется всеми паттернами,
    которым нельзя трогать содержимое формул (<<>> и %-комментарии — знаки
    внутри математики почти всегда содержательные, а не мусор)."""
    mask = [False] * len(text)
    for m in _MATH_RE.finditer(text):
        for k in range(m.start(), m.end()):
            mask[k] = True
    return mask


def _fix_pseudo_quotes(text):
    # type: (str) -> str
    # Сначала удаляем метку-лейбл в начале
    text = _LABEL_AT_START_RE.sub('', text)
    # Заменяем << >> вне математики на «ёлочки»
    mask = _math_mask(text)

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

# Признак слипшегося комментария: % (не экранированный), сразу за ним буква
# без пробела — обычный процент («20%», «20% годовых») так не выглядит,
# пробел или конец строки после % не матчатся. Это только ТРИГГЕР — где
# кончается сам комментарий, решает _remove_junk_comments по границе \n.
_JUNK_COMMENT_RE = re.compile(r'(?<!\\)%([А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z]*)')


def _remove_junk_comments(text):
    # type: (str) -> Tuple[str, bool]
    """Удаляет %-комментарии вне формул.

    Правило границы (переписано по итогам ревью — старая версия вырезала
    только первое слово после %, оставляя огрызки вроде «при вмешательстве»,
    см. reports/fix_latex_junk/approval_summary.md, #4853): LaTeX-комментарий
    тянется от % до конца строки, поэтому вырезаем всё от % до ближайшего
    \n включительно слева (сам \n остаётся — это разделитель, не мусор).
    Пробел перед % (стык вырезания) схлопывается вместе с ним.

    Если у ХОТЯ БЫ ОДНОГО кандидата в этом тексте нет \n после себя — граница
    комментария неопределима (последняя строка текста, конца не видно). В
    этом случае НЕ гадаем: весь текст этим паттерном не трогаем, возвращаем
    (исходный_текст, True) — True здесь значит «нужен ручной разбор».

    Знак % внутри $...$/\\(...\\)/\\[...\\] — почти всегда содержательная
    часть формулы (проценты, доли), не комментарий, поэтому не трогаем.
    """
    mask = _math_mask(text)
    candidates = [m for m in _JUNK_COMMENT_RE.finditer(text) if not mask[m.start()]]
    if not candidates:
        return text, False

    for m in candidates:
        if text.find('\n', m.start()) == -1:
            return text, True  # граница неопределима — весь текст на ручной разбор

    result = []
    last = 0
    for m in candidates:
        strip_start = m.start()
        while strip_start > last and text[strip_start - 1] in ' \t':
            strip_start -= 1  # пробел перед % — тоже часть вырезаемого стыка
        nl = text.find('\n', m.start())
        result.append(text[last:strip_start])
        last = nl
    result.append(text[last:])
    return ''.join(result), False


# ── Паттерн 4: инлайновый маркер « • », слипшийся с текстом ────────────────────

# Символ перед пробелами/табами и маркером должен быть НЕ переводом строки и НЕ
# самим маркером — иначе (а) маркер уже стоит в начале строки, трогать не надо;
# (б) слипшиеся «••» (OCR-мусор) будут раскачиваться между проходами вместо
# стабильного результата — идемпотентность.
_INLINE_BULLET_RE = re.compile(r'([^\n•])[ \t]*•')


def _fix_inline_bullets(text):
    # type: (str) -> str
    return _INLINE_BULLET_RE.sub(r'\1\n•', text)


# ── Основная функция чистки ───────────────────────────────────────────────────

def clean_text(text, include_footnote=False):
    # type: (str, bool) -> Tuple[str, List[str], bool]
    """Возвращает (очищенный текст, список применённых паттернов,
    нужен_ли_ручной_разбор_junk_comment).

    footnote выключен по умолчанию — включается include_footnote=True
    (флаг --include-footnote), см. докстринг модуля.

    Общего прохода по пробелам больше нет: каждый паттерн отвечает за
    точечную чистку стыка на месте собственного вырезания. Если ни один
    паттерн не сработал, text возвращается байт-в-байт таким же, каким пришёл.
    """
    applied = []  # type: List[str]

    if include_footnote:
        t1 = _remove_footnotes(text)
        if t1 != text:
            applied.append('footnote')
        text = t1

    t2 = _fix_pseudo_quotes(text)
    if t2 != text:
        applied.append('pseudo_quotes')
    text = t2

    t3, needs_manual = _remove_junk_comments(text)
    if t3 != text:
        applied.append('junk_comment')
    text = t3

    t4 = _fix_inline_bullets(text)
    if t4 != text:
        applied.append('inline_bullet')
    text = t4

    return text, applied, needs_manual


def _check_idempotent(text, include_footnote=False):
    # type: (str, bool) -> bool
    """True если повторный прогон не меняет текст."""
    cleaned, _, _ = clean_text(text, include_footnote=include_footnote)
    return cleaned == text


class Command(BaseCommand):
    help = ('Механическая чистка LaTeX-мусора в условиях задач. '
            'Без --confirm — только предпросмотр.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Записать изменения в базу.')
        parser.add_argument('--include-footnote', action='store_true',
                            help='Включить паттерн footnote (выключен по умолчанию — '
                                 'см. докстринг модуля, почти все сноски в базе '
                                 'содержательные, не мусор).')

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        include_footnote = opts['include_footnote']
        os.makedirs(REPORT_DIR, exist_ok=True)
        os.makedirs('backups', exist_ok=True)

        self.stdout.write('Загружаем published-задачи с подпунктами...')
        qs = (Problem.objects
              .filter(status='published')
              .prefetch_related('parts')
              .order_by('id'))
        total_pub = qs.count()
        self.stdout.write('  published: {:,}'.format(total_pub))
        if include_footnote:
            self.stdout.write('  --include-footnote передан: паттерн footnote ВКЛЮЧЁН.')
        else:
            self.stdout.write('  Паттерн footnote выключен по умолчанию.')

        # (pid, field, old_text, new_text, patterns_applied, part_id_or_none)
        hits = []   # type: List[Tuple[int, str, str, str, List[str], Optional[int]]]
        skipped_too_short = []  # type: List[Tuple[int, str]]  # (pid, field)
        pattern_counts = {'footnote': 0, 'pseudo_quotes': 0, 'junk_comment': 0,
                         'inline_bullet': 0}
        non_idempotent = []  # type: List[Tuple[int, str]]
        junk_comment_manual_count = 0

        for p in qs:
            pid = p.id

            # Проверяем statement
            stmt = p.statement or ''
            if stmt:
                cleaned, applied, needs_manual = clean_text(stmt, include_footnote=include_footnote)
                if needs_manual:
                    junk_comment_manual_count += 1
                if cleaned != stmt:
                    if len(cleaned) < SKIP_SHRINK_RATIO * len(stmt):
                        skipped_too_short.append((pid, 'statement'))
                    else:
                        for pat in applied:
                            pattern_counts[pat] = pattern_counts.get(pat, 0) + 1
                        hits.append((pid, 'statement', stmt, cleaned, applied, None))
                        if not _check_idempotent(cleaned, include_footnote=include_footnote):
                            non_idempotent.append((pid, 'statement'))

            # Проверяем подпункты
            for part in p.parts.all():
                ps = part.statement or ''
                if not ps:
                    continue
                cleaned, applied, needs_manual = clean_text(ps, include_footnote=include_footnote)
                if needs_manual:
                    junk_comment_manual_count += 1
                if cleaned != ps:
                    if len(cleaned) < SKIP_SHRINK_RATIO * len(ps):
                        skipped_too_short.append((pid, 'part:{}'.format(part.label)))
                    else:
                        for pat in applied:
                            pattern_counts[pat] = pattern_counts.get(pat, 0) + 1
                        hits.append(
                            (pid, 'part:{}'.format(part.label), ps, cleaned, applied, part.id))
                        if not _check_idempotent(cleaned, include_footnote=include_footnote):
                            non_idempotent.append((pid, 'part:{}'.format(part.label)))

        problems_touched = len({h[0] for h in hits})

        self.stdout.write('')
        self.stdout.write('Затронуто задач: {:,}'.format(problems_touched))
        self.stdout.write('  Полей (statement+parts): {:,}'.format(len(hits)))
        self.stdout.write('По паттернам:')
        for pat, cnt in sorted(pattern_counts.items()):
            self.stdout.write('  {}: {:,}'.format(pat, cnt))
        self.stdout.write('Пропущено (< 50% исходного): {:,}'.format(len(skipped_too_short)))
        self.stdout.write('junk_comment: полей на ручной разбор (нет \\n после %): {:,}'.format(
            junk_comment_manual_count))
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
