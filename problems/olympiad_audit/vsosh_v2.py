# -*- coding: utf-8 -*-
"""ВсОШ v2 (сессия Q2, фаза 5): сборка эталона v2, проверки, очередь людям,
сухой план импорта, файл готовности.

Сборка — та же `assemble.assemble` (профиль econ), что у v1, но страницы
берутся по старшинству: `pages_v2` (Q2: terra + Haiku + арбитр Sonnet) →
`pages_claude` (P3: Sonnet/Haiku) → запись GLM. Поверх собранного:
правки второго прохода Opus (фаза 4, ЗЭ/РЭ) и ключи-сетки (фаза 3).

Пишет только в `digitized\\v2\\` (и очередь — в `quality_20261029\\queues\\`);
файлы v1 не трогает: `assemble` пишет в `out_dir`, а недостающие записи
страниц подставляются в памяти (подмена `assemble.load_page` на время сборки),
а не заглушками на диске, как в v1.
"""
from __future__ import annotations

import csv
import re
import json
import os
import subprocess
from collections import Counter, defaultdict

from problems.olympiad_audit import assemble, digitize, vsosh_digitize, vsosh_keys, vsosh_quality
from problems.olympiad_audit import vsosh_verify as vv

STAGES = ('final', 'regional', 'municipal', 'school', 'invitational')
QUEUE_SOURCE = 'q2_vsosh_v2'


def row_key(r):
    return f"{r['event_id']}|{r['number']}|{r.get('task_variant', '')}"


class V2Overlay(vsosh_digitize.ClaudeOverlay):
    """Заплатка страницы: `pages_v2` старше `pages_claude` P3, тот — GLM."""

    def __init__(self, v2_folder, claude_folder):
        super().__init__(claude_folder)
        self.v2 = v2_folder
        self.applied_v2 = 0

    def v2_path(self, page_dir, page):
        return os.path.join(self.v2, page_dir.split('/')[-1], f'p{page}.json')

    def has(self, page_dir, page):
        return os.path.isfile(self.v2_path(page_dir, page)) or os.path.isfile(self.path(page_dir, page))

    def apply(self, page_dir, page, record):
        rec = vv.read_record(self.v2_path(page_dir, page))
        if rec and rec.get('status') == 'ok':
            self.applied_v2 += 1
            return dict(record or {}, blocks=rec.get('blocks') or [], model=rec.get('model'),
                        read_by=rec.get('read_by'), needs_eyes=False)
        return super().apply(page_dir, page, record)


def _patched_load_page(overlay):
    """`assemble.load_page`, которой не нужна заглушка на диске: страницы,
    прочитанной только заплаткой, нет в `pages\\` v1 — её запись берётся
    из заплатки (v1 подставлял пустой json-файл через `ensure_stub`)."""
    original = assemble.load_page

    def load_page(root, page_dir, page, ov=None):
        rec = original(root, page_dir, page, ov)
        if rec is None and ov is not None and ov.has(page_dir, page):
            return ov.apply(page_dir, page, {'page_dir': page_dir, 'page': page, 'blocks': [],
                                             'status': 'claude_only', 'needs_eyes': False})
        return rec
    return original, load_page


def page_model(overlay, v1_root, page_dir, page):
    rec = vv.read_record(overlay.v2_path(page_dir, page))
    if rec and rec.get('status') == 'ok':
        rb = rec.get('read_by') or {}
        return f"{rb.get('primary')}+{rb.get('second')}:{rb.get('decision')}"
    rec = vv.read_record(overlay.path(page_dir, page))
    if rec and rec.get('status') == 'ok':
        return rec.get('model') or 'claude'
    return vsosh_digitize.FLASH_MODEL


