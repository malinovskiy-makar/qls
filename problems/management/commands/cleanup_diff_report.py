import json
import re
import html as html_lib
import datetime as dt
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

KATEX = "0.16.11"
CDN = "https://cdn.jsdelivr.net/npm/katex@" + KATEX + "/dist/"

CORE_ASSETS = {
    "katex.min.css": CDN + "katex.min.css",
    "katex.min.js": CDN + "katex.min.js",
    "auto-render.min.js": CDN + "contrib/auto-render.min.js",
}
FONT_FAMILIES = [
    "KaTeX_AMS-Regular", "KaTeX_Caligraphic-Bold", "KaTeX_Caligraphic-Regular",
    "KaTeX_Fraktur-Bold", "KaTeX_Fraktur-Regular", "KaTeX_Main-Bold",
    "KaTeX_Main-BoldItalic", "KaTeX_Main-Italic", "KaTeX_Main-Regular",
    "KaTeX_Math-BoldItalic", "KaTeX_Math-Italic", "KaTeX_SansSerif-Bold",
    "KaTeX_SansSerif-Italic", "KaTeX_SansSerif-Regular", "KaTeX_Script-Regular",
    "KaTeX_Size1-Regular", "KaTeX_Size2-Regular", "KaTeX_Size3-Regular",
    "KaTeX_Size4-Regular", "KaTeX_Typewriter-Regular",
]

JUNK_MARKERS = ['t.me', 'vk.com', 'http://', 'https://', '@gmail', '@mail',
                'помоги', 'спасибо', 'решебник', 'наугад', 'заранее благодар']

BADGE_LABELS = {
    'table':  'таблица собрана · сверь цифры',
    'split':  'split на подпункты',
    'hidden': 'скрыта',
    'answer': 'ответ извлечён',
    'forum':  'форум/мусор вычищен',
    'edit':   'правка текста/формул',
}
FILTER_ORDER = ['table', 'split', 'forum', 'answer', 'edit', 'hidden']

ARRAY_RE = re.compile(
    r'(?:\${1,2})\s*\\begin\{array\}\{[^}]*\}(.*?)\\end\{array\}\s*(?:\${1,2})', re.S)


def inline_assets(asset_dir):
    """Прочитать KaTeX с диска для вшивания в страницу.

    Шрифты в CSS подключены относительными путями (url(fonts/…)), поэтому их
    тоже переводим в data:. Без этого вшитый CSS остался бы без шрифтов, и
    формулы отрисовались бы бракованными глифами.
    """
    import base64
    try:
        css = (asset_dir / 'katex.min.css').read_text(encoding='utf-8')
        js = (asset_dir / 'katex.min.js').read_text(encoding='utf-8')
        ar = (asset_dir / 'auto-render.min.js').read_text(encoding='utf-8')
    except OSError:
        return '', '', ''

    fonts_dir = asset_dir / 'fonts'

    def sub_font(m):
        name = m.group(1)
        path = fonts_dir / name
        if not path.exists():
            return m.group(0)
        b64 = base64.b64encode(path.read_bytes()).decode('ascii')
        return 'url(data:font/woff2;base64,' + b64 + ')'

    css = re.sub(r'url\(fonts/([A-Za-z0-9_\-]+\.woff2)\)', sub_font, css)
    # Форматы, которых мы не вшивали, убираем: браузер иначе полезет за ними
    # по несуществующему относительному пути.
    css = re.sub(r",\s*url\(fonts/[^)]+\)\s*format\(['\"](?:woff|truetype)['\"]\)", '', css)
    return css, js, ar


def esc(s):
    return html_lib.escape(s or '', quote=False)


def _unwrap_text(cell):
    return re.sub(r'\\text\{([^{}]*)\}', r'\1', cell)


def cell_html(cell):
    cell = (cell or '').strip()
    if not cell:
        return ''
    unwrapped = _unwrap_text(cell)
    if re.search(r'\\|[_^]', unwrapped):
        return '<span class="tex">$' + unwrapped + '$</span>'
    return esc(unwrapped)


def array_to_table_html(inner):
    inner = inner.replace('\\hline', ' ')
    rows = re.split(r'\\\\', inner)
    out = ['<table class="rebuilt">']
    for row in rows:
        row = row.strip()
        if not row:
            continue
        cells = row.split('&')
        out.append('<tr>' + ''.join('<td>' + cell_html(c) + '</td>' for c in cells) + '</tr>')
    out.append('</table>')
    return ''.join(out)


