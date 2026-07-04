"""
Применяет заголовки из batch1_parsed.jsonl к задачам с плохими заголовками.

Кандидаты: published-задачи, чей текущий заголовок попал в категории
  (а) echo_stub, (б) raw_latex, (в) tail_stub, (г) junk
И для которых в batch1_parsed.jsonl есть непустой title_suggestion.

Без --confirm: генерирует HTML-предпросмотр
  reports/dirty_text_audit/titles_preview.html

С --confirm: бэкап в backups/, запись в базу,
  список id → reports/dirty_text_audit/titles_changed_ids.txt

В этой сессии --confirm НЕ запускать.
"""
from typing import Dict, List, Optional, Set, Tuple
import html as html_lib
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime

from django.core.management.base import BaseCommand
from problems.models import Problem

REPORT_DIR = "reports/dirty_text_audit"
BATCH1_PARSED = "batch1_parsed.jsonl"

_HANGING_WORDS = frozenset({
    'и', 'или', 'а', 'но', 'да', 'же', 'то', 'бы', 'ли',
    'в', 'на', 'по', 'с', 'из', 'от', 'до', 'к', 'у', 'о', 'об',
    'за', 'при', 'без', 'для', 'над', 'под', 'про', 'через',
    'что', 'как', 'если', 'хотя', 'чтобы', 'когда', 'где',
})

_MATH_RE = re.compile(
    r'\$\$[\s\S]{0,3000}?\$\$'
    r'|\$[^\$\n]{0,400}?\$'
    r'|\\\([\s\S]{0,800}?\\\)'
    r'|\\\[[\s\S]{0,3000}?\\\]'
)

_TITLE_LATEX_RE = re.compile(r'\\\(|\\\)|\\frac\b|\\sqrt\b|\^|_\{|\$|\{|}')


def _norm(s):
    # type: (str) -> str
    return re.sub(r'\s+', ' ', (s or '')).strip()


def _strip_math(text):
    # type: (str) -> str
    return _MATH_RE.sub(lambda m: ' ' * len(m.group()), text)


def classify_title(title, statement):
    # type: (str, str) -> Optional[str]
    t = (title or '').strip()
    s = statement or ''

    if not t or t in ('—', '-', '–', '−'):
        return 'junk'
    if re.match(r'^Разное\s*\d*$', t, re.UNICODE):
        return 'junk'

    t60 = _norm(t)[:60]
    s60 = _norm(s)[:60]
    if t60 and s60 and s60.startswith(t60):
        return 'echo_stub'

    if _TITLE_LATEX_RE.search(t):
        return 'raw_latex'

    if t[-1] in (',', ':'):
        return 'tail_stub'
    m = re.search(r'\b([а-яёА-ЯЁ]{1,7})\s*$', t, re.UNICODE)
    if m and m.group(1).lower() in _HANGING_WORDS:
        return 'tail_stub'

    return None


def _new_title_ok(new_title):
    # type: (str) -> Optional[str]
    """Возвращает причину пропуска или None если всё хорошо."""
    t = (new_title or '').strip()
    if not t:
        return 'пустой'
    if len(t) > 200:
        return 'длиннее 200 символов'
    if re.search(r'[\$\\]', t):
        return 'содержит $ или \\'
    return None


