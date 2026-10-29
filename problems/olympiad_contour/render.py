# -*- coding: utf-8 -*-
"""Проверка отображения: задача так, как её видит ученик.

Страница — служебный просмотр `/_quality/problem/<id>/` (`views.preview`):
тот же контекст и шаблон `catalog/stol.html`, что у `/catalog/problem/<id>/`,
плюс карточка решения. Проверки по HTML ответа сервера (R1–R6) смотрят только
блоки текста задачи — `.math-content` и `#q-solution`, каждый текстовый узел
отдельно, как его обходит авторендер KaTeX:

    R1 katex_error         формула узла не разбирается KaTeX
    R2 img_*               <img> без картинки задачи / картинка не открывается
    R3 raw_*               ученик видит сырое: \\frac, [[FIGURE, **, |---|, «$», &lt;
    R4 table_not_rendered  markdown-таблица задачи не стала <table>
    R5 long_word           «слово» > 60 знаков без пробела (порвёт телефон)
    R6 text_cut            слов условия/пунктов/вариантов из базы нет на странице

Браузер (Playwright, `scripts/olympiad_contour_render.js`), ширины 390 и 1280:

    B0 load_error          страница не открылась
    B1 page_scroll / element_overflow   горизонтальная прокрутка / текст за краем окна
    B2 katex_error_dom / red_text       .katex-error / красный rgb(204,0,0)
    B3 img_not_loaded      naturalWidth = 0
    B4 table_too_wide      таблица шире своего блока
"""
from __future__ import annotations

import collections
import gzip
import html as htmlmod
import json
import os
import random
import re
import subprocess
import time
from html.parser import HTMLParser

from problems.olympiad_contour import bank, katex, run, standard

RENDER_CHECKS = ('R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'B0', 'B1', 'B2', 'B3', 'B4')
RENDER_NAMES = {
    'R1': 'формулы разбираются KaTeX (узлы страницы)',
    'R2': 'картинки страницы есть и открываются',
    'R3': 'нет сырой разметки в тексте',
    'R4': 'таблицы стали таблицами',
    'R5': 'нет слов длиннее 60 знаков',
    'R6': 'текст из базы целиком на странице',
    'B0': 'страница открылась',
    'B1': 'нет горизонтальной прокрутки / вылета за край',
    'B2': 'нет ошибок KaTeX и красного текста в браузере',
    'B3': 'картинки загрузились',
    'B4': 'таблицы не шире блока',
}
WIDTHS = (390, 1280)
LONG_WORD = 60
_FIGURE_SRC = re.compile(r'/catalog/figure/(\d+)\.svg$')


def fail(check, code, details=''):
    return {'check': check, 'code': code, 'details': details}


# ── Разбор HTML ──────────────────────────────────────────────────────────

class _Blocks(HTMLParser):
    """Текстовые узлы, таблицы и картинки внутри блоков текста задачи.

    Блок — самый внешний `.math-content` или `#q-solution`; место блока —
    по ближайшему узнаваемому предку: условие, пункт, вариант теста, решение."""

    VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'source', 'wbr', 'col', 'area', 'base', 'embed'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # (tag, place или None, это блок?)
        self.depth_block = 0
        self.nodes = []          # (место, текст)
        self.tables = 0
        self.imgs = []           # (место, src)
        self.skip = 0

    def _place(self, tag, attrs):
        cls = ' ' + (attrs.get('class') or '') + ' '
        if attrs.get('id') == 'q-solution':
            return 'решение'
        if tag == 'section' and ' stm ' in cls:
            return 'условие'
        if tag == 'li' and ' part ' in cls:
            return 'пункт'
        if ' opt ' in cls:
            return 'вариант'
        return None

    def current_place(self):
        for _tag, place, _blk in reversed(self.stack):
            if place:
                return place
        return '?'

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'template'):
            self.skip += 1
        cls = ' ' + (attrs.get('class') or '') + ' '
        is_block = self.depth_block == 0 and (' math-content ' in cls or attrs.get('id') == 'q-solution')
        if tag in self.VOID:
            if tag == 'img' and self.depth_block:
                self.imgs.append((self.current_place(), attrs.get('src') or ''))
            return
        self.stack.append((tag, self._place(tag, attrs), is_block))
        if is_block:
            self.depth_block += 1
        if tag == 'table' and self.depth_block:
            self.tables += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'template') and self.skip:
            self.skip -= 1
        if tag in self.VOID:
            return
        while self.stack:
            t, _place, blk = self.stack.pop()
            if blk:
                self.depth_block -= 1
            if t == tag:
                break

    def handle_data(self, data):
        if self.depth_block and not self.skip and data.strip():
            self.nodes.append((self.current_place(), data))