def render_field(text):
    """Текстовые сегменты → .tex (KaTeX); блоки \\begin{array} → HTML-таблица."""
    text = text or ''
    parts, last = [], 0
    for m in ARRAY_RE.finditer(text):
        before = text[last:m.start()]
        if before.strip():
            parts.append('<span class="tex">' + esc(before) + '</span>')
        parts.append(array_to_table_html(m.group(1)))
        last = m.end()
    tail = text[last:]
    if tail.strip() or not parts:
        parts.append('<span class="tex">' + esc(tail) + '</span>')
    return ''.join(parts)


def field_block(text):
    """Поле в двух видах: как увидит ученик и как лежит в базе.

    Отрендеренный вид идёт первым и виден всегда — по нему судят о качестве
    правки. Сырой текст лежит рядом и открывается переключателем: он нужен
    для разбора, но без рендера правильная разметка формул читается как
    порча, и превью вводит в заблуждение.

    ⚠️ Свои классы только с префиксом qls-. KaTeX внутри .katex-html сам
    раздаёт узлам классы text/mord/base/strut/mfrac/sqrt, а CSS матчит по
    ТОКЕНУ класса — одноимённое правило протащило бы рамку внутрь формулы.
    """
    text = text or ''
    return ('<div class="qls-pair">'
            '<div class="qls-rendered">' + render_field(text) + '</div>'
            '<div class="qls-raw">' + esc(text) + '</div>'
            '</div>')


def task_to_html(task, hidden=False):
    blocks = []
    stmt = (task.get('statement') or '').strip()
    if stmt:
        blocks.append('<div class="lbl">Условие</div><div class="fld">' + field_block(stmt) + '</div>')
    parts = task.get('parts') or []
    if parts:
        items = []
        for p in parts:
            lab = esc((p.get('label') or '').strip())
            st = field_block((p.get('statement') or '').strip())
            an = (p.get('answer') or '').strip()
            an_html = ('<span class="ans">→ ' + field_block(an) + '</span>') if an else ''
            items.append('<div class="part"><span class="plab">' + lab + '</span> ' + st + ' ' + an_html + '</div>')
        blocks.append('<div class="lbl">Подпункты</div>' + ''.join(items))
    sol = (task.get('solution') or '').strip()
    if sol:
        blocks.append('<div class="lbl">Решение</div><div class="fld">' + field_block(sol) + '</div>')
    ans = (task.get('answer') or '').strip()
    if ans:
        blocks.append('<div class="lbl">Ответ</div><div class="fld">' + field_block(ans) + '</div>')
    if not blocks:
        blocks.append('<div class="empty">— пусто —</div>')
    body = ''.join(blocks)
    if hidden:
        body = '<div class="hidden-note">скрыта (status=hidden)</div>' + body
    return body


def field(t, k):
    return (t.get(k) or '') if t else ''


def compute_keys(raw_task, patch_task, merged, hidden):
    keys = []
    raw_text = ' '.join([field(raw_task, 'statement'), field(raw_task, 'solution'), field(raw_task, 'answer')])
    merged_text = ' '.join([merged.get('statement') or '', merged.get('solution') or '', merged.get('answer') or ''])
    for p in (merged.get('parts') or []):
        merged_text += ' ' + (p.get('statement') or '') + ' ' + (p.get('answer') or '')
    if hidden:
        keys.append('hidden')
    if patch_task and 'parts' in patch_task:
        keys.append('split')
    if '\\begin{array}' in merged_text and '\\begin{array}' not in raw_text:
        keys.append('table')
    if patch_task and (patch_task.get('answer') or '').strip() and not field(raw_task, 'answer').strip():
        keys.append('answer')
    rl, ml = raw_text.lower(), merged_text.lower()
    if any(j in rl and j not in ml for j in JUNK_MARKERS):
        keys.append('forum')
    has_text_edit = patch_task and (('statement' in patch_task) or ('solution' in patch_task))
    if has_text_edit and not any(k in ('table', 'answer', 'forum') for k in keys):
        keys.append('edit')
    if not keys:
        keys.append('edit')
    return keys


def sort_key(card):
    keys = card['keys']
    pri = 0 if 'table' in keys else (2 if 'hidden' in keys else 1)
    return (pri, card['id'])