def assemble_v2(v1_root, v2_root, log):
    """Сборка v2 → `reference_problems_v2asm.jsonl` (сырое) и строки после
    тех же правил формы, что у v1 (повторы абзацев, валютный $, `\\*`,
    непарные \\left/\\right, повторы ключа, ключ теста из таблицы)."""
    files, meta = vsosh_digitize.load_events(v1_root)
    overlay = V2Overlay(os.path.join(v2_root, 'pages_v2'), os.path.join(v1_root, 'pages_claude'))
    ready = {}
    for eid, ev in files.items():
        total = sum(int(f['pages'] or 0) for f in ev['task_files'])
        done = sum(1 for f in ev['task_files'] for p in range(1, int(f['pages'] or 0) + 1)
                   if vsosh_digitize.transcribe.page_done(
                       os.path.join(v1_root, f['page_dir'], f'p{p}.json')) or overlay.has(f['page_dir'], p))
        if done:
            ready[eid] = (done, total)
    original, patched = _patched_load_page(overlay)
    assemble.load_page = patched
    try:
        summary = assemble.assemble(v1_root, vsosh_digitize.reference_events(meta), [],
                                    'q2', only_events=set(ready), crop=True, overlay=overlay,
                                    out_dir=v2_root, suffix='v2asm', figures_subdir='figures_v2',
                                    profile=assemble.ECON)
    finally:
        assemble.load_page = original
    rows = digitize.read_jsonl(os.path.join(v2_root, 'reference_problems_v2asm.jsonl'))
    pdf_dirs = {x['pdf']: x['page_dir'] for x in digitize.read_jsonl(
        os.path.join(v1_root, 'render_index.jsonl'))}
    out, keys = [], Counter()
    for r in rows:
        m = meta.get(r['event_id'], {})
        for k in vsosh_digitize.EXTRA_KEYS:
            r[k] = m.get(k, '') if k != 'stage' else (m.get('stage') or r.get('stage'))
        r['olympiad_slug'] = 'vseros'
        r['statement_md'], dropped = vsosh_digitize.drop_repeated_paragraphs(r.get('statement_md') or '')
        if dropped:
            r['repeated_paragraphs_dropped'] = dropped
        models = Counter()
        for ref in r.get('source_pages') or []:
            pdf, _, page = ref.rpartition('#p')
            if pdf in pdf_dirs and page.isdigit():
                models[page_model(overlay, v1_root, pdf_dirs[pdf], int(page))] += 1
        r['digitized_by'] = dict(r.get('digitized_by') or {},
                                 model='+'.join(x for x, _ in models.most_common()) or 'q2')
        r['pages_ready'] = list(ready.get(r['event_id'], (0, 0)))
        r['event_partial'] = r['pages_ready'][0] < r['pages_ready'][1]
        r['title'] = vsosh_digitize.official_title(r.get('title'))
        fixed = 0
        for field in ('statement_md', 'solution_md', 'criteria_md', 'answer'):
            r[field], k1 = vsosh_digitize.fix_currency_dollars(r.get(field) or '')
            r[field], k2 = vsosh_digitize.fix_math_star(r[field])
            r[field], k3 = vsosh_digitize.fix_unbalanced_delims(r[field])
            fixed += k1 + k2 + k3
        for part in r.get('parts') or []:
            for fn in (vsosh_digitize.fix_currency_dollars, vsosh_digitize.fix_math_star,
                       vsosh_digitize.fix_unbalanced_delims):
                part['text'], k = fn(part.get('text') or '')
                fixed += k
        if fixed:
            r['form_rules_applied'] = fixed
        key = (r['event_id'], r['number'], r.get('task_variant', ''))
        keys[key] += 1
        if keys[key] > 1:
            r['task_variant'] = (r.get('task_variant') or '') + f'#dup{keys[key]}'
            r.setdefault('flags', []).append('повтор_ключа')
        out.append(r)
    by_event = defaultdict(list)
    for r in out:
        by_event[r['event_id']].append(r)
    filled = 0
    for eid, rs in by_event.items():
        kb = vsosh_digitize.key_blocks(v1_root, files.get(eid, {}),
                                       first_dirs=(os.path.join(v2_root, 'pages_v2'),))
        for kind in ('marked', 'table', 'short'):
            filled += vsosh_digitize.fill_test_keys(rs, kb[kind])
    log(f'сборка v2: {dict(summary)}; заплаток v2 {overlay.applied_v2}, P3 Claude {overlay.applied}; '
        f'ключ из таблицы ответов: {filled}')
    return out


# ── ЗЭ 2008/09: печатная страница ILE ──────────────────────────────────

ILE_2008_NOTE = 'ILE (печатная страница), официальный файл не найден'
ILE_2008_URL = 'https://iloveeconomics.ru/print-all-tasks/3950'