def parse_page(html):
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    return parser


# ── R-проверки ──────────────────────────────────────────────────────────

RAW_PATTERNS = (
    ('raw_tex', re.compile(r'\\(?:frac|dfrac|left|right|cdot|times|sqrt|begin|end|text|mathrm|le|ge|'
                           r'alpha|beta|Delta|sum|infty|quad|approx)\b')),
    ('raw_figure_marker', re.compile(r'\[\[FIGURE')),
    ('raw_bold', re.compile(r'\*\*\S|\S\*\*')),
    ('raw_table', re.compile(r'\|\s*:?-{3,}|^\s*\|.+\|\s*$', re.MULTILINE)),
    ('raw_html_entity', re.compile(r'&(?:lt|gt|amp|nbsp|quot|#\d+);')),
    ('raw_html_tag', re.compile(r'</?(?:br|b|i|u|sub|sup|div|span|p|table|tr|td)\s*/?>', re.IGNORECASE)),
)


def r_checks(problem, html, katex_check=katex.check_texts):
    """Провалы R1–R6 одной задачи по HTML страницы."""
    page = parse_page(html)
    out = []
    texts = [t for _p, t in page.nodes]
    results = katex_check(texts, outside=True) if texts else []
    for (place, _t), res in zip(page.nodes, results):
        for err in res.get('errors') or []:
            out.append(fail('R1', 'katex_error', '%s: %s ⟵ %s' % (place, err['problem'][:100], err['tex'][:60])))
        for seg in res.get('currency') or []:
            out.append(fail('R1', 'currency_dollar', '%s: валюта стала формулой «%s»' % (place, seg[:70])))
        for seg in res.get('text_in_math') or []:
            out.append(fail('R1', 'text_in_math', '%s: слова в формуле слипнутся «%s»' % (place, seg[:70])))
        visible = res.get('outside') or ''
        if res.get('unpaired'):
            out.append(fail('R3', 'raw_dollar', '%s: «$» без пары виден как есть' % place))
        for code, pattern in RAW_PATTERNS:
            m = pattern.search(visible)
            if m:
                at = max(0, m.start() - 30)
                out.append(fail('R3', code, '%s: «%s»' % (place, visible[at:m.end() + 30].strip()[:90])))
        for word in visible.split():
            if len(word) > LONG_WORD:
                out.append(fail('R5', 'long_word', '%s: %d знаков «%s…»' % (place, len(word), word[:40])))
                break
    # R2: картинки — только свои строки ProblemFigure, и они открываются
    figs = {f.pk: f for f in problem.figures.all()}
    for place, src in page.imgs:
        m = _FIGURE_SRC.search(src.split('?')[0])
        if not m:
            out.append(fail('R2', 'img_unknown_src', '%s: %s' % (place, src[:80])))
            continue
        fig = figs.get(int(m.group(1)))
        if fig is None:
            out.append(fail('R2', 'img_foreign', '%s: картинка #%s не этой задачи' % (place, m.group(1))))
            continue
        data = bytes(fig.image_data) if fig.image_data else b''
        if data and not bank.image_opens_bytes(data):
            out.append(fail('R2', 'img_broken', '%s: #%d не открывается' % (place, fig.pk)))
        elif not data and not (fig.svg or '').lstrip().startswith('<svg'):
            out.append(fail('R2', 'img_empty', '%s: #%d пустая' % (place, fig.pk)))
    # R4: таблицы
    parts = list(problem.parts.all())
    sources = [problem.statement or '', problem.solution or '', problem.answer or '']
    sources += [p.statement or '' for p in parts] + [p.answer or '' for p in parts]
    expected = sum(len(standard.table_blocks(s)) for s in sources)
    if expected > page.tables:
        out.append(fail('R4', 'table_not_rendered', 'таблиц в тексте %d, на странице %d' % (expected, page.tables)))
    # R6: текст условия, пунктов и вариантов целиком на странице
    db_words = collections.Counter(_words(' '.join([problem.statement or ''] + [p.statement or '' for p in parts])))
    page_words = collections.Counter(_words(' '.join(t for p, t in page.nodes if p != 'решение')))
    missing = [w for w, n in db_words.items() if page_words[w] < n]
    if missing:
        out.append(fail('R6', 'text_cut', 'нет на странице слов: %d (%s)' % (len(missing), ', '.join(missing[:6]))))
    return out