def ensure_assets(asset_dir, stdout):
    """Скачивает KaTeX локально один раз. Возвращает True, если ядро (css/js/auto-render) на месте."""
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / 'fonts').mkdir(exist_ok=True)
    core_ok = True
    for name, url in CORE_ASSETS.items():
        f = asset_dir / name
        if f.exists() and f.stat().st_size > 0:
            continue
        try:
            urllib.request.urlretrieve(url, f)
            stdout('  скачан ' + name)
        except Exception as e:
            core_ok = False
            stdout('  НЕ удалось скачать ' + name + ': ' + str(e))
    for fam in FONT_FAMILIES:
        f = asset_dir / 'fonts' / (fam + '.woff2')
        if f.exists() and f.stat().st_size > 0:
            continue
        try:
            urllib.request.urlretrieve(CDN + 'fonts/' + fam + '.woff2', f)
        except Exception:
            pass  # шрифты не критичны: KaTeX отрендерит с запасным шрифтом
    return core_ok


PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="__CSS__">
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:1100px;margin:0 auto;padding:24px;color:#222;background:#fafaf8;line-height:1.55}
h1{font-size:20px;font-weight:500;margin:0 0 4px}
.sub{color:#777;font-size:13px;margin-bottom:18px}
.bar{position:sticky;top:0;background:#fafaf8;padding:10px 0;border-bottom:0.5px solid #ddd;z-index:5;display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.fbtn{font-size:13px;padding:5px 12px;border-radius:8px;border:0.5px solid #cbcbc4;background:#fff;cursor:pointer;color:#555}
.fbtn.active{background:#E6F1FB;color:#0C447C;border-color:#85B7EB}
.banner{display:flex;gap:8px;align-items:flex-start;background:#FAEEDA;color:#854F0B;border-radius:8px;padding:10px 12px;margin-bottom:16px;font-size:13px}
.diag{background:#FCEBEB;color:#791F1F;border-radius:8px;padding:10px 12px;margin-bottom:16px;font-size:13px;display:none}
.card{background:#fff;border:0.5px solid #e2e2dc;border-radius:12px;padding:14px 18px;margin-bottom:14px}
.chead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.cid{font-weight:500;font-size:15px}
.badge{font-size:12px;padding:3px 9px;border-radius:8px}
.b-table{background:#FAEEDA;color:#854F0B}
.b-split{background:#E6F1FB;color:#0C447C}
.b-hidden{background:#FCEBEB;color:#791F1F}
.b-answer{background:#EAF3DE;color:#27500A}
.b-forum{background:#F1EFE8;color:#444441}
.b-edit{background:#E1F5EE;color:#085041}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:720px){.cols{grid-template-columns:1fr}}
.col{min-width:0}
.coltitle{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#999;margin-bottom:8px}
.col.after{border-left:0.5px solid #eee;padding-left:16px}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#aaa;margin:10px 0 3px}
.fld{white-space:pre-wrap;font-size:14px;word-wrap:break-word}
.fld .tex{white-space:pre-wrap}
table.rebuilt{border-collapse:collapse;margin:8px 0;font-size:13px;white-space:normal}
table.rebuilt td{border:0.5px solid #c9c9c2;padding:4px 9px;text-align:center}
table.rebuilt tr:first-child td{background:#f3f2ec;font-weight:500}
.part{margin:5px 0}
.plab{color:#0C447C;font-weight:500}
.ans{color:#999;font-size:13px}
.empty{color:#bbb;font-style:italic}
.hidden-note{color:#791F1F;font-size:13px;margin-bottom:6px}
.katex .text{font-family:KaTeX_Main,-apple-system,"Segoe UI",sans-serif}
.qls-raw{display:none;white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;line-height:1.45;background:#f6f7f9;border:0.5px solid #dfe3e9;border-radius:6px;padding:6px 9px;margin:5px 0 2px;color:#3a4152;overflow-x:auto}
body.qls-show-raw .qls-raw{display:block}
.qls-rawbtn{border:0.5px solid #c9c9c2;background:#fff;border-radius:8px;padding:5px 12px;font-size:13px;cursor:pointer;margin-left:auto}
body.qls-show-raw .qls-rawbtn{background:#3a4152;color:#fff;border-color:#3a4152}
.bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
</style></head><body>
<h1>__TITLE__</h1>
<div class="sub">__META__ · сгенерировано __TS__</div>
<div id="diag" class="diag">&#x26A0; Формулы не отрисовались: библиотека KaTeX не загрузилась. Открой файл в Chrome, либо перегенерируй отчёт при наличии интернета.</div>
<div class="bar">__FILTERS__</div>
__BANNER__
__CARDS__
<script src="__JS__"></script>
<script src="__AUTORENDER__"></script>
<script>
(function(){
  var rb=document.getElementById('qls-rawbtn');
  if(rb){rb.addEventListener('click',function(){
    var on=document.body.classList.toggle('qls-show-raw');
    rb.textContent=on?'Сырой текст: показан':'Сырой текст: скрыт';
  });}
})();
(function(){
  if(typeof renderMathInElement==='undefined'){
    document.getElementById('diag').style.display='block';
    // Формулы не отрисовались — сырой текст показываем сразу, иначе на
    // экране останется вид, по которому о качестве правки судить нельзя.
    document.body.classList.add('qls-show-raw');
    var rb2=document.getElementById('qls-rawbtn');
    if(rb2){rb2.textContent='Сырой текст: показан';}
    return;
  }
  document.querySelectorAll('.tex').forEach(function(el){
    try{renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false,errorColor:'#cc0000'});}catch(e){}
  });
})();
var btns=document.querySelectorAll('.fbtn'),cards=document.querySelectorAll('.card');
btns.forEach(function(b){b.addEventListener('click',function(){
  btns.forEach(function(x){x.classList.remove('active');});b.classList.add('active');
  var f=b.dataset.filter;
  cards.forEach(function(c){
    c.style.display=(f==='all'||c.dataset.tags.split(' ').indexOf(f)>=0)?'':'none';
  });
});});
</script>
</body></html>"""


class Command(BaseCommand):
    help = "Строит HTML «было/стало» для ревью партии ИИ-чистки ILE (raw + patch → html). KaTeX скачивается локально."

    def add_arguments(self, parser):
        parser.add_argument('--raw', required=True)
        parser.add_argument('--patch', required=True)
        parser.add_argument('--out', required=True)
        parser.add_argument('--ids', default='',
                            help='Только эти id через запятую (точечная сверка).')
        parser.add_argument('--limit', type=int, default=0,
                            help='Взять первые N задач (0 — все).')
        parser.add_argument('--no-inline', action='store_true',
                            help='Не вшивать KaTeX в страницу (ссылки на _assets).')

    def handle(self, *args, **opts):
        raw_path, patch_path, out_path = Path(opts['raw']), Path(opts['patch']), Path(opts['out'])
        for p in (raw_path, patch_path):
            if not p.exists():
                raise CommandError('Файл не найден: ' + str(p))

        asset_dir = out_path.parent / '_assets' / 'katex'
        self.stdout.write('Проверяю KaTeX (локально, скачивается один раз)…')
        core_ok = ensure_assets(asset_dir, lambda m: self.stdout.write(m))
        if core_ok:
            css = '_assets/katex/katex.min.css'
            js = '_assets/katex/katex.min.js'
            autorender = '_assets/katex/auto-render.min.js'
            self.stdout.write(self.style.SUCCESS('KaTeX: локальные файлы готовы.'))
        else:
            css = CDN + 'katex.min.css'
            js = CDN + 'katex.min.js'
            autorender = CDN + 'contrib/auto-render.min.js'
            self.stdout.write(self.style.WARNING('KaTeX: не удалось скачать локально, оставляю CDN-ссылки (нужен интернет в браузере).'))

        raw = json.loads(raw_path.read_text(encoding='utf-8'))
        patch = json.loads(patch_path.read_text(encoding='utf-8'))
        raw_by = {str(r.get('id')): r for r in raw}
        meta = patch.get('meta', {})
        hide = set(str(x) for x in meta.get('hide', []))
        ptasks = patch.get('tasks', {})

        ids = sorted(set(list(ptasks.keys()) + list(hide)), key=lambda x: int(x))
        if opts.get('ids'):
            want = {i.strip() for i in opts['ids'].split(',') if i.strip()}
            missing = want - set(ids)
            if missing:
                self.stdout.write(self.style.WARNING(
                    'В этом патче нет id: ' + ', '.join(sorted(missing))))
            ids = [i for i in ids if i in want]
        if opts.get('limit'):
            ids = ids[:opts['limit']]
        cards, counts = [], {}
        for tid in ids:
            rawt = raw_by.get(tid, {})
            patcht = ptasks.get(tid)
            hidden = tid in hide
            merged = dict(rawt)
            if patcht:
                for k in ('statement', 'solution', 'answer', 'parts'):
                    if k in patcht:
                        merged[k] = patcht[k]
            keys = compute_keys(rawt, patcht, merged, hidden)
            for k in keys:
                counts[k] = counts.get(k, 0) + 1
            badges = ''.join('<span class="badge b-' + k + '">' + esc(BADGE_LABELS[k]) + '</span>' for k in keys)
            card_html = ('<div class="card" data-tags="' + ' '.join(keys) + '">'
                         '<div class="chead"><span class="cid">#' + tid + '</span>' + badges + '</div>'
                         '<div class="cols">'
                         '<div class="col before"><div class="coltitle">было</div>' + task_to_html(rawt) + '</div>'
                         '<div class="col after"><div class="coltitle">стало</div>' + task_to_html(merged, hidden=hidden) + '</div>'
                         '</div></div>')
            cards.append({'id': int(tid), 'keys': keys, 'html': card_html})

        cards.sort(key=sort_key)
        cards_html = ''.join(c['html'] for c in cards)

        filters = ['<button class="fbtn active" data-filter="all">Все · ' + str(len(cards)) + '</button>']
        for k in FILTER_ORDER:
            if counts.get(k):
                filters.append('<button class="fbtn" data-filter="' + k + '">'
                               + esc(BADGE_LABELS[k]) + ' · ' + str(counts[k]) + '</button>')
        # Переключатель сырого текста — справа, отдельно от фильтров: он
        # меняет не выборку карточек, а вид полей.
        filters.append('<button class="qls-rawbtn" id="qls-rawbtn" '
                       'type="button">Сырой текст: скрыт</button>')
        filters_html = ''.join(filters)

        banner_html = ''
        if counts.get('table'):
            banner_html = ('<div class="banner">&#x26A0; ' + str(counts['table'])
                           + ' задач с собранными таблицами вынесены наверх — сверьте числа с исходными картинками, прежде чем применять патч.</div>')

        title = 'Обзор чистки ILE · ' + raw_path.stem
        meta_line = ('партия ' + str(meta.get('batch', '?'))
                     + ' · offset ' + str(meta.get('offset', '?'))
                     + ' · ' + str(len(cards)) + ' карточек · скрыто ' + str(len(hide)))
        ts = dt.datetime.now().strftime('%Y-%m-%d %H:%M')

        # Вшиваем KaTeX внутрь страницы. Иначе отчёт живёт только рядом со
        # своей папкой _assets: стоит переслать или перенести один файл — и
        # формулы не отрисуются, а правильная разметка снова читается как
        # порча. Ровно эта хрупкость и породила жалобу на «сырое превью».
        if core_ok and not opts.get('no_inline'):
            doc_css, doc_js, doc_ar = inline_assets(asset_dir)
            if doc_css:
                PAGE_LOCAL = (PAGE
                              .replace('<link rel="stylesheet" href="__CSS__">',
                                       '<style>' + doc_css + '</style>')
                              .replace('<script src="__JS__"></script>',
                                       '<script>' + doc_js + '</script>')
                              .replace('<script src="__AUTORENDER__"></script>',
                                       '<script>' + doc_ar + '</script>'))
                self.stdout.write(self.style.SUCCESS(
                    'KaTeX вшит в страницу: файл самодостаточен.'))
            else:
                PAGE_LOCAL = PAGE
        else:
            PAGE_LOCAL = PAGE

        doc = (PAGE_LOCAL.replace('__CSS__', css)
                   .replace('__JS__', js)
                   .replace('__AUTORENDER__', autorender)
                   .replace('__TITLE__', esc(title))
                   .replace('__META__', esc(meta_line))
                   .replace('__TS__', ts)
                   .replace('__FILTERS__', filters_html)
                   .replace('__BANNER__', banner_html)
                   .replace('__CARDS__', cards_html))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(doc, encoding='utf-8')

        self.stdout.write(self.style.SUCCESS('Готово: ' + str(out_path)))
        self.stdout.write('Карточек: ' + str(len(cards)) + ' · скрыто: ' + str(len(hide)))
        self.stdout.write('По категориям: ' + ', '.join(k + '=' + str(v) for k, v in sorted(counts.items())))
