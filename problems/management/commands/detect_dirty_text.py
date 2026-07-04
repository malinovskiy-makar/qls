"""
Детектор мусора в опубликованных задачах. Только читает.
Создаёт reports/dirty_text_audit/dirty_report.csv и samples.html.
"""
from typing import Optional, List, Tuple, Dict
import csv
import html as html_lib
import json
import os
import random
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from problems.models import Problem

REPORT_DIR = "reports/dirty_text_audit"
BATCH2_PARSED = "batch2_parsed.jsonl"
BATCH2_ERRORS = "batch2_errors.txt"
SAMPLE_PER_MARKER = 5
SAMPLE_WINDOW = 100
RANDOM_SEED = 2026

# ── Математические регионы — заменяем пробелами той же длины (позиции сохраняются)

_MATH_RE = re.compile(
    r'\$\$[\s\S]{0,3000}?\$\$'
    r'|\$[^\$\n]{0,400}?\$'
    r'|\\\([\s\S]{0,800}?\\\)'
    r'|\\\[[\s\S]{0,3000}?\\\]'
    r'|\\begin\{(?:equation|align|aligned|cases|gather|gathered|multline|array|tabular)\*?\}'
      r'[\s\S]{0,5000}?'
     r'\\end\{(?:equation|align|aligned|cases|gather|gathered|multline|array|tabular)\*?\}'
)

_RU_VOWELS = frozenset('аеёиоуыьъэюяАЕЁИОУЫЬЪЭЮЯ')

_HANGING_WORDS = frozenset({
    'и', 'или', 'а', 'но', 'да', 'же', 'то', 'бы', 'ли',
    'в', 'на', 'по', 'с', 'из', 'от', 'до', 'к', 'у', 'о', 'об',
    'за', 'при', 'без', 'для', 'над', 'под', 'про', 'через',
    'что', 'как', 'если', 'хотя', 'чтобы', 'когда', 'где',
})


def _strip_math(text):
    # type: (str) -> str
    """Заменяет матем. регионы пробелами той же длины — позиции в строке не сдвигаются."""
    return _MATH_RE.sub(lambda m: ' ' * len(m.group()), text)


def _snippet(text, start, end, window=SAMPLE_WINDOW):
    # type: (str, int, int, int) -> Tuple[str, int, int]
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right], start - left, end - left


# ── Маркеры условий (statement / ProblemPart.statement) ──────────────────────

def m_footnote(text):
    # type: (str) -> List[Tuple[int, int]]
    """\\footnote{ — LaTeX-сноска."""
    return [(m.start(), m.end()) for m in re.finditer(r'\\footnote\{', text)]


def m_latex_comment(text):
    # type: (str) -> List[Tuple[int, int]]
    """Строка начинается с %, или }%текст (слипшийся комментарий)."""
    hits = []
    for m in re.finditer(r'(?m)^\s*%', text):
        hits.append((m.start(), m.end()))
    for m in re.finditer(r'\}%\S', text):
        hits.append((m.start(), m.end()))
    return hits[:3]


def m_pseudo_quotes(text):
    # type: (str) -> List[Tuple[int, int]]
    """<< или >> вне математики."""
    stripped = _strip_math(text)
    return [(m.start(), m.end()) for m in re.finditer(r'<<|>>', stripped)]


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


def m_bare_latex_cmds(text):
    # type: (str) -> List[Tuple[int, int]]
    """Голые LaTeX-команды форматирования вне математики."""
    stripped = _strip_math(text)
    # Позиции в stripped == позиции в оригинале (замена той же длиной)
    return [(m.start(), m.end()) for m in _BARE_CMDS_RE.finditer(stripped)]


def m_unpaired_dollars(text):
    # type: (str) -> List[Tuple[int, int]]
    """Нечётное число $ — сломанный рендер формулы."""
    cleaned = re.sub(r'\$\$', '\x00\x00', text)  # убираем $$ парами
    if cleaned.count('$') % 2 == 1:
        idx = cleaned.find('$')
        return [(idx, idx + 1)] if idx >= 0 else [(0, 1)]
    return []


