# -*- coding: utf-8 -*-
"""Автономный HTML-пакет проверки: папка с `index.html`, картинками и KaTeX.

Пакет открывается двойным щелчком (Chrome, `file://`), без интернета и без
доступа к базе: задача отрисована заранее тем же рендерером, что и сайт
(`problems/rendering.py` + маркеры рисунков), формулы — вложенный KaTeX с
разделителями и маскировкой долларов сайта (`templates/_katex_dollars.html`
вставляется дословно). Решения рецензент скачивает JSON-файлом; по ходу они
лежат в localStorage браузера.

Рядом с `index.html` — `cards.jsonl` (снимок карточек на момент сборки):
по нему `apply` сверяет, что задача не менялась после выдачи пакета.
"""
from __future__ import annotations

import difflib
import hashlib
import html
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings

from problems.olympiad_review import common

TEMPLATE = Path(__file__).with_name('pack_template.html')
KATEX_DIR = 'katex-0.16.9'
#: Страницы PDF в пакете: WebP, не шире 1500 px — пакет пересылается архивом.
PAGE_WIDTH = 1500
PAGE_QUALITY = 72
_FIGURE = re.compile(r'\[\[FIGURE:([0-9a-f]{8,64})\]\]')
_PAGE = re.compile(r'^(.*[\\/])p(\d+)\.png$')


def katex_dollars_script():
    """<script> из `_katex_dollars.html` дословно (без блока комментария Django)."""
    text = (Path(settings.BASE_DIR) / 'templates' / '_katex_dollars.html').read_text(encoding='utf-8')
    start = text.index('<script>')
    end = text.rindex('</script>') + len('</script>')
    return text[start:end]


class Assets:
    """Картинки пакета: страницы PDF и рисунки задач, без повторов."""

    def __init__(self, root):
        self.root = Path(root)
        (self.root / 'img' / 'pages').mkdir(parents=True, exist_ok=True)
        (self.root / 'img' / 'fig').mkdir(parents=True, exist_ok=True)
        self.pages = {}
        self.missing = []

    def page(self, png):
        if png in self.pages:
            return self.pages[png]
        from PIL import Image
        name = hashlib.sha1(png.encode('utf-8')).hexdigest()[:16] + '.webp'
        rel = f'img/pages/{name}'
        try:
            with Image.open(png) as im:
                im = im.convert('RGB')
                if im.size[0] > PAGE_WIDTH:
                    im = im.resize((PAGE_WIDTH, round(im.size[1] * PAGE_WIDTH / im.size[0])),
                                   Image.LANCZOS)
                im.save(self.root / rel, 'WEBP', quality=PAGE_QUALITY)
        except (OSError, ValueError):
            self.missing.append(png)
            rel = ''
        self.pages[png] = rel
        return rel

    def figure(self, digest, where):
        """Рисунок задачи: файл эталона (путь) или ProblemFigure (`db:<id>`)."""
        rel = f'img/fig/{digest}.png'
        target = self.root / rel
        if target.exists():
            return rel
        data, svg = None, ''
        if where and where.startswith('db:'):
            from problems.models import ProblemFigure
            fig = ProblemFigure.objects.filter(pk=int(where[3:])).first()
            if fig is not None:
                data, svg = (bytes(fig.image_data) if fig.image_data else None), fig.svg or ''
        elif where and os.path.isfile(where):
            data = Path(where).read_bytes()
        if data:
            target.write_bytes(data)
            return rel
        if svg:
            rel = f'img/fig/{digest}.svg'
            (self.root / rel).write_text(svg, encoding='utf-8')
            return rel
        self.missing.append(f'рисунок {digest} ({where})')
        return ''


def neighbours(pngs):
    """Соседние страницы: перед первой и после последней страницы задания."""
    out = []
    for png in pngs[:1]:
        m = _PAGE.match(png)
        if m and int(m.group(2)) > 1:
            out.append(f'{m.group(1)}p{int(m.group(2)) - 1}.png')
    for png in pngs[-1:]:
        m = _PAGE.match(png)
        if m:
            out.append(f'{m.group(1)}p{int(m.group(2)) + 1}.png')
    return [p for p in out if p not in pngs and os.path.isfile(p)]