def load_batch1_titles():
    # type: () -> Dict[int, str]
    """Возвращает dict {problem_id: title_suggestion} из batch1_parsed.jsonl."""
    titles = {}  # type: Dict[int, str]
    if not os.path.exists(BATCH1_PARSED):
        return titles
    with open(BATCH1_PARSED, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            cid = rec.get('custom_id', '')
            if not cid.startswith('p'):
                continue
            try:
                pid = int(cid[1:])
            except ValueError:
                continue
            ts = (rec.get('data', {}).get('title_suggestion') or '').strip()
            if ts:
                titles[pid] = ts
    return titles


class Command(BaseCommand):
    help = ('Применяет заголовки из batch1_parsed.jsonl к задачам с плохими заголовками. '
            'Без --confirm — только предпросмотр.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Записать изменения в базу (по умолчанию только предпросмотр).')

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        os.makedirs(REPORT_DIR, exist_ok=True)
        os.makedirs('backups', exist_ok=True)

        self.stdout.write('Загружаем заголовки из batch1_parsed.jsonl...')
        b1_titles = load_batch1_titles()
        self.stdout.write('  загружено заголовков: {:,}'.format(len(b1_titles)))

        self.stdout.write('Загружаем published-задачи...')
        qs = (Problem.objects
              .filter(status='published')
              .prefetch_related('parts')
              .order_by('id'))
        total_pub = qs.count()
        self.stdout.write('  published: {:,}'.format(total_pub))

        # Категория : List[(id, old_title, new_title, statement_snippet)]
        categories = {
            'echo_stub': [],
            'raw_latex': [],
            'tail_stub': [],
            'junk': [],
        }  # type: Dict[str, List[Tuple[int, str, str, str]]]

        skipped_no_b1 = 0
        skipped_bad_new = []  # type: List[Tuple[int, str, str]]  # (id, new_title, reason)
        candidates_ids = []   # type: List[int]

        for p in qs:
            cat = classify_title(p.title or '', p.statement or '')
            if cat is None:
                continue

            new_title = b1_titles.get(p.id)
            if not new_title:
                skipped_no_b1 += 1
                continue

            reason = _new_title_ok(new_title)
            if reason:
                skipped_bad_new.append((p.id, new_title, reason))
                continue

            stmt_snip = _norm(p.statement or '')[:120]
            categories[cat].append((p.id, p.title or '', new_title, stmt_snip))
            candidates_ids.append(p.id)

        total_candidates = len(candidates_ids)
        self.stdout.write('')
        self.stdout.write('Кандидатов всего: {:,}'.format(total_candidates))
        for cat, rows in categories.items():
            self.stdout.write('  {}: {:,}'.format(cat, len(rows)))
        self.stdout.write('Пропущено (нет в batch1): {:,}'.format(skipped_no_b1))
        self.stdout.write('Пропущено (плохой новый заголовок): {:,}'.format(len(skipped_bad_new)))

        # ── HTML-предпросмотр ─────────────────────────────────────────────────
        html_path = os.path.join(REPORT_DIR, 'titles_preview.html')
        self._write_html(html_path, categories, skipped_bad_new, total_pub)
        self.stdout.write('\nПредпросмотр → {} ({:,} кандидатов)'.format(
            html_path, total_candidates))

        if not confirm:
            self.stdout.write('')
            self.stdout.write('Режим предпросмотра. Для записи добавьте --confirm.')
            return

        # ── Запись ───────────────────────────────────────────────────────────
        # Бэкап SQLite
        db_path = 'db.sqlite3'
        if os.path.exists(db_path):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            bk = os.path.join('backups', 'before_batch1_titles_{}.sqlite3'.format(ts))
            shutil.copy2(db_path, bk)
            self.stdout.write('Бэкап → {}'.format(bk))

        changed = []  # type: List[int]
        for cat, rows in categories.items():
            ids_in_cat = [r[0] for r in rows]
            new_map = {r[0]: r[2] for r in rows}
            batch = Problem.objects.filter(id__in=ids_in_cat)
            for p in batch:
                p.title = new_map[p.id]
            Problem.objects.bulk_update(batch, ['title'])
            changed.extend(ids_in_cat)
            self.stdout.write('  {} обновлено: {:,}'.format(cat, len(ids_in_cat)))

        ids_path = os.path.join(REPORT_DIR, 'titles_changed_ids.txt')
        with open(ids_path, 'w', encoding='utf-8') as f:
            for pid in sorted(changed):
                f.write('{}\n'.format(pid))
        self.stdout.write('\nИзменено: {:,}. Список → {}'.format(len(changed), ids_path))

    def _write_html(self, path, categories, skipped_bad_new, total_pub):
        # type: (str, dict, list, int) -> None
        total = sum(len(v) for v in categories.values())
        cat_labels = {
            'echo_stub': '(а) echo_stub — заголовок = начало условия',
            'raw_latex': '(б) raw_latex — LaTeX в заголовке',
            'tail_stub': '(в) tail_stub — обрубок по хвосту',
            'junk':      '(г) junk — пусто / прочерк / Разное N',
        }

        sections = []
        for cat in ['echo_stub', 'raw_latex', 'tail_stub', 'junk']:
            rows = categories[cat]
            if not rows:
                continue
            label = cat_labels[cat]
            trs = []
            for (pid, old_t, new_t, stmt_snip) in rows:
                trs.append(
                    '<tr>'
                    '<td><a href="http://127.0.0.1:8000/catalog/{pid}/" target="_blank">#{pid}</a></td>'
                    '<td class="old">{old}</td>'
                    '<td class="new">{new}</td>'
                    '<td class="cat">{cat}</td>'
                    '<td class="snip">{snip}</td>'
                    '</tr>'.format(
                        pid=pid,
                        old=html_lib.escape(old_t[:120]),
                        new=html_lib.escape(new_t[:120]),
                        cat=html_lib.escape(cat),
                        snip=html_lib.escape(stmt_snip),
                    )
                )
            sections.append(
                '<h2>{label} — {n:,} задач</h2>'
                '<table><thead><tr>'
                '<th>ID</th><th>Заголовок сейчас</th><th>Из Батча 1</th>'
                '<th>Категория</th><th>Условие (начало)</th>'
                '</tr></thead><tbody>{rows}</tbody></table>'.format(
                    label=html_lib.escape(label),
                    n=len(rows),
                    rows='\n'.join(trs),
                )
            )

        # Пропущенные плохие заголовки
        if skipped_bad_new:
            skip_rows = ''.join(
                '<tr><td>#{}</td><td>{}</td><td>{}</td></tr>'.format(
                    pid,
                    html_lib.escape((new_t or '')[:120]),
                    html_lib.escape(reason),
                )
                for pid, new_t, reason in skipped_bad_new
            )
            sections.append(
                '<h2>Пропущены (плохой новый заголовок) — {:,}</h2>'
                '<table><thead><tr><th>ID</th><th>Предложенный заголовок</th>'
                '<th>Причина пропуска</th></tr></thead>'
                '<tbody>{}</tbody></table>'.format(len(skipped_bad_new), skip_rows)
            )

        html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Предпросмотр: заголовки из Батча 1</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer
  src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{{delimiters:[
    {{left:'$$',right:'$$',display:true}},
    {{left:'$',right:'$',display:false}}
  ]}})"></script>
<style>
body{{font-family:system-ui,sans-serif;font-size:13px;margin:20px;background:#f9fafb;color:#111}}
h1{{font-size:16px}}h2{{font-size:13px;margin-top:28px;color:#374151}}
table{{border-collapse:collapse;width:100%;margin-top:8px;background:#fff;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px #0001}}
th{{background:#e5e7eb;padding:6px 10px;text-align:left;font-weight:600;white-space:nowrap}}
td{{padding:5px 10px;border-top:1px solid #f3f4f6;vertical-align:top}}
td.old{{color:#b91c1c;max-width:260px;word-break:break-word}}
td.new{{color:#166534;max-width:260px;word-break:break-word}}
td.cat{{color:#6b7280;white-space:nowrap}}
td.snip{{color:#555;max-width:320px;font-size:11px;word-break:break-word}}
a{{color:#1d4ed8;text-decoration:none;font-weight:700}}
</style>
</head>
<body>
<h1>Предпросмотр замены заголовков (Батч 1)</h1>
<p>Всего кандидатов: <b>{total:,}</b> из {pub:,} published.
KaTeX-рендер включён.</p>
{sections}
</body>
</html>""".format(
            total=total,
            pub=total_pub,
            sections='\n'.join(sections),
        )

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