def m_truncated(text):
    # type: (str) -> List[Tuple[int, int]]
    """Условие обрывается: запятая/двоеточие в конце, зависший союз, обрубок слова."""
    t = text.rstrip()
    if not t:
        return []
    end = len(t)
    if t[-1] == ',':
        return [(end - 1, end)]
    if t[-1] == ':':
        return [(end - 1, end)]
    # Последнее слово — зависший союз/предлог
    m = re.search(r'\b([а-яёА-ЯЁ]{1,6})\s*$', t, re.UNICODE)
    if m and m.group(1).lower() in _HANGING_WORDS:
        return [(m.start(), m.end())]
    # Последнее кирилл. слово ≥4 символов без гласных — обрубок
    m = re.search(r'([а-яёА-ЯЁ]{4,})[^\w]*$', t, re.UNICODE)
    if m and not any(c in _RU_VOWELS for c in m.group(1)):
        return [(m.start(), m.end())]
    return []


def m_forum_traces(text):
    # type: (str) -> List[Tuple[int, int]]
    """Форумные следы."""
    pat = re.compile(
        r'помогите|подскажите|не уверен|спасибо заранее',
        re.IGNORECASE | re.UNICODE
    )
    return [(m.start(), m.end()) for m in pat.finditer(text)]


def m_spam_links(text):
    # type: (str) -> List[Tuple[int, int]]
    """Служебный мусор и ссылки-спам."""
    pat = re.compile(
        r'версия для печати|войдите или|t\.me/|vk\.com/',
        re.IGNORECASE | re.UNICODE
    )
    return [(m.start(), m.end()) for m in pat.finditer(text)]


STATEMENT_MARKERS = [
    ('footnote',         m_footnote),
    ('latex_comment',    m_latex_comment),
    ('pseudo_quotes',    m_pseudo_quotes),
    ('bare_latex_cmds',  m_bare_latex_cmds),
    ('unpaired_dollars', m_unpaired_dollars),
    ('truncated',        m_truncated),
    ('forum_traces',     m_forum_traces),
    ('spam_links',       m_spam_links),
]

# ── Маркеры заголовков (title) ────────────────────────────────────────────────

def mt_comma_or_prep(title):
    # type: (str) -> List[Tuple[int, int]]
    """Заголовок заканчивается на запятую или зависший предлог/союз."""
    t = title.rstrip()
    if not t:
        return []
    if t[-1] == ',':
        return [(len(t) - 1, len(t))]
    m = re.search(r'\b([а-яёА-ЯЁ]{1,7})\s*$', t, re.UNICODE)
    if m and m.group(1).lower() in _HANGING_WORDS:
        return [(m.start(), m.end())]
    return []


_TITLE_LATEX_RE = re.compile(r'\\\(|\\\)|\\frac\b|\\sqrt\b|\^|_\{|\$')


def mt_raw_latex(title):
    # type: (str) -> List[Tuple[int, int]]
    """Raw LaTeX в заголовке: \\(, \\), \\frac, ^, _{, $."""
    return [(m.start(), m.end()) for m in _TITLE_LATEX_RE.finditer(title)]


def mt_truncation(title, statement):
    # type: (str, str) -> List[Tuple[int, int]]
    """Заголовок — обрубок первой строки условия (первые 40 символов совпадают)."""
    def norm(s):
        return re.sub(r'\s+', ' ', s or '').strip()
    t40 = norm(title)[:40]
    s40 = norm(statement)[:40]
    if t40 and s40 and s40.startswith(t40):
        return [(0, len(title))]
    return []


def mt_junk(title):
    # type: (str) -> List[Tuple[int, int]]
    """Пустой заголовок / прочерк / «Разное N»."""
    t = (title or '').strip()
    if not t or t in ('—', '-', '–', '−'):
        return [(0, max(1, len(title or ' ')))]
    if re.match(r'^Разное\s*\d*$', t, re.UNICODE):
        return [(0, len(title))]
    return []


TITLE_MARKERS = [
    ('title_comma_or_prep', mt_comma_or_prep),
    ('title_raw_latex',     mt_raw_latex),
    ('title_junk',          mt_junk),
    # title_truncation обрабатывается отдельно (нужен statement)
]

# ── Загрузка статуса Batch 2 ──────────────────────────────────────────────────