def _html_md(node, images):
    """Кусок HTML ILE → Markdown: абзацы, переносы, списки, таблицы; формулы
    ILE уже в `$…$` и остаются как есть; картинки — в `images` (src)."""
    from bs4 import NavigableString
    out = []

    def inline(el):
        parts = []
        for ch in el.children:
            if isinstance(ch, NavigableString):
                parts.append(str(ch))
            elif ch.name == 'br':
                parts.append('\n')
            elif ch.name == 'img':
                # Рисунок — в поле `figures`, как у вырезок v1 (метки в тексте нет).
                images.append(ch.get('src'))
            elif ch.name in ('strong', 'b'):
                parts.append(f'**{inline(ch).strip()}**')
            elif ch.name in ('em', 'i'):
                parts.append(f'*{inline(ch).strip()}*')
            elif ch.name in ('sub',):
                parts.append(f'$_{{{inline(ch).strip()}}}$')
            elif ch.name in ('sup',):
                parts.append(f'$^{{{inline(ch).strip()}}}$')
            else:
                parts.append(inline(ch))
        return ''.join(parts)

    for el in node.find_all(['p', 'ol', 'ul', 'table']):
        if el.find_parent(['ol', 'ul', 'table']):   # вложенное — уже внутри списка/таблицы
            continue
        if el.name == 'p':
            text = inline(el).replace('\xa0', ' ').strip()
            if text:
                out.append(text)
        elif el.name in ('ol', 'ul'):
            items = [inline(li).strip() for li in el.find_all('li', recursive=False)]
            out.append('\n'.join((f'{i}. ' if el.name == 'ol' else '- ') + t
                                 for i, t in enumerate(items, 1)))
        else:
            rows = [[inline(td).strip().replace('\n', ' ').replace('|', '\\|')
                     for td in tr.find_all(['td', 'th'])] for tr in el.find_all('tr')]
            rows = [r for r in rows if any(r)]
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [''] * (width - len(r)) for r in rows]
                out.append('\n'.join(['| ' + ' | '.join(rows[0]) + ' |',
                                      '|' + '---|' * width] +
                                     ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]))
    if not out:   # текст прямо в div без абзацев (две задачи 2008/09)
        text = inline(node).replace('\xa0', ' ').strip()
        out = [re.sub(r'\n[ \t]*\n+', '\n', text)] if text else []
    return '\n\n'.join(out)


def ile_2008_rows(html_path, figures_dir, fetch=True):
    """ЗЭ 2008/09 из печатной страницы ILE → строки эталона (схема v1).

    Официального файла нет: архив ЦПМ начинается с 2009/10, у rosolymp —
    2010–2012 (сверено в Q2, 29.10). Комплекты — по разделам страницы
    («1-й тур: задачи», «3-й тур: задачи», «Тест»); рисунки — с ILE в
    `figures_v2\\ile_2008_09\\`. Источник помечается `ILE_2008_NOTE`."""
    import re
    import urllib.request

    from bs4 import BeautifulSoup
    with open(html_path, encoding='utf-8') as fh:
        soup = BeautifulSoup(fh.read(), 'lxml')
    rows, section = [], ''
    os.makedirs(figures_dir, exist_ok=True)
    # Список — до разбора: `decompose` заголовка решения иначе ломает обход.
    for el in soup.select('h2, div.task'):
        if el.name == 'h2':
            section = el.get_text(' ', strip=True)
            continue
        head = el.find('h3').get_text(' ', strip=True)
        m = re.match(r'\s*(\d+)\s*[.)]\s*(.*)', head)
        tour = 'test' if 'тест' in section.lower() else (
            'tur' + (re.search(r'(\d)', section).group(1) if re.search(r'(\d)', section) else ''))
        imgs, sol_imgs = [], []
        cond = el.find('div', class_='condition')
        sol = el.find('div', class_='solution_and_answer')
        statement = _html_md(cond, imgs) if cond else ''
        if sol and sol.find('div', class_='title'):
            sol.find('div', class_='title').decompose()
        solution = _html_md(sol, sol_imgs) if sol else ''
        figs = []
        for kind, srcs in (('figures', imgs), ('solution_figures', sol_imgs)):
            for src in srcs:
                name = os.path.basename(src)
                path = os.path.join(figures_dir, name)
                if fetch and not os.path.isfile(path):
                    url = 'https://iloveeconomics.ru' + src if src.startswith('/') else src
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=60) as resp, open(path, 'wb') as out:  # noqa: S310
                        out.write(resp.read())
                # Путь — от папки v2, как у вырезок `assemble` (`figures_v2/…`).
                figs.append((kind, {'path': os.path.relpath(path, os.path.dirname(os.path.dirname(
                    figures_dir))).replace(os.sep, '/'), 'caption': '', 'source': src}))
        number = m.group(1) if m else head
        rows.append({
            'event_id': f'vseros-final-2008-09-ru-all-{tour}',
            'number': ('тест-' + number) if tour == 'test' else number, 'task_variant': '',
            'title': (m.group(2) if m else '').strip(), 'year': 2009, 'academic_year': '2008/09',
            'stage': 'final', 'grade': 'all', 'statement_md': statement, 'parts': [],
            'tables': [], 'figures': [f for k, f in figs if k == 'figures'],
            'solution_figures': [f for k, f in figs if k == 'solution_figures'],
            'solution_md': solution, 'answer': '', 'criteria_md': '', 'max_score': None,
            'source_file': [], 'source_pages': [], 'solution_pages': [], 'criteria_pages': [],
            'official': False, 'source': 'ile_print', 'source_note': ILE_2008_NOTE,
            'source_urls': [ILE_2008_URL], 'region_code': 'ru', 'region_name': '', 'tour': tour,
            'variant': 'all', 'olympiad_slug': 'vseros', 'section': section,
            'digitized_by': {'model': 'ile_html', 'date': '2026-10-29'}, 'check_flags': []})
    return rows


