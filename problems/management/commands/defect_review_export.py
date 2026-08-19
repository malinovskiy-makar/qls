"""defect_review_export — офлайн-пакеты разбора ЗАБРАКОВАННЫХ задач.

⚠️ ТОЛЬКО ЧИТАЕТ. В базу не пишет ничего.

По пакету на источник: задачи, у которых человек нашёл брак. На экране два
столбца: слева «ДО» (текст до ПЕРВОЙ применённой правки, из индекса
problems/before_index.py), справа «ПОСЛЕ» (текущее состояние базы).

⚠️ ОБА СТОЛБЦА ОТРЕНДЕРЕНЫ по умолчанию, ровно тем же конвейером, что и
боевая страница: маскировка «\\$» вне формул -> renderMathInElement с теми же
разделителями и в том же порядке ($$ раньше $) -> возврат долларов. Второй
конвейер здесь не заводится: разойдясь с боевым, он показывал бы не то, что
увидит ученик. Сырой текст открывается кнопкой, не по умолчанию — на сыром
тексте правильная разметка формул читается как порча.

⚠️ ЕСЛИ СНИМКА «ДО» НЕТ — так и написано, «версия ДО не найдена». Текущий
текст в левый столбец НЕ подставляется: это превратило бы столбец в копию
правого, и разбор потерял бы смысл.

⚠️ Свои CSS-классы только с префиксом qls-. KaTeX внутри .katex-html сам
раздаёт узлам классы text/mord/base/strut/mfrac/sqrt, а CSS матчит по ТОКЕНУ
класса — одноимённое правило протащило бы рамку прямо в формулу.

ЦИТАТЫ. Ревьюер выделяет кусок текста мышью и жмёт кнопку «Привязать к
выделенному» (или клавишу C — по event.code, а не по букве: буква зависит от
раскладки). Цитата и комментарий к ней уезжают в вердикт; цитат к одной
задаче может быть несколько. Работает и на отрендеренном виде, и на исходнике.

    venv\\Scripts\\python manage.py defect_review_export
    venv\\Scripts\\python manage.py defect_review_export --bundle matek_20260808
"""

import io
import json
import os

from django.core.management.base import BaseCommand

from problems.models import Problem, ReviewVerdict
from problems.review_categories import (CATEGORY_LABELS, EXCLUSIVE_KINDS,
                                        REVIEW_CATEGORIES, VERDICTS_FORMAT_V3)
from problems import before_index as bi
from problems.management.commands.repair_gate import katex_head

OUT_ROOT = os.path.join('reports', 'defect_review')

# Исходный пакет -> как назвать пакет разбора. Имя обязано совпадать с ключом
# в human_review_mark.SUPERSEDES, иначе «идеально» из разбора не отменит брак.
BUNDLES = [
    ('ile_20260721', 'defect_ile_20260721', 'ILE / iloveeconomics.ru'),
    ('aa_20260728', 'defect_aa_20260728', 'Сборник тестов АА'),
    ('matek_20260808', 'defect_matek_20260808', 'МатЭк — Overleaf архивы'),
]