def load_batch2_status():
    # type: () -> Dict[int, str]
    status = {}   # type: Dict[int, str]
    if os.path.exists(BATCH2_PARSED):
        with open(BATCH2_PARSED, encoding='utf-8') as f:
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
                data = rec.get('data', {})
                if data.get('_parse_error'):
                    status[pid] = 'parse_error'
                elif data.get('dirty'):
                    status[pid] = 'dirty_true'
                else:
                    status[pid] = 'dirty_false'
    if os.path.exists(BATCH2_ERRORS):
        with open(BATCH2_ERRORS, encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2 and parts[1] in ('errored', 'expired', 'canceled'):
                    cid = parts[0]
                    if cid.startswith('p'):
                        try:
                            status[int(cid[1:])] = 'errored'
                        except ValueError:
                            pass
    return status


# ── Команда ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Детектор мусора в published-задачах. Только чтение. Создаёт отчёты.'

    def add_arguments(self, parser):
        parser.add_argument('--seed', type=int, default=RANDOM_SEED,
                            help='Seed для воспроизводимой выборки примеров в HTML.')

    def handle(self, *args, **opts):
        rng = random.Random(opts['seed'])
        os.makedirs(REPORT_DIR, exist_ok=True)

        self.stdout.write('Загружаем статус Batch 2...')
        b2_status = load_batch2_status()
        self.stdout.write('  загружено статусов: {:,}'.format(len(b2_status)))

        self.stdout.write('Загружаем published-задачи...')
        qs = (Problem.objects
              .filter(status='published')
              .prefetch_related('parts', 'source_references__source')
              .order_by('id'))
        total_pub = qs.count()
        self.stdout.write('  published задач: {:,}'.format(total_pub))

        # per_marker: marker_name -> set(problem_ids)
        per_marker = defaultdict(set)    # type: Dict[str, set]
        # samples_pool: marker_name -> list of Hit
        # Hit = (pid, title60, source_name, field_name, snippet, hl_start, hl_end, b2_status)
        samples_pool = defaultdict(list)  # type: Dict[str, list]
        seen_in_pool = set()              # (marker_name, pid) — по одному примеру на задачу

        source_dirty = Counter()   # type: Counter
        source_total = Counter()   # type: Counter

        csv_rows = []
        problems_with_any = 0

        for p in qs:
            pid = p.id
            title = p.title or ''
            stmt = p.statement or ''
            b2 = b2_status.get(pid, 'not_sent')

            src_name = '(нет источника)'
            for sr in p.source_references.all():
                if sr.source:
                    src_name = sr.source.name
                    break
            source_total[src_name] += 1

            triggered = set()

            def _record(mname, text, hits, field):
                # type: (str, str, List[Tuple[int,int]], str) -> None
                if not hits:
                    return
                per_marker[mname].add(pid)
                triggered.add(mname)
                key = (mname, pid)
                if key not in seen_in_pool:
                    seen_in_pool.add(key)
                    s, e = hits[0]
                    snip, hl_s, hl_e = _snippet(text, s, e)
                    samples_pool[mname].append(
                        (pid, title[:60], src_name, field, snip, hl_s, hl_e, b2)
                    )

            # Проверяем statement
            texts = [('statement', stmt)]
            for part in p.parts.all():
                ps = (part.statement or '').strip()
                if ps:
                    texts.append(('part:{}'.format(part.label), ps))

            for field, text in texts:
                for mname, func in STATEMENT_MARKERS:
                    _record(mname, text, func(text), field)

            # Проверяем title
            if title:
                for mname, func in TITLE_MARKERS:
                    _record(mname, title, func(title), 'title')
                hits_tr = mt_truncation(title, stmt)
                _record('title_truncation', title, hits_tr, 'title')

            if triggered:
                problems_with_any += 1
                source_dirty[src_name] += 1
                csv_rows.append({
                    'id': pid,
                    'title_preview': title[:60],
                    'source': src_name,
                    'batch2_status': b2,
                    'markers': ','.join(sorted(triggered)),
                })

        # ── Консоль ───────────────────────────────────────────────────────────
        W = 62
        self.stdout.write('')
        self.stdout.write('=' * W)
        self.stdout.write('МАРКЕРЫ УСЛОВИЙ (statement + подпункты)')
        self.stdout.write('{:<26} {:>7}  {:>6}'.format('Маркер', 'Задач', '%pub'))
        self.stdout.write('-' * W)
        for mname, _ in STATEMENT_MARKERS:
            cnt = len(per_marker[mname])
            pct = 100.0 * cnt / total_pub if total_pub else 0
            self.stdout.write('{:<26} {:>7,}  {:>5.1f}%'.format(mname, cnt, pct))

        self.stdout.write('')
        self.stdout.write('МАРКЕРЫ ЗАГОЛОВКОВ')
        self.stdout.write('{:<26} {:>7}  {:>6}'.format('Маркер', 'Задач', '%pub'))
        self.stdout.write('-' * W)
        for mname in ['title_comma_or_prep', 'title_raw_latex',
                      'title_truncation', 'title_junk']:
            cnt = len(per_marker[mname])
            pct = 100.0 * cnt / total_pub if total_pub else 0
            self.stdout.write('{:<26} {:>7,}  {:>5.1f}%'.format(mname, cnt, pct))

        pct_total = 100.0 * problems_with_any / total_pub if total_pub else 0
        self.stdout.write('')
        self.stdout.write('=' * W)
        self.stdout.write(
            'Всего published с хотя бы одним маркером: {:,} ({:.1f}%)'.format(
                problems_with_any, pct_total))

        # Топ-15 источников
        self.stdout.write('')
        self.stdout.write('ТОП-15 ИСТОЧНИКОВ (по % грязных)')
        self.stdout.write('{:<46} {:>12}  {:>5}'.format('Источник', 'Гряз/Всего', '%'))
        self.stdout.write('-' * W)
        sorted_src = sorted(
            source_total,
            key=lambda s: -(source_dirty.get(s, 0) / source_total[s])
            if source_total[s] else 0
        )
        for src in sorted_src[:15]:
            tot = source_total[src]
            dirty = source_dirty.get(src, 0)
            pct = 100.0 * dirty / tot if tot else 0
            self.stdout.write(
                '{:<46} {:>5}/{:<5}  {:>4.1f}%'.format(src[:46], dirty, tot, pct))

        # Статус Batch 2 среди задач с маркерами
        self.stdout.write('')
        self.stdout.write('СТАТУС BATCH 2 СРЕДИ ЗАДАЧ С МАРКЕРАМИ')
        self.stdout.write('-' * W)
        b2_counts = Counter(r['batch2_status'] for r in csv_rows)
        total_flagged = sum(b2_counts.values())
        labels = [
            ('dirty_false',  'dirty=False  (ложноотрицат. ИИ)'),
            ('dirty_true',   'dirty=True   (ИИ тоже нашёл)'),
            ('errored',      'errored      (API error)'),
            ('parse_error',  'parse_error  (JSON сломан)'),
            ('not_sent',     'not_sent     (вне охвата батча)'),
        ]
        for key, label in labels:
            cnt = b2_counts.get(key, 0)
            pct = 100.0 * cnt / total_flagged if total_flagged else 0
            self.stdout.write('{:<38} {:>6,}  ({:.1f}%)'.format(label, cnt, pct))

        # ── CSV ───────────────────────────────────────────────────────────────
        csv_path = os.path.join(REPORT_DIR, 'dirty_report.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(
                f, fieldnames=['id', 'title_preview', 'source',
                               'batch2_status', 'markers'])
            writer.writeheader()
            writer.writerows(csv_rows)
        self.stdout.write('\nCSV → {} ({:,} строк)'.format(csv_path, len(csv_rows)))

        # ── HTML ──────────────────────────────────────────────────────────────
        html_path = os.path.join(REPORT_DIR, 'samples.html')
        self._write_html(html_path, samples_pool, per_marker, rng, total_pub, problems_with_any)
        self.stdout.write('HTML → {}'.format(html_path))

    # ── HTML-генератор ────────────────────────────────────────────────────────

    def _write_html(self, path, samples_pool, per_marker, rng, total_pub, total_dirty):
        # type: (str, dict, dict, random.Random, int, int) -> None

        B2_COLORS = {
            'dirty_false': '#d97706',
            'dirty_true':  '#15803d',
            'errored':     '#dc2626',
            'parse_error': '#9333ea',
            'not_sent':    '#6b7280',
        }

        def render_section(group_label, marker_names):
            parts = ['<h2>{}</h2>'.format(html_lib.escape(group_label))]
            for mname in marker_names:
                pool = samples_pool.get(mname, [])
                cnt = len(per_marker.get(mname, set()))
                if not pool:
                    continue
                chosen = rng.sample(pool, min(SAMPLE_PER_MARKER, len(pool)))
                parts.append('<details open>')
                parts.append('<summary><b>{}</b> — {:,} задач</summary>'.format(
                    html_lib.escape(mname), cnt))
                parts.append('<div class="mb">')
                for (pid, title60, src, field, snip, hl_s, hl_e, b2) in chosen:
                    color = B2_COLORS.get(b2, '#6b7280')
                    badge = '<span class="badge" style="background:{}">{}</span>'.format(
                        color, html_lib.escape(b2))
                    before = html_lib.escape(snip[:hl_s])
                    marked = html_lib.escape(snip[hl_s:hl_e])
                    after  = html_lib.escape(snip[hl_e:])
                    parts.append('''
<div class="card">
  <div class="ch">
    <a href="http://127.0.0.1:8000/catalog/{pid}/" target="_blank">#{pid}</a>
    <span class="fb">{field}</span>
    {badge}
    <span class="src">{src}</span>
  </div>
  <div class="ct">{title}</div>
  <pre class="snip">{before}<mark>{marked}</mark>{after}</pre>
</div>'''.format(
                        pid=pid, field=html_lib.escape(field), badge=badge,
                        src=html_lib.escape(src[:50]),
                        title=html_lib.escape(title60),
                        before=before, marked=marked, after=after,
                    ))
                parts.append('</div></details>')
            return '\n'.join(parts)

        stmt_names = [n for n, _ in STATEMENT_MARKERS]
        title_names = ['title_comma_or_prep', 'title_raw_latex',
                       'title_truncation', 'title_junk']

        pct = 100.0 * total_dirty / total_pub if total_pub else 0
        body = '\n'.join([
            render_section('Маркеры условий (statement / подпункты)', stmt_names),
            render_section('Маркеры заголовков', title_names),
        ])

        html_out = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Аудит мусора в задачах</title>
<style>
body{{font-family:monospace;font-size:13px;margin:20px;background:#f9fafb;color:#111}}
h1{{font-size:16px;border-bottom:2px solid #333;padding-bottom:6px;margin-bottom:16px}}
h2{{font-size:13px;margin:20px 0 4px;color:#555;text-transform:uppercase;letter-spacing:.5px}}
details{{margin:6px 0}}
summary{{cursor:pointer;padding:5px 10px;background:#e5e7eb;border-radius:4px;list-style:none}}
summary:hover{{background:#d1d5db}}
.mb{{padding:6px 0 6px 14px}}
.card{{border:1px solid #d1d5db;border-radius:4px;margin:6px 0;padding:8px 12px;background:#fff}}
.ch{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:3px}}
.ch a{{font-weight:700;color:#1d4ed8;text-decoration:none}}
.badge,.fb{{color:#fff;border-radius:3px;padding:1px 6px;font-size:11px}}
.fb{{background:#374151}}
.src{{color:#6b7280;font-size:11px}}
.ct{{font-size:11px;color:#555;font-style:italic;margin-bottom:3px}}
.snip{{background:#f3f4f6;border:1px solid #e5e7eb;padding:6px 8px;font-size:12px;
       white-space:pre-wrap;word-break:break-all;margin:0;border-radius:3px}}
mark{{background:#fde047;color:#000;padding:0 2px;border-radius:2px}}
</style>
</head>
<body>
<h1>Аудит мусора в published-задачах</h1>
<p>С хотя бы одним маркером: <b>{dirty:,}</b> из {total:,} ({pct:.1f}%).<br>
Примеры случайны (seed={seed}). Сырой текст — KaTeX не рендерится, это нормально.</p>
{body}
</body>
</html>""".format(
            dirty=total_dirty, total=total_pub, pct=pct,
            seed=RANDOM_SEED, body=body,
        )

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html_out)