# ── Правки фаз 3 и 4 ───────────────────────────────────────────────────

def apply_recheck(rows, decisions_path):
    """Решения Opus (фаза 4): `fix` — поля заменяются, `keep` — флаги сняты
    вторым проходом, `human` — остаются. → Counter."""
    by_key = {row_key(r): r for r in rows}
    stats = Counter()
    if not os.path.isfile(decisions_path):
        return stats
    for d in digitize.read_jsonl(decisions_path):
        r = by_key.get(d['row'])
        if r is None:
            stats['строка_не_найдена'] += 1
            continue
        r['q2_recheck'] = d['verdict']
        if d['verdict'] == 'fix':
            for field, value in (d.get('fixes') or {}).items():
                r[field] = value
            r['q2_fixed_fields'] = sorted(d['fixes'])
        elif d['verdict'] == 'human':
            r['q2_recheck_note'] = {'reasons': d.get('reasons'), 'why': d.get('why'),
                                    'confidence': d.get('confidence')}
        stats[d['verdict']] += 1
    return stats


def apply_keys(rows, accepted_path, v1_rows):
    """Ключи-сетки (фаза 3) → `answer` тех же вопросов. Строка ищется по ключу
    v1; условие обязано совпасть с v1 (комплект мог пересобраться)."""
    from rapidfuzz import fuzz
    by_key = {row_key(r): r for r in rows}
    v1 = {row_key(r): r for r in v1_rows}
    stats = Counter()
    if not os.path.isfile(accepted_path):
        return stats
    for a in digitize.read_jsonl(accepted_path):
        r, old = by_key.get(a['row']), v1.get(a['row'])
        if r is None or old is None or fuzz.ratio((r.get('statement_md') or '')[:800],
                                                  (old.get('statement_md') or '')[:800]) < 90:
            stats['строка_сдвинулась'] += 1
            continue
        if (r.get('answer') or '').strip():
            stats['ответ_уже_есть'] += 1
            continue
        r['answer'] = a['answer']
        r['answer_from_key_grid'] = a['models']
        stats['ключ'] += 1
    return stats


# ── Проверки ───────────────────────────────────────────────────────────