def render_text(text, fmt, figures, assets):
    """Текст поля → HTML как на сайте: markdown-рендерер сайта и маркеры рисунков."""
    if not text:
        return ''
    if fmt != 'markdown':
        return html.escape(text).replace('\n', '<br>')
    from problems.rendering import render_markdown
    out = render_markdown(text)

    def repl(match):
        digest = match.group(1)
        rel = assets.figure(digest, figures.get(digest)) if digest in figures else ''
        if not rel:
            assets.missing.append(f'маркер рисунка без файла {digest}')
            return '<span class="fig-missing">[рисунок не найден]</span>'
        return f'<img src="{rel}" alt="Рисунок к задаче" class="problem-figure">'
    return _FIGURE.sub(repl, out)


def render_task(fields, fmt, figures, assets):
    if not fields:
        return {}
    return {
        'title': html.escape(fields.get('title') or ''),
        'statement': render_text(fields.get('statement') or '', fmt, figures, assets),
        'parts': [{'label': html.escape(p['label']),
                   'html': render_text(p.get('statement') or '', fmt, figures, assets),
                   'answer': render_text(p.get('answer') or '', fmt, figures, assets)}
                  for p in fields.get('parts') or []],
        'answer': render_text(fields.get('answer') or '', fmt, figures, assets),
        'solution': render_text(fields.get('solution') or '', fmt, figures, assets),
    }


def _tokens(text):
    return re.findall(r'\s+|[^\s]+', text or '')