def _words(text):
    text = re.sub(r'\[\[FIGURE:[0-9a-f]+\]\]', ' ', htmlmod.unescape(text or '')).lower().replace('ё', 'е')
    return [w for w in re.findall(r'[а-яa-z]{4,}', text)]


def b_checks(rec):
    """Провалы B0–B4 из записи браузера."""
    if rec.get('error') or rec.get('status') != 200:
        return [fail('B0', 'load_error', rec.get('error') or 'HTTP %s' % rec.get('status'))]
    out = []
    for w in WIDTHS:
        m = (rec.get('widths') or {}).get(str(w)) or (rec.get('widths') or {}).get(w)
        if not m:
            out.append(fail('B0', 'not_measured', '%d px' % w))
            continue
        if m.get('scroll'):
            out.append(fail('B1', 'page_scroll', '%d px: прокрутка на %d px' % (w, m.get('scroll_px', 0))))
        if m.get('overflow'):
            out.append(fail('B1', 'element_overflow', '%d px: за краем %s' % (w, ', '.join(m['overflow'][:3]))))
        if m.get('katex_err'):
            out.append(fail('B2', 'katex_error_dom', '%d px: .katex-error × %d' % (w, m['katex_err'])))
        if m.get('red'):
            out.append(fail('B2', 'red_text', '%d px: красный текст × %d' % (w, m['red'])))
        if m.get('broken_img'):
            out.append(fail('B3', 'img_not_loaded', '%d px: %s' % (w, ', '.join(m['broken_img'][:3]))))
        if m.get('wide_table'):
            out.append(fail('B4', 'table_too_wide', '%d px: таблиц %d' % (w, m['wide_table'])))
    return out


# ── Прогон ───────────────────────────────────────────────────────────────

def _olympiads(out_dir):
    path = os.path.join(out_dir, 'standard_results.jsonl')
    if not os.path.isfile(path):
        return {}
    return {r['problem_id']: r['olympiad'] for r in run.read_jsonl(path) if r['level'] == 'bank'}


def contact_sample(ids, olympiad_of, n, seed=29):
    """n задач поровну по олимпиадам (детерминированно)."""
    by = collections.defaultdict(list)
    for pk in ids:
        by[olympiad_of.get(pk, '?')].append(pk)
    rnd = random.Random(seed)
    for pks in by.values():
        rnd.shuffle(pks)
    names = sorted(by, key=lambda o: run.OLYMPIAD_ORDER.index(o) if o in run.OLYMPIAD_ORDER else 99)
    out, i = [], 0
    while len(out) < n and any(by[o] for o in names):
        o = names[i % len(names)]
        if by[o]:
            out.append(by[o].pop())
        i += 1
    return out


def fetch_with_client(ids, html_dir):
    """Запасной путь без браузера: HTML служебного просмотра тестовым клиентом."""
    from django.test import Client
    client = Client(HTTP_HOST='127.0.0.1')
    os.makedirs(html_dir, exist_ok=True)
    recs = {}
    for pk in ids:
        path = os.path.join(html_dir, '%d.html.gz' % pk)
        if os.path.isfile(path):
            recs[pk] = {'pid': pk, 'status': 200}
            continue
        resp = client.get('/_quality/problem/%d/' % pk)
        recs[pk] = {'pid': pk, 'status': resp.status_code}
        if resp.status_code == 200:
            with gzip.open(path, 'wb') as handle:
                handle.write(resp.content)
    return recs