def check_rows(rows, v1_root, v2_root, human_pages=()):
    """Флаги v2 тем же `vsosh_quality.task_flags`, что у v1, плюс:
    `страница_на_человека` (арбитр не решил), снятые Opus флаги — в
    `check_flags_closed`. KaTeX — отдельно (`katex`)."""
    files = {e['event_id']: e for e in digitize.read_jsonl(os.path.join(v1_root, 'events_files.jsonl'))}
    index = {x['pdf']: x['page_dir'] for x in digitize.read_jsonl(
        os.path.join(v1_root, 'render_index.jsonl'))}
    eyes = vsosh_quality.figure_eyes(os.path.join(v1_root, 'figure_flags_eyes.tsv'))
    eyes.update(vsosh_quality.figure_eyes(os.path.join(v2_root, 'figure_flags_eyes_v2.tsv')))
    human = set(human_pages)
    ev_layers = {}
    for r in rows:
        for f in (r.get('figures') or []) + (r.get('solution_figures') or []):
            if f.get('path') in eyes:
                f['flag'] = eyes[f['path']]
        ev = files.get(r['event_id'], {})
        if r['event_id'] not in ev_layers:
            ev_layers[r['event_id']] = vsosh_quality.event_layers(v1_root, ev)
        has_sol = bool(ev.get('solution_files') or ev.get('criteria_files')) or any(
            f.get('source_kind') == 'tasks+solutions' for f in ev.get('task_files') or [])
        flags = vsosh_quality.task_flags(r, has_sol, vsosh_quality.page_layers(
            v1_root, index, r.get('source_pages')), ev_layers[r['event_id']])
        pages = set()
        for ref in r.get('source_pages') or []:
            pdf, _, page = ref.rpartition('#p')
            if pdf in index:
                pages.add(f'{index[pdf]}/p{page}')
        if pages & human:
            flags.append('страница_на_человека')
        if r.get('q2_recheck') in ('keep', 'fix'):
            closed = [f for f in flags if f in vsosh_recheck_closable()]
            r['check_flags_closed'] = closed
            flags = [f for f in flags if f not in closed]
        r['check_flags'] = sorted(set(flags))
    return rows


def vsosh_recheck_closable():
    """Флаги, которые решение Opus «верно/исправлено» снимает: проверка
    заданий по картинке закрыла именно их (ключ и рисунок — свои фазы)."""
    return {'числа_не_со_страницы', 'расходится_со_слоем', 'тест_без_вариантов', 'нет_решения',
            'пустое_условие', 'пункты_не_разобраны', 'скан_на_глаза', 'расхождение_с_ILE'}


def katex_check(path, out_path):
    script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'vsosh_katex.js')
    subprocess.run(['node', os.path.abspath(script), path, out_path], check=True,  # noqa: S603,S607
                   capture_output=True)
    with open(out_path, encoding='utf-8') as fh:
        return json.load(fh)


def figures_ok(rows, v2_root):
    """Рисунки: файл есть и открывается. → [(ключ строки, путь, причина)]."""
    from PIL import Image
    bad = []
    for r in rows:
        for f in (r.get('figures') or []) + (r.get('solution_figures') or []):
            path = f.get('path') or ''
            full = path if os.path.isabs(path) else os.path.join(v2_root, *path.split('/'))
            if not os.path.isfile(full):
                bad.append((row_key(r), path, 'нет_файла'))
                continue
            try:
                with Image.open(full) as im:
                    im.verify()
            except Exception as exc:  # noqa: BLE001 — любой сбой открытия — брак
                bad.append((row_key(r), path, f'не_открывается: {exc}'[:80]))
    return bad


def test_keys_in_options(rows):
    """Инвариант: у теста с ключом из сетки ответ — среди вариантов. → нарушения."""
    out = []
    for r in rows:
        if not r.get('answer_from_key_grid'):
            continue
        ans = vsosh_keys.norm_answer(r.get('answer'))
        if not vsosh_keys.answer_in_options(ans, vsosh_keys.options(r.get('statement_md') or '')):
            out.append(row_key(r))
    return out


INFO = vsosh_quality.INFO_FLAGS


def flag_share(rows):
    by = defaultdict(lambda: [0, 0])
    for r in rows:
        by[r['stage']][0] += 1
        by[r['stage']][1] += bool(set(r.get('check_flags') or []) - INFO)
    return {s: {'tasks': by[s][0], 'flagged': by[s][1],
                'share': round(by[s][1] / by[s][0], 3) if by[s][0] else None} for s in STAGES}