def diff_html(old, new):
    """Различия исходного текста по словам: <del> было, <ins> стало."""
    a, b = _tokens(old), _tokens(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal':
            out.append(html.escape(''.join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(f'<del>{html.escape("".join(a[i1:i2]))}</del>')
        if j2 > j1:
            out.append(f'<ins>{html.escape("".join(b[j1:j2]))}</ins>')
    return ''.join(out)


def parts_text(parts):
    return '\n'.join(f'{p["label"]}) {p.get("statement") or ""}'
                     + (f'  [ответ: {p["answer"]}]' if p.get('answer') else '') for p in parts or [])


FIELD_NAMES = {'title': 'Заголовок', 'statement': 'Условие', 'parts': 'Пункты / варианты',
               'solution': 'Решение', 'answer': 'Ответ'}


def card_payload(card, fmt, assets):
    """Карточка → данные страницы (HTML отрисован заранее, исходники — для правки)."""
    figures = card.get('figures') or {}
    current = card.get('current') or {}
    proposed = card.get('proposed') or None
    merged = dict(current, **proposed) if proposed else None
    diffs = []
    for name, value in (proposed or {}).items():
        if name == 'parts':
            old, new = parts_text(current.get('parts')), parts_text(value)
        else:
            old, new = current.get(name) or '', value or ''
        diffs.append({'field': FIELD_NAMES.get(name, name), 'html': diff_html(old, new)})
    pages = []
    own = list(card.get('page_images') or [])
    for png in own:
        rel = assets.page(png)
        if rel:
            pages.append({'src': rel, 'label': _page_label(png), 'neighbour': False})
    for png in neighbours(own):
        rel = assets.page(png)
        if rel:
            pages.append({'src': rel, 'label': _page_label(png) + ' (соседняя)', 'neighbour': True})
    pair = card.get('pair_bank')
    head = [registry_name(card.get('olympiad'))]
    if card.get('ref_key'):
        head.append(card['ref_key'])
    if card.get('problem_id'):
        head.append(f'задача #{card["problem_id"]}' + (' · видна на сайте' if card.get('visible')
                                                       else ' · скрыта'))
    else:
        head.append('в банке её ещё нет')
    return {
        'item_id': card['item_id'],
        'kind': card.get('kind', 'fix'),
        'head': ' · '.join(head),
        'checks': card.get('checks') or [],
        'details': card.get('details') or [],
        'pages': pages,
        'fmt': fmt,
        'current': current,
        'current_html': render_task(current, fmt, figures, assets),
        'proposed': proposed,
        'proposed_html': render_task(merged, fmt, figures, assets) if merged else None,
        'diffs': diffs,
        'pair': ({'id': pair['id'], 'source': pair.get('source') or '',
                  'html': render_task(pair['fields'], 'markdown', figures, assets)} if pair else None),
        'confidence': card.get('confidence'),
    }


def registry_name(slug):
    from problems.olympiad_audit import registry
    try:
        return registry.short_name(slug)
    except KeyError:
        return slug or '—'


def _page_label(png):
    m = _PAGE.match(png)
    folder = os.path.basename(os.path.dirname(png))
    return f'стр. {m.group(2)} · файл {folder[:8]}' if m else os.path.basename(png)


def content_format(card):
    """Формат текста карточки: у задачи банка — её собственный, у строки эталона — markdown."""
    if not card.get('problem_id') or card.get('current_from') == 'reference':
        return 'markdown'
    from problems.models import Problem
    return Problem.objects.filter(pk=card['problem_id']).values_list(
        'content_format', flat=True).first() or 'markdown'


def build(cards, out_dir, *, reviewer, pack_id, mode='review', note=''):
    """Собрать пакет. Возвращает {cards, pages, missing}."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f'папка пакета уже есть: {out_dir}')
    out_dir.mkdir(parents=True)
    katex_src = Path(settings.BASE_DIR) / 'static' / 'vendor' / KATEX_DIR
    shutil.copytree(katex_src, out_dir / 'katex', ignore=shutil.ignore_patterns('*.map', 'README*'))
    assets = Assets(out_dir)
    payload = [card_payload(c, content_format(c), assets) for c in cards]
    meta = {'pack_id': pack_id, 'reviewer': reviewer, 'mode': mode, 'note': note,
            'created': datetime.now().isoformat(timespec='seconds'),
            'defects': common.ACCEPTANCE_DEFECTS, 'decisions': list(common.DECISIONS)}
    data = json.dumps({'meta': meta, 'cards': payload}, ensure_ascii=False)
    data = data.replace('</', '<\\/')
    page = TEMPLATE.read_text(encoding='utf-8')
    page = page.replace('<!--__DOLLARS__-->', katex_dollars_script())
    page = page.replace('/*__DATA__*/null', data)
    page = page.replace('__TITLE__', html.escape(f'Проверка: {reviewer}, пакет {pack_id}'))
    (out_dir / 'index.html').write_text(page, encoding='utf-8')
    common.write_jsonl(out_dir / 'cards.jsonl', cards)
    with open(out_dir / 'pack.json', 'w', encoding='utf-8') as handle:
        json.dump(dict(meta, cards=len(cards), items=[c['item_id'] for c in cards],
                       missing=assets.missing), handle, ensure_ascii=False, indent=1)
    return {'cards': len(cards), 'pages': len(assets.pages), 'missing': assets.missing}


def find_chrome():
    """Chrome для самопроверки: `PACK_CHECK_CHROME` или Chromium, поставленный playwright."""
    env = os.environ.get('PACK_CHECK_CHROME')
    if env and os.path.isfile(env):
        return env
    base = Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright'
    found = sorted(base.glob('chromium-*/chrome-win64/chrome.exe')) if base.is_dir() else []
    return str(found[-1]) if found else None


def selfcheck(pack_dir, screenshot=None):
    """Открыть пакет в headless Chrome по file:// (#selfcheck) → {katex_errors, broken, …} или None."""
    import subprocess
    chrome = find_chrome()
    if not chrome:
        return None
    url = (Path(pack_dir) / 'index.html').resolve().as_uri()
    base = [chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--allow-file-access-from-files',
            '--virtual-time-budget=60000', '--window-size=1500,950']
    out = subprocess.run(base + ['--dump-dom', url + '#selfcheck'], capture_output=True,
                         timeout=600, check=False)
    dom = out.stdout.decode('utf-8', 'replace')
    m = re.search(r'<pre id="selfcheck">(.*?)</pre>', dom, re.S)
    if screenshot:
        subprocess.run(base + [f'--screenshot={screenshot}', url], capture_output=True, timeout=300,
                       check=False)
    if not m:
        return {'error': 'самопроверка не отработала', 'stderr': out.stderr.decode('utf-8', 'replace')[-500:]}
    return json.loads(html.unescape(m.group(1)))


def load_index(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def save_index(path, index):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(index, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def next_pack_id(packs_dir, date, reviewer):
    n = 1
    while (Path(packs_dir) / f'{date}_{reviewer}_{n:02d}').exists():
        n += 1
    return f'{date}_{reviewer}_{n:02d}'


def select(cards, index, *, size, olympiads=(), sources=()):
    """Следующие `size` карточек очереди, ещё не выданных ни одному рецензенту."""
    out = []
    for card in cards:
        if card['item_id'] in index:
            continue
        if olympiads and card['olympiad'] not in olympiads:
            continue
        if sources and not set(card.get('sources') or []) & set(sources):
            continue
        out.append(card)
        if len(out) >= size:
            break
    return out