def esc(text):
    """HTML-экранирование. None -> пустая строка."""
    return (str(text or '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def field_blocks(data):
    """Список блоков поля для одной стороны: [(подпись, текст), ...]."""
    out = []
    if data.get('statement') is not None:
        out.append(('Условие', data['statement']))
    for part in data.get('parts') or []:
        label = part.get('label') or ''
        head = 'Пункт {}'.format(label) if label else 'Пункт'
        if part.get('statement') is not None:
            out.append((head, part['statement']))
        if part.get('answer'):
            out.append((head + ' — ответ', part['answer']))
    if data.get('answer'):
        out.append(('Ответ', data['answer']))
    if data.get('solution'):
        out.append(('Решение', data['solution']))
    return out


def side_html(blocks, side):
    """Разметка одной стороны. Каждый блок несёт имя поля — оно уедет в цитату."""
    if not blocks:
        return ('<p class="qls-none">версия ДО не найдена</p>'
                if side == 'before' else
                '<p class="qls-none">поле пустое</p>')
    chunks = []
    for name, text in blocks:
        chunks.append(
            '<div class="qls-field" data-field="{n}" data-side="{s}">'
            '<div class="qls-fname">{n}</div>'
            '<div class="qls-body qls-render">{t}</div>'
            '<div class="qls-body qls-raw" hidden>{t}</div>'
            '</div>'.format(n=esc(name), s=side, t=esc(text)))
    return ''.join(chunks)


class Command(BaseCommand):
    help = ('Собирает офлайн-пакеты разбора забракованных задач '
            '(reports/defect_review). Только читает.')

    def add_arguments(self, parser):
        parser.add_argument('--bundle', default=None,
                            help='только один исходный пакет')
        parser.add_argument('--limit', type=int, default=0,
                            help='ограничить число задач (для пробы)')

    def handle(self, *args, **opts):
        say = self.stdout.write
        os.makedirs(OUT_ROOT, exist_ok=True)

        say('Собираю индекс «ДО»...')
        idx = bi.build_index()
        head = katex_head()
        if not head:
            say('⚠️ KaTeX из пакета ревью не прочитался — страницы будут '
                'без формул.')

        made = []
        for src_bundle, out_bundle, title in BUNDLES:
            if opts['bundle'] and opts['bundle'] != src_bundle:
                continue
            made.append(self.build_one(src_bundle, out_bundle, title, idx,
                                       head, opts['limit'], say))

        say('')
        say('=== ПАКЕТЫ ===')
        say('{:<26}{:>8}{:>10}{:>12}{:>10}'.format(
            'пакет', 'задач', 'есть ДО', 'размер, МБ', 'экранов'))
        for rec in made:
            say('  {:<24}{:>8}{:>10}{:>12}{:>10}'.format(
                rec['bundle'], rec['count'], rec['with_before'],
                rec['mb'], rec['count']))

        # Смета времени: 8 секунд на задачу — темп владельца.
        say('')
        say('=== СМЕТА ПРИ ТЕМПЕ 8 СЕКУНД НА ЗАДАЧУ ===')
        total = 0
        for rec in made:
            secs = rec['count'] * 8
            total += secs
            say('  {:<24}{:>6} задач  {:>4} мин'.format(
                rec['bundle'], rec['count'], round(secs / 60)))
        say('  {:<24}{:>6}        {:>4} мин ({} ч {:02d} мин)'.format(
            'ВСЕГО', sum(r['count'] for r in made), round(total / 60),
            total // 3600, (total % 3600) // 60))

    # ------------------------------------------------------------------
    def build_one(self, src_bundle, out_bundle, title, idx, head, limit, say):
        verdicts = {}
        for rv in ReviewVerdict.objects.filter(bundle=src_bundle):
            rec = verdicts.setdefault(rv.problem_id,
                                      {'cats': [], 'comment': '', 'at': None})
            rec['cats'].append(rv.category)
            if rv.comment:
                rec['comment'] = rv.comment
            rec['at'] = rv.created_at

        # Только те, что реально помечены браком: недостоверные вердикты ILE
        # (проба оболочки) в разбор идти не должны — про них ничего не known.
        defect_ids = set(Problem.objects
                         .filter(id__in=list(verdicts),
                                 human_review=Problem.HumanReview.DEFECT)
                         .values_list('id', flat=True))
        ids = sorted(defect_ids)
        if limit:
            ids = ids[:limit]

        problems = {p.id: p for p in Problem.objects.filter(id__in=ids)
                    .prefetch_related('parts')}

        screens, with_before = [], 0
        for pid in ids:
            problem = problems.get(pid)
            if problem is None:
                continue
            parts = sorted(problem.parts.all(), key=lambda x: (x.order, x.pk))
            before = bi.before_for(idx, problem, parts)
            if before['found']:
                with_before += 1

            after = {
                'statement': problem.statement,
                'solution': problem.solution,
                'answer': problem.answer,
                'parts': [{'pk': p.pk, 'label': p.label,
                           'statement': p.statement, 'answer': p.answer}
                          for p in parts],
            }
            v = verdicts.get(pid, {})
            screens.append({
                'pid': pid,
                'cats': sorted(v.get('cats') or []),
                'comment': v.get('comment') or '',
                'before': before,
                'after': after,
                'updated': (problem.updated_at.strftime('%Y-%m-%d')
                            if problem.updated_at else ''),
                'processes': before.get('sources') or [],
            })

        out_dir = os.path.join(OUT_ROOT, out_bundle)
        os.makedirs(out_dir, exist_ok=True)
        html = self.page(screens, out_bundle, title, src_bundle, head)
        path = os.path.join(out_dir, 'reviewer.html')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(html)

        manifest = {
            'format': 'qls-defect-review-v1',
            'bundle_id': out_bundle,
            'source_bundle': src_bundle,
            'title': title,
            'count': len(screens),
            'with_before': with_before,
            'categories': REVIEW_CATEGORIES,
        }
        with io.open(os.path.join(out_dir, 'manifest.json'), 'w',
                     encoding='utf-8') as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)

        mb = round(os.path.getsize(path) / 1048576.0, 1)
        say('  {:<24} задач {:>4}, есть ДО {:>4}, {:>6} МБ -> {}'.format(
            out_bundle, len(screens), with_before, mb, path))
        return {'bundle': out_bundle, 'count': len(screens),
                'with_before': with_before, 'mb': mb, 'path': path}

    # ------------------------------------------------------------------
    def page(self, screens, bundle, title, src_bundle, head):
        cards = []
        for i, s in enumerate(screens):
            cats = ', '.join(CATEGORY_LABELS.get(c, c) for c in s['cats'])
            comment = ('<div class="qls-cmt"><b>Комментарий ревьюера:</b> '
                       + esc(s['comment']) + '</div>') if s['comment'] else ''
            procs = ', '.join(bi.SOURCE_LABEL.get(p, p) for p in s['processes'])
            meta = []
            if procs:
                meta.append('правил процесс: ' + esc(procs))
            if s['updated']:
                meta.append('последняя правка в базе: ' + esc(s['updated']))
            meta_html = ('<div class="qls-meta">' + ' · '.join(meta) + '</div>'
                         if meta else '')

            cards.append(
                '<section class="qls-screen" id="qls-s{i}" data-pid="{pid}" '
                'data-index="{i}">'
                '<header class="qls-head">'
                '<span class="qls-num">{n} из {total}</span>'
                '<span class="qls-pid">#{pid}</span>'
                '<span class="qls-cats">{cats}</span>'
                '</header>'
                '{comment}{meta}'
                '<div class="qls-cols">'
                '<div class="qls-col"><div class="qls-colhead">ДО</div>{before}</div>'
                '<div class="qls-col"><div class="qls-colhead">ПОСЛЕ '
                '<span class="qls-live">так задача выглядит сейчас</span>'
                '</div>{after}</div>'
                '</div>'
                '<div class="qls-quotes" id="qls-q{i}"></div>'
                '</section>'.format(
                    i=i, n=i + 1, total=len(screens), pid=s['pid'],
                    cats=esc(cats), comment=comment, meta=meta_html,
                    before=side_html(field_blocks(s['before']), 'before'),
                    after=side_html(field_blocks(s['after']), 'after')))

        buttons = []
        for c in REVIEW_CATEGORIES:
            buttons.append(
                '<button class="qls-cat" data-key="{k}" data-kind="{kind}">'
                '<span class="qls-key">{hk}</span> {label}</button>'.format(
                    k=c['key'], kind=c['kind'], hk=esc(c['hotkey']),
                    label=esc(c['label'])))

        payload = {
            'bundle': bundle,
            'source_bundle': src_bundle,
            'format': VERDICTS_FORMAT_V3,
            'count': len(screens),
            'exclusive_kinds': list(EXCLUSIVE_KINDS),
            'categories': [{'key': c['key'], 'hotkey': c['hotkey'],
                            'kind': c['kind'], 'label': c['label']}
                           for c in REVIEW_CATEGORIES],
        }

        return (HTML_HEAD.replace('{{TITLE}}', esc(title))
                         .replace('{{BUNDLE}}', esc(bundle))
                         .replace('{{KATEX}}', head)
                         .replace('{{CSS}}', CSS)
                + '<div class="qls-bar">'
                + '<div class="qls-bar-cats">' + ''.join(buttons) + '</div>'
                + BAR_TAIL
                + '</div><main id="qls-main">' + ''.join(cards) + '</main>'
                + '<script>var QLS_DATA = '
                + json.dumps(payload, ensure_ascii=False) + ';</script>'
                + '<script>' + JS + '</script></body></html>')


HTML_HEAD = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Разбор дефектов — {{TITLE}} ({{BUNDLE}})</title>
{{KATEX}}
<style>{{CSS}}</style>
</head><body>
"""

BAR_TAIL = """
<div class="qls-bar-acts">
  <button id="qls-quote" title="Выделите текст и нажмите (клавиша C)">
    Привязать к выделенному</button>
  <button id="qls-toggle">Показать исходник</button>
  <button id="qls-prev">← назад</button>
  <button id="qls-next">вперёд →</button>
  <button id="qls-save" class="qls-save">Скачать вердикты (JSON)</button>
  <span id="qls-progress" class="qls-progress"></span>
</div>
<div class="qls-cmtbox">
  <input id="qls-comment" type="text" placeholder="Комментарий ко всей задаче
 (Enter — подтвердить вердикт)">
</div>
"""

CSS = """
:root{--qls-bg:#f6f7f9;--qls-surf:#fff;--qls-line:#d8dce3;--qls-ink:#1b2330;
      --qls-dim:#5b6675;--qls-acc:#be185d;--qls-ok:#1d7e45;--qls-warn:#b26b00}
*{box-sizing:border-box}
body{margin:0;background:var(--qls-bg);color:var(--qls-ink);
     font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif;
     padding-top:96px}
.qls-bar{position:fixed;top:0;left:0;right:0;z-index:50;background:var(--qls-surf);
         border-bottom:1px solid var(--qls-line);padding:6px 10px;
         box-shadow:0 1px 6px rgba(0,0,0,.06)}
.qls-bar-cats{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px}
.qls-cat{border:1px solid var(--qls-line);background:#fff;border-radius:6px;
         padding:3px 8px;font-size:13px;cursor:pointer}
.qls-cat[data-kind="ok"]{border-color:var(--qls-ok);color:var(--qls-ok)}
.qls-cat[data-kind="trash"]{border-color:#b00020;color:#b00020}
.qls-cat.qls-on{background:var(--qls-acc);color:#fff;border-color:var(--qls-acc)}
.qls-cat[data-kind="ok"].qls-on{background:var(--qls-ok);border-color:var(--qls-ok)}
.qls-key{display:inline-block;min-width:14px;text-align:center;
         border:1px solid currentColor;border-radius:3px;font-size:11px;
         padding:0 2px;margin-right:3px;opacity:.75}
.qls-bar-acts{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.qls-bar-acts button{border:1px solid var(--qls-line);background:#fff;
         border-radius:6px;padding:3px 9px;font-size:13px;cursor:pointer}
.qls-save{background:#334155;color:#fff;border-color:#334155}
.qls-progress{margin-left:auto;font-size:13px;color:var(--qls-dim)}
.qls-cmtbox{margin-top:4px}
#qls-comment{width:100%;border:1px solid var(--qls-line);border-radius:6px;
             padding:4px 8px;font-size:13px}
.qls-screen{display:none;max-width:1500px;margin:0 auto;padding:12px}
.qls-screen.qls-cur{display:block}
.qls-head{display:flex;gap:10px;align-items:baseline;margin-bottom:6px}
.qls-num{color:var(--qls-dim);font-size:13px}
.qls-pid{font-weight:700}
.qls-cats{color:var(--qls-warn);font-size:13px}
.qls-cmt{background:#fff7e6;border-left:3px solid var(--qls-warn);
         padding:6px 10px;border-radius:0 6px 6px 0;margin-bottom:6px;font-size:14px}
.qls-meta{color:var(--qls-dim);font-size:12px;margin-bottom:8px}
.qls-cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.qls-col{background:var(--qls-surf);border:1px solid var(--qls-line);
         border-radius:8px;padding:10px;min-width:0}
.qls-colhead{font-size:12px;letter-spacing:.06em;text-transform:uppercase;
             color:var(--qls-dim);border-bottom:1px solid var(--qls-line);
             padding-bottom:4px;margin-bottom:8px}
.qls-live{text-transform:none;letter-spacing:0;color:var(--qls-ok)}
.qls-field{margin-bottom:10px}
.qls-fname{font-size:11px;color:var(--qls-dim);text-transform:uppercase;
           letter-spacing:.05em;margin-bottom:2px}
/* Переносы строк — как на боевой странице; без linebreaksbr, иначе
   авторендер потеряет формулу, разрезанную тегом на два текстовых узла. */
.qls-body{white-space:pre-line;overflow-wrap:anywhere}
.qls-raw{white-space:pre-wrap;font-family:ui-monospace,Consolas,monospace;
         font-size:13px;background:#f2f4f7;border-radius:6px;padding:6px}
.qls-none{color:var(--qls-dim);font-style:italic}
:is(table,.katex-display){overflow-x:auto}
.qls-quotes{margin-top:10px}
.qls-quote{background:#fff;border:1px solid var(--qls-line);
           border-left:3px solid var(--qls-acc);border-radius:0 6px 6px 0;
           padding:6px 10px;margin-bottom:6px;font-size:13px}
.qls-quote blockquote{margin:0 0 4px;color:var(--qls-ink);font-style:italic}
.qls-quote .qls-qmeta{color:var(--qls-dim);font-size:11px}
.qls-quote button{float:right;border:0;background:none;color:#b00020;
                  cursor:pointer;font-size:14px}
@media (max-width:900px){.qls-cols{grid-template-columns:1fr}}
"""

# Конвейер долларов и рендера — дословно как в templates/_katex_dollars.html
# и catalog/base.html. Второй копии правил здесь не заводим: расхождение
# показывало бы не то, что видит ученик.
JS = r"""
var DOLLAR_SENTINEL = '\uE000';
function findClose(s, from, close) {
  var i = from;
  while (i < s.length) {
    if (s.charAt(i) === '\\' && s.charAt(i + 1) === '$') { i += 2; continue; }
    if (s.substr(i, close.length) === close) return i;
    i++;
  }
  return -1;
}
function mathSpanEnd(s, i) {
  var pairs = [['$$', '$$'], ['\\[', '\\]'], ['\\(', '\\)'], ['$', '$']];
  for (var k = 0; k < pairs.length; k++) {
    var open = pairs[k][0], close = pairs[k][1];
    if (s.substr(i, open.length) !== open) continue;
    var end = findClose(s, i + open.length, close);
    if (end === -1) continue;
    return end + close.length;
  }
  return i;
}
function maskOutsideMath(s) {
  if (s.indexOf('\\$') === -1) return s;
  var out = '', i = 0, n = s.length;
  while (i < n) {
    if (s.charAt(i) === '\\' && s.charAt(i + 1) === '$') {
      out += DOLLAR_SENTINEL; i += 2; continue;
    }
    var end = mathSpanEnd(s, i);
    if (end > i) { out += s.slice(i, end); i = end; continue; }
    out += s.charAt(i); i++;
  }
  return out;
}
function walkText(root, fn) {
  var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), n;
  while ((n = w.nextNode())) {
    var p = n.parentNode && n.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    fn(n);
  }
}
function maskEscapedDollars(root) {
  walkText(root, function (n) {
    if (n.nodeValue.indexOf('\\$') !== -1) n.nodeValue = maskOutsideMath(n.nodeValue);
  });
}
function fixCurrencyDollars(root) {
  walkText(root, function (n) {
    var v = n.nodeValue;
    if (v.indexOf(DOLLAR_SENTINEL) !== -1 || v.indexOf('\\$') !== -1 ||
        v.indexOf('\\_') !== -1 || v.indexOf('\\&') !== -1 ||
        v.indexOf('\\#') !== -1) {
      n.nodeValue = v.split(DOLLAR_SENTINEL).join('$').split('\\$').join('$')
                     .split('\\_').join('_').split('\\&').join('&')
                     .split('\\#').join('#');
    }
  });
}
function renderScreen(el) {
  if (el.dataset.rendered === '1') return;
  el.dataset.rendered = '1';
  var zones = el.querySelectorAll('.qls-render');
  for (var i = 0; i < zones.length; i++) {
    maskEscapedDollars(zones[i]);
    if (typeof renderMathInElement === 'function') {
      renderMathInElement(zones[i], {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false }
        ],
        throwOnError: false
      });
    }
    fixCurrencyDollars(zones[i]);
  }
}

/* ---------- состояние ---------- */
var KEY = 'qls-defect-' + QLS_DATA.bundle;
var state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }
var cur = 0;
try { cur = parseInt(localStorage.getItem(KEY + '-pos') || '0', 10) || 0; } catch (e) { cur = 0; }
var screens = [].slice.call(document.querySelectorAll('.qls-screen'));
var kindOf = {}, hotkeys = {};
QLS_DATA.categories.forEach(function (c) { kindOf[c.key] = c.kind; hotkeys[c.hotkey] = c.key; });
var EXCL = QLS_DATA.exclusive_kinds;

function rec(pid) {
  if (!state[pid]) state[pid] = { categories: [], comment: '', quotes: [] };
  if (!state[pid].quotes) state[pid].quotes = [];
  return state[pid];
}
function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
    localStorage.setItem(KEY + '-pos', String(cur));
  } catch (e) {}
}
function curScreen() { return screens[cur]; }
function curPid() { return curScreen() ? curScreen().dataset.pid : null; }

function paintQuotes() {
  var el = curScreen(); if (!el) return;
  var box = el.querySelector('.qls-quotes');
  var r = rec(curPid());
  box.innerHTML = '';
  r.quotes.forEach(function (q, i) {
    var d = document.createElement('div');
    d.className = 'qls-quote';
    var b = document.createElement('button');
    b.textContent = '×'; b.title = 'убрать цитату';
    b.onclick = function () { r.quotes.splice(i, 1); save(); paintQuotes(); };
    var bq = document.createElement('blockquote');
    bq.textContent = '«' + q.text + '»';
    var m = document.createElement('div');
    m.className = 'qls-qmeta';
    m.textContent = (q.side === 'before' ? 'ДО' : 'ПОСЛЕ') + ' · ' +
                    (q.field || 'поле не определено') + ' · ' +
                    (q.view === 'raw' ? 'исходник' : 'отрендеренный вид') +
                    (q.note ? ' — ' + q.note : '');
    d.appendChild(b); d.appendChild(bq); d.appendChild(m);
    box.appendChild(d);
  });
}
function paint() {
  screens.forEach(function (s, i) { s.classList.toggle('qls-cur', i === cur); });
  var el = curScreen(); if (!el) return;
  renderScreen(el);
  var r = rec(curPid());
  document.querySelectorAll('.qls-cat').forEach(function (b) {
    b.classList.toggle('qls-on', r.categories.indexOf(b.dataset.key) !== -1);
  });
  document.getElementById('qls-comment').value = r.comment || '';
  var done = Object.keys(state).filter(function (k) {
    return state[k].categories && state[k].categories.length;
  }).length;
  document.getElementById('qls-progress').textContent =
    (cur + 1) + ' / ' + screens.length + ' · размечено ' + done;
  paintQuotes();
  el.scrollIntoView({ block: 'start' });
  // Соседний экран рендерим заранее — иначе на тяжёлой формуле видно паузу.
  if (screens[cur + 1]) renderScreen(screens[cur + 1]);
}
function go(step) {
  cur = Math.max(0, Math.min(screens.length - 1, cur + step));
  save(); paint();
}
function toggleCat(key) {
  var r = rec(curPid());
  var kind = kindOf[key];
  if (EXCL.indexOf(kind) !== -1) {
    // Исключающий вид — вердикт из одного нажатия: сбрасывает всё и листает.
    r.categories = [key];
    save(); paint(); go(1); return;
  }
  var i = r.categories.indexOf(key);
  if (i === -1) {
    // Исключающие снимаем: «идеально и сломанная формула» — противоречие.
    r.categories = r.categories.filter(function (k) {
      return EXCL.indexOf(kindOf[k]) === -1;
    });
    r.categories.push(key);
  } else {
    r.categories.splice(i, 1);
  }
  save(); paint();
}

/* ---------- цитаты ---------- */
function attachQuote() {
  var sel = window.getSelection();
  var text = sel ? String(sel).trim() : '';
  if (!text) { alert('Сначала выделите кусок текста мышью.'); return; }
  var node = sel.anchorNode;
  var host = node && (node.nodeType === 1 ? node : node.parentNode);
  var field = host && host.closest ? host.closest('.qls-field') : null;
  var body = host && host.closest ? host.closest('.qls-body') : null;
  var note = prompt('Что не так с этим куском?', '');
  if (note === null) return;
  rec(curPid()).quotes.push({
    text: text,
    note: note,
    side: field ? field.dataset.side : '',
    field: field ? field.dataset.field : '',
    view: body && body.classList.contains('qls-raw') ? 'raw' : 'rendered',
    at: new Date().toISOString()
  });
  save(); paintQuotes();
  if (sel.removeAllRanges) sel.removeAllRanges();
}

/* ---------- выгрузка ---------- */
function download() {
  var out = [];
  Object.keys(state).forEach(function (pid) {
    var r = state[pid];
    if ((!r.categories || !r.categories.length) &&
        (!r.quotes || !r.quotes.length) && !r.comment) return;
    out.push({
      problem_id: parseInt(pid, 10),
      categories: r.categories || [],
      comment: r.comment || '',
      quotes: r.quotes || [],
      at: new Date().toISOString()
    });
  });
  var doc = {
    format: QLS_DATA.format,
    bundle_id: QLS_DATA.bundle,
    source_bundle: QLS_DATA.source_bundle,
    reviewer: (prompt('Ваше имя для файла вердиктов:', 'анич') || 'анич'),
    exported_at: new Date().toISOString(),
    count: out.length,
    verdicts: out
  };
  var blob = new Blob([JSON.stringify(doc, null, 1)],
                      { type: 'application/json' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'verdicts_' + QLS_DATA.bundle + '.json';
  document.body.appendChild(a); a.click(); a.remove();
}

/* ---------- события ---------- */
document.querySelectorAll('.qls-cat').forEach(function (b) {
  b.onclick = function () { toggleCat(b.dataset.key); };
});
document.getElementById('qls-next').onclick = function () { go(1); };
document.getElementById('qls-prev').onclick = function () { go(-1); };
document.getElementById('qls-save').onclick = download;
document.getElementById('qls-quote').onclick = attachQuote;
document.getElementById('qls-toggle').onclick = function () {
  var el = curScreen(); if (!el) return;
  var raws = el.querySelectorAll('.qls-raw');
  var showRaw = raws.length && raws[0].hasAttribute('hidden');
  el.querySelectorAll('.qls-raw').forEach(function (n) {
    if (showRaw) { n.removeAttribute('hidden'); } else { n.setAttribute('hidden', ''); }
  });
  el.querySelectorAll('.qls-render').forEach(function (n) {
    if (showRaw) { n.setAttribute('hidden', ''); } else { n.removeAttribute('hidden'); }
  });
  this.textContent = showRaw ? 'Показать отрендеренный вид' : 'Показать исходник';
};
var box = document.getElementById('qls-comment');
box.oninput = function () { rec(curPid()).comment = box.value; save(); };
box.onkeydown = function (e) {
  if (e.key === 'Enter') { e.preventDefault(); box.blur(); go(1); }
};
document.addEventListener('keydown', function (e) {
  var t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (hotkeys[e.key] !== undefined) { e.preventDefault(); toggleCat(hotkeys[e.key]); return; }
  // Клавиша цитаты — по event.code: буква зависит от раскладки, код нет.
  if (e.code === 'KeyC') { e.preventDefault(); attachQuote(); return; }
  if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); go(1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
});
paint();
"""