def run_browser(ids, opts, out_dir, html_dir, shot_dir, shots, stdout):
    bases = [b.strip().rstrip('/') for b in opts['base_url'].split(',') if b.strip()]
    jobs = [{'pid': pk, 'url': '%s/_quality/problem/%d/' % (bases[i % len(bases)], pk)}
            for i, pk in enumerate(ids)]
    out_path = os.path.join(out_dir, 'render_browser.jsonl')
    cfg = {'jobs': jobs, 'out': out_path, 'html_dir': html_dir, 'shot_dir': shot_dir,
           'shots': shots, 'concurrency': max(2, 2 * len(bases)), 'widths': list(WIDTHS)}
    cfg_path = os.path.join(out_dir, 'logs', 'render_jobs.json')
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, 'w', encoding='utf-8') as handle:
        json.dump(cfg, handle)
    script = os.path.join(os.path.dirname(katex.SCRIPT), 'olympiad_contour_render.js')
    proc = subprocess.Popen(['node', script, cfg_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    for line in proc.stdout:
        stdout.write('  браузер: ' + line.rstrip())
        stdout.flush()
    if proc.wait() != 0:
        raise RuntimeError('браузерный прогон упал, см. вывод выше')
    recs = {}
    for rec in run.read_jsonl(out_path):
        if rec['pid'] in recs and recs[rec['pid']].get('error') is None:
            continue
        recs[rec['pid']] = rec
    return recs


def main(opts, stdout):
    from problems.models import Problem

    out_dir = opts['out']
    next_ids = bank.read_ids(opts['next_ids'] or bank.NEXT_API_IDS)
    ids, visible, scope = bank.scope_ids(next_ids)
    if opts.get('ids'):
        ids = [int(x) for x in opts['ids'].split(',') if x.strip()]
    if opts.get('limit'):
        ids = ids[:opts['limit']]
    olympiad_of = _olympiads(out_dir)
    html_dir = os.path.join(out_dir, 'render_html')
    shot_dir = os.path.join(out_dir, 'render_shots')
    shots = contact_sample(ids, olympiad_of, opts.get('contact') or 0)
    stdout.write('отображение: %d задач, браузер: %s' % (len(ids), 'да' if opts.get('browser') else 'нет'))
    started = time.time()
    if opts.get('browser'):
        recs = run_browser(ids, opts, out_dir, html_dir, shot_dir, shots, stdout)
    else:
        recs = fetch_with_client(ids, html_dir)
    stdout.write('страницы получены за %.0f с; проверки R…' % (time.time() - started))
    rows = []
    for start in range(0, len(ids), 300):
        chunk = ids[start:start + 300]
        problems = {p.pk: p for p in Problem.objects.filter(pk__in=chunk).prefetch_related('parts', 'figures')}
        for pk in chunk:
            rec = recs.get(pk) or {'pid': pk, 'error': 'нет записи'}
            fails = []
            path = os.path.join(html_dir, '%d.html.gz' % pk)
            if rec.get('status') == 200 and os.path.isfile(path):
                with gzip.open(path, 'rb') as handle:
                    fails += r_checks(problems[pk], handle.read().decode('utf-8'))
            if opts.get('browser'):
                fails += b_checks(rec)
            elif rec.get('status') != 200:
                fails.append(fail('B0', 'load_error', 'HTTP %s' % rec.get('status')))
            order = {c: i for i, c in enumerate(RENDER_CHECKS)}
            fails.sort(key=lambda f: order.get(f['check'], 99))
            rows.append({'problem_id': pk, 'olympiad': olympiad_of.get(pk, '?'),
                         'visible': pk in visible, 'scope': sorted(scope.get(pk, ())),
                         'passed': not fails,
                         'failed_checks': sorted({f['check'] for f in fails}, key=lambda c: order[c]),
                         'fails': fails, 'browser': rec.get('widths')})
        stdout.write('  R: %d/%d' % (min(start + 300, len(ids)), len(ids)))
        stdout.flush()
    run.write_jsonl(os.path.join(out_dir, 'render_results.jsonl'), rows)
    with open(os.path.join(out_dir, 'render_report.md'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(report_md(rows, browser=bool(opts.get('browser'))))
    if shots:
        with open(os.path.join(out_dir, 'render_contact.html'), 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(contact_html(shots, rows, shot_dir))
    stdout.write('прошли отображение: %d из %d' % (sum(r['passed'] for r in rows), len(rows)))


def report_md(rows, browser):
    lines = ['# Проверка отображения — отчёт (Q1, %s)' % time.strftime('%d.%m.%Y %H:%M'), '',
             'Страница: служебный просмотр `/_quality/problem/<id>/` — шаблон `catalog/stol.html`, '
             'контекст `_problem_context`, решение — партиал `_help_solution.html` в колонке 392 px.',
             'Браузер: %s.' % ('Chromium (Playwright 1.62), ширины 390 и 1280 px' if browser
                               else 'нет (тестовый клиент Django, только R1–R6)'), '']
    checks = [c for c in RENDER_CHECKS if browser or c.startswith('R') or c == 'B0']
    lines += ['| олимпиада | всего | прошли | ' + ' | '.join(checks) + ' |',
              '|---|---|---|' + '---|' * len(checks)]
    by = collections.defaultdict(list)
    for row in rows:
        by[row['olympiad']].append(row)
    tot = collections.Counter()
    for name in sorted(by, key=lambda o: run.OLYMPIAD_ORDER.index(o) if o in run.OLYMPIAD_ORDER else 99):
        rs = by[name]
        c = collections.Counter(ch for r in rs for ch in r['failed_checks'])
        passed = sum(r['passed'] for r in rs)
        tot['total'] += len(rs)
        tot['passed'] += passed
        tot.update(c)
        lines.append('| %s | %d | %d (%s) | %s |' % (name, len(rs), passed, run._pct(passed, len(rs)),
                                                     ' | '.join(str(c[ch]) for ch in checks)))
    lines.append('| **всего** | %d | %d (%s) | %s |' % (tot['total'], tot['passed'],
                                                       run._pct(tot['passed'], tot['total']),
                                                       ' | '.join(str(tot[ch]) for ch in checks)))
    lines += ['', '## Причины с примерами', '']
    codes, ex = collections.Counter(), collections.defaultdict(list)
    for row in rows:
        seen = set()
        for f in row['fails']:
            k = (f['check'], f['code'])
            if k in seen:
                continue
            seen.add(k)
            codes[k] += 1
            if len(ex[k]) < 3:
                ex[k].append('#%d — %s' % (row['problem_id'], f['details'][:120]))
    for (check, code), n in codes.most_common():
        lines.append('- **%s `%s`** (%s): %d — %s' % (check, code, RENDER_NAMES[check], n,
                                                      '; '.join(ex[(check, code)]).replace('|', '¦')))
    return '\n'.join(lines) + '\n'


def contact_html(shots, rows, shot_dir):
    by_id = {r['problem_id']: r for r in rows}
    cells = []
    for pk in shots:
        row = by_id.get(pk) or {}
        bad = ', '.join('%s %s' % (f['check'], f['code']) for f in row.get('fails', [])[:4])
        img = os.path.join(shot_dir, '%d.jpg' % pk)
        src = 'render_shots/%d.jpg' % pk if os.path.isfile(img) else ''
        cells.append(
            '<figure class="%s"><figcaption><b>#%d</b> %s%s<br><span>%s</span></figcaption>%s</figure>' % (
                'bad' if row.get('fails') else 'ok', pk, htmlmod.escape(row.get('olympiad', '')),
                '' if row.get('visible') else ' · скрыта', htmlmod.escape(bad) or 'всё прошло',
                '<a href="%s"><img loading="lazy" src="%s" alt="#%d"></a>' % (src, src, pk) if src else '<p>нет снимка</p>'))
    return ('<!doctype html><meta charset="utf-8"><title>Контактный лист — отображение задач</title>'
            '<style>body{font:13px system-ui;margin:16px;background:#f4f4f2}'
            '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}'
            'figure{margin:0;background:#fff;border:2px solid #cfe8cf;border-radius:6px;overflow:hidden}'
            'figure.bad{border-color:#e8a0a0}figcaption{padding:6px 8px;min-height:44px}'
            'figcaption span{color:#a33}img{width:100%%;height:420px;object-fit:cover;object-position:top}'
            '</style><h1>Контактный лист: %d задач, ширина 390 px (телефон)</h1>'
            '<p>Рамка красная — есть провал проверки отображения. Снимок — верх страницы до 2 600 px; '
            'клик открывает снимок целиком.</p><div class="grid">%s</div>' % (len(shots), ''.join(cells)))