CHECK_TEXT = {
    'тест_без_ключа': 'у вопроса теста нет ключа; модели прочитали сетку ответов по-разному или не нашли',
    'тест_без_вариантов': 'вопрос теста без вариантов ответа',
    'нет_решения': 'у задачи нет решения и критериев, хотя у комплекта есть файл решений',
    'числа_не_со_страницы': 'в условии есть числа, которых нет в текстовом слое страницы',
    'расходится_со_слоем': 'текст заметно расходится с текстовым слоем страницы',
    'страница_на_человека': 'две модели прочитали страницу по-разному, арбитр Sonnet не решил уверенно',
    'katex': 'формула не разбирается KaTeX',
    'пустое_условие': 'условие пустое', 'пункты_не_разобраны': 'пункты а), б)… не разобраны',
    'скан_на_глаза': 'скан без текстового слоя — сверить с картинкой',
}


def page_images(r, index, v1_root):
    out = []
    for ref in (r.get('source_pages') or []) + (r.get('solution_pages') or []):
        pdf, _, page = ref.rpartition('#p')
        if pdf in index:
            path = os.path.join(v1_root, *index[pdf].split('/'), f'p{page}.png')
            if path not in out:
                out.append(path)
    return out[:6]


def build_queue(rows, v1_root, key_queue, human_pages, path):
    """Очередь людям (общий формат Q1–Q3): строка на (задание, проверка)."""
    index = {x['pdf']: x['page_dir'] for x in digitize.read_jsonl(
        os.path.join(v1_root, 'render_index.jsonl'))}
    kq = {x['row']: x for x in key_queue}
    hp = {x['key']: x for x in human_pages}
    out = []
    for r in rows:
        flags = sorted(set(r.get('check_flags') or []) - INFO)
        for check in flags:
            current = {k: r.get(k) for k in ('statement_md', 'answer', 'solution_md', 'criteria_md')
                       if r.get(k)}
            proposed, conf, details = None, None, CHECK_TEXT.get(check, check)
            if check == 'тест_без_ключа' and row_key(r) in kq:
                x = kq[row_key(r)]
                details += f' ({x["why"]})'
                proposed = {'answer_by_model': {m: (v[0] if v else None)
                                                for m, v in (x.get('replies') or {}).items()}}
            if check == 'числа_не_со_страницы':
                details += ': ' + ', '.join(r.get('numbers_not_on_page') or [])
            if check == 'страница_на_человека':
                notes = [hp[k] for k in hp if any(k.split('/')[1] in p for p in page_images(r, index, v1_root))]
                if notes:
                    details += '; ' + '; '.join(str(d) for n in notes for d in (n.get('differences') or []))[:600]
                    conf = notes[0].get('confidence')
            if r.get('q2_recheck') == 'human':
                note = r.get('q2_recheck_note') or {}
                details += f'; второй проход Opus: {note.get("why") or ""}'[:500]
                conf = note.get('confidence')
            out.append({'item_id': f'{QUEUE_SOURCE}:vseros:{row_key(r)}:{check}',
                        'source': QUEUE_SOURCE, 'olympiad': 'vseros', 'ref_key': row_key(r),
                        'problem_id': None, 'check': check, 'details': details,
                        'page_images': page_images(r, index, v1_root), 'current': current,
                        'proposed': proposed, 'confidence': conf})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    digitize.write_jsonl(path, out)
    return out


def changed_keys(v1_rows, v2_rows, path):
    """`changed_keys_v1_v2.csv`: ключ, этап, что случилось (added / removed /
    changed: поля)."""
    fields = ('statement_md', 'answer', 'solution_md', 'criteria_md', 'parts', 'title')
    a = {row_key(r): r for r in v1_rows}
    b = {row_key(r): r for r in v2_rows}
    n = Counter()
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['ref_key', 'stage', 'change', 'fields'])
        for k in sorted(set(a) | set(b)):
            if k not in a:
                w.writerow([k, b[k]['stage'], 'added', ''])
                n['added'] += 1
            elif k not in b:
                w.writerow([k, a[k]['stage'], 'removed', ''])
                n['removed'] += 1
            else:
                diff = [f for f in fields if (a[k].get(f) or '') != (b[k].get(f) or '')]
                if diff:
                    w.writerow([k, b[k]['stage'], 'changed', ','.join(diff)])
                    n['changed'] += 1
    return dict(n)
