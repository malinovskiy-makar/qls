"""repair_wave1_export — пакет разбора ПОЧИНОК волны 1. ТОЛЬКО ЧИТАЕТ.

Оболочка та же, что у пакетов ревью, которые владелец уже проходил
(export_review_bundle -> defect_review_export): вёрстка, конвейер долларов,
цитаты и выгрузка переиспользуются, второй оболочки не заводим.

ЧТО ИНОГО ПРОТИВ ПАКЕТОВ РЕВЬЮ, и почему:

  * КНОПКИ ПРО ПОЧИНКУ, А НЕ ПРО ДЕФЕКТ. Их пять, словарь —
    problems/repair_outcomes.py. Категория дефекта на этом экране показана
    СПРАВКОЙ: она проставлена на первом проходе, переголосовывать её здесь
    нечем и незачем.
  * ЕСТЬ БЛОК «ЧТО СКАЗАЛА МОДЕЛЬ». Это ключевой элемент экрана: по нему
    видно, поняла модель задачу или нет. Без него оценка мерила бы только
    текст, а не работу модели.
  * ЕСТЬ ПОМЕТКА ШЛЮЗА. Ничего не отбраковано: человек видит и то, что шлюз
    не пропустил, — так измеряется заодно и сам шлюз.

⚠️ «ДО» ЗДЕСЬ — ЭТО ТЕКУЩАЯ БАЗА, а не исторический снимок. Именно её видел
ревьюер на первом проходе и именно она сейчас на сайте. «ПОСЛЕ» в базе НЕ
лежит: это предложение модели, и решение о нём принимает человек.

⚠️ ОБА СТОЛБЦА ОТРЕНДЕРЕНЫ по умолчанию, боевым конвейером
(defect_review_export.PIPELINE_JS). Сырой текст — кнопкой: на сыром тексте
правильная разметка формул читается как порча.

⚠️ ПОРЯДОК ЭКРАНОВ — по номеру задачи, и идентификатор экрана это номер по
порядку. Ни то, ни другое не зависит ни от результата шлюза, ни от объёма
правки: иначе человек начал бы судить по подсказке, а не по существу.

⚠️ Свои CSS-классы только с префиксом qls-. KaTeX внутри .katex-html сам
раздаёт узлам классы text/mord/base/strut/mfrac/sqrt, а CSS матчит по ТОКЕНУ
класса — одноимённое правило протащило бы рамку прямо в формулу.

Запуск:
    venv\\Scripts\\python manage.py repair_wave1_export
"""

import io
import json
import os

from django.core.management.base import BaseCommand

from problems.review_categories import CATEGORY_LABELS
from problems.repair_outcomes import REPAIR_OUTCOMES, REPAIR_VERDICTS_FORMAT
from problems.management.commands.repair_gate import katex_head
from problems.management.commands.defect_review_export import (
    CSS as BASE_CSS, PIPELINE_JS, esc)

OUT_DIR = os.path.join('reports', 'repair_wave1')
BUNDLE = 'repair_aa_20260728'
SOURCE_BUNDLE = 'aa_20260728'
TITLE = 'Сборник тестов АА — волна 1'

ACTION_WORD = {
    'fixed': 'правка есть',
    'nothing_to_fix': 'модель говорит: чинить нечего',
    'unclear': 'модель говорит: дефект непонятен',
}


def apply_fields(before, patch):
    """«ПОСЛЕ» — исходные поля, поверх которых легли правленые."""
    after = json.loads(json.dumps(before))
    for k in ('statement', 'solution', 'answer', 'parts'):
        if k in (patch or {}):
            after[k] = patch[k]
    return after


def field_blocks(fields):
    """Блоки поля в порядке показа: [(подпись, текст), ...]."""
    out = [('Условие', fields.get('statement') or '')]
    for p in fields.get('parts') or []:
        label = (p.get('label') or '').strip()
        head = 'Пункт %s' % label if label else 'Пункт'
        out.append((head, p.get('statement') or ''))
        if p.get('answer'):
            out.append((head + ' — ответ', p['answer']))
    if fields.get('solution'):
        out.append(('Решение', fields['solution']))
    if fields.get('answer'):
        out.append(('Ответ', fields['answer']))
    return out


def side_html(fields, side, changed):
    """Разметка одной стороны. Каждый блок несёт имя поля — оно уедет в цитату."""
    chunks = []
    for name, text in field_blocks(fields):
        mark = ' qls-changed' if changed.get(name) else ''
        chunks.append(
            '<div class="qls-field{m}" data-field="{n}" data-side="{s}">'
            '<div class="qls-fname">{n}</div>'
            '<div class="qls-body qls-render">{t}</div>'
            '<div class="qls-body qls-raw" hidden>{t}</div>'
            '</div>'.format(m=mark, n=esc(name), s=side, t=esc(text)))
    return ''.join(chunks) or '<p class="qls-none">полей нет</p>'


def changed_map(before, after):
    """Какие блоки различаются — по подписи блока.

    ⚠️ Подписи НЕ уникальны: в банке есть пары подпунктов с одинаковой меткой
    (34 пары «а» нашлись ещё при склейке строк). Поэтому под одной подписью
    сравнивается СПИСОК текстов, а не один текст: словарь схлопнул бы пару и
    объявил бы блок нетронутым.
    """
    def group(fields):
        out = {}
        for name, text in field_blocks(fields):
            out.setdefault(name, []).append(text)
        return out

    b, a = group(before), group(after)
    return {name: b.get(name) != a.get(name) for name in set(b) | set(a)}


class Command(BaseCommand):
    help = ('Собирает пакет разбора починок волны 1 (reports/repair_wave1). '
            'Только читает.')

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='взять первые N экранов (проверка оболочки)')
        parser.add_argument('--out', default='reviewer.html')
        parser.add_argument('--light', action='store_true',
                            help='без шрифтов KaTeX — только для проверки механики')

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **opts):
        sample = {r['id']: r for r in json.load(
            io.open(os.path.join(OUT_DIR, 'sample.json'), encoding='utf-8'))}
        repairs = json.load(io.open(os.path.join(OUT_DIR, 'aa_repairs.json'),
                                    encoding='utf-8'))['repairs']
        gate = {}
        gate_path = os.path.join(OUT_DIR, 'gate.json')
        if os.path.exists(gate_path):
            for g in json.load(io.open(gate_path, encoding='utf-8')):
                gate[g['id']] = g

        screens = []
        for rep in sorted(repairs, key=lambda r: r['id']):
            rec = sample.get(rep['id'])
            if rec is None:
                continue
            after = apply_fields(rec['before'], rep.get('fields') or {})
            screens.append({
                'pid': rep['id'],
                'cats': rec['categories'],
                'comment': rec['comment'],
                'action': rep['action'],
                'explain': rep['explain'],
                'edit_chars': rep.get('edit_chars', 0),
                'before': rec['before'],
                'after': after,
                'gate': gate.get(rep['id']),
            })
        if opts['limit']:
            screens = screens[:opts['limit']]

        head = '' if opts['light'] else katex_head()
        if not head and not opts['light']:
            self.say('⚠️ KaTeX из пакета ревью не прочитался — страница будет '
                     'без формул.')

        html = self.page(screens, head)
        path = os.path.join(OUT_DIR, opts['out'])
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(html)

        manifest = {
            'format': 'qls-repair-review-v1',
            'bundle_id': BUNDLE,
            'source_bundle': SOURCE_BUNDLE,
            'title': TITLE,
            'count': len(screens),
            'with_edit': sum(1 for s in screens if s['action'] == 'fixed'),
            'outcomes': REPAIR_OUTCOMES,
        }
        with io.open(os.path.join(OUT_DIR, 'manifest.json'), 'w',
                     encoding='utf-8') as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)

        mb = round(os.path.getsize(path) / 1048576.0, 1)
        passed = sum(1 for s in screens
                     if s['gate'] and s['gate']['gate_passed'])
        self.say('=== ПАКЕТ РАЗБОРА ПОЧИНОК ===')
        self.say('экранов: %d (с правкой %d, отказов %d)'
                 % (len(screens),
                    sum(1 for s in screens if s['action'] == 'fixed'),
                    sum(1 for s in screens if s['action'] != 'fixed')))
        self.say('шлюз пройден: %d из %d' % (passed, len(screens)))
        self.say('размер: %s МБ' % mb)
        self.say('-> %s' % os.path.abspath(path))
        # Смета времени: 8 секунд на экран — темп владельца на прошлых пакетах.
        secs = len(screens) * 8
        self.say('при темпе 8 секунд на экран это ~%d мин' % round(secs / 60))

    # ------------------------------------------------------------------
    def page(self, screens, head):
        cards = []
        for i, s in enumerate(screens):
            cats = ', '.join(CATEGORY_LABELS.get(c, c) for c in s['cats'])
            first = ['<b>Первый проход:</b> ' + esc(cats)]
            if s['comment']:
                first.append('«' + esc(s['comment']) + '»')
            first_html = ('<div class="qls-cmt">' + ' · '.join(first) + '</div>')

            g = s['gate']
            if g is None:
                gate_html = ('<div class="qls-gate qls-gate--none">'
                             'Шлюз: не считался</div>')
            elif s['action'] != 'fixed':
                gate_html = ('<div class="qls-gate qls-gate--none">'
                             'Шлюз: проверять нечего, правки нет</div>')
            elif g['gate_passed']:
                gate_html = ('<div class="qls-gate qls-gate--ok">'
                             'Шлюз пройден: числа и знаки на месте, ошибок '
                             'KaTeX не прибавилось</div>')
            else:
                gate_html = ('<div class="qls-gate qls-gate--bad">'
                             '<b>Шлюз НЕ пройден:</b> '
                             + esc('; '.join(g['gate_labels'])) + '</div>')

            changed = (changed_map(s['before'], s['after'])
                       if s['action'] == 'fixed' else {})
            right_note = ('так задача будет выглядеть, если принять починку'
                          if s['action'] == 'fixed'
                          else 'модель текст не правила — столбцы совпадают')

            cards.append(
                '<section class="qls-screen" id="qls-s{i}" data-pid="{pid}" '
                'data-index="{i}">'
                '<header class="qls-head">'
                '<span class="qls-num">{n} из {total}</span>'
                '<span class="qls-pid">#{pid}</span>'
                '<span class="qls-act">{act}</span>'
                '</header>'
                '{first}'
                '<div class="qls-model"><div class="qls-model-h">Что сказала '
                'модель</div><div class="qls-model-b">{explain}</div></div>'
                '{gate}'
                '<div class="qls-cols">'
                '<div class="qls-col"><div class="qls-colhead">ДО '
                '<span class="qls-live">так задача выглядит на сайте сейчас'
                '</span></div>{before}</div>'
                '<div class="qls-col"><div class="qls-colhead">ПОСЛЕ '
                '<span class="qls-live">{rnote}</span></div>{after}</div>'
                '</div>'
                '<div class="qls-quotes" id="qls-q{i}"></div>'
                '</section>'.format(
                    i=i, n=i + 1, total=len(screens), pid=s['pid'],
                    act=esc(ACTION_WORD.get(s['action'], s['action'])),
                    first=first_html, gate=gate_html,
                    explain=esc(s['explain']) or
                            '<i>модель ничего не объяснила</i>',
                    rnote=esc(right_note),
                    before=side_html(s['before'], 'before', {}),
                    after=side_html(s['after'], 'after', changed)))

        buttons = []
        for o in REPAIR_OUTCOMES:
            buttons.append(
                '<button class="qls-out" data-key="{k}" title="{hint}">'
                '<span class="qls-key">{hk}</span> {label}</button>'.format(
                    k=o['key'], hk=esc(o['hotkey']), label=esc(o['label']),
                    hint=esc(o['hint'])))

        payload = {
            'bundle': BUNDLE,
            'source_bundle': SOURCE_BUNDLE,
            'format': REPAIR_VERDICTS_FORMAT,
            'count': len(screens),
            'outcomes': [{'key': o['key'], 'hotkey': o['hotkey'],
                          'label': o['label']} for o in REPAIR_OUTCOMES],
            'origin': {str(s['pid']): s['cats'] for s in screens},
        }

        return (HEAD.replace('{{TITLE}}', esc(TITLE))
                    .replace('{{BUNDLE}}', esc(BUNDLE))
                    .replace('{{KATEX}}', head)
                    .replace('{{CSS}}', BASE_CSS + EXTRA_CSS)
                + '<div class="qls-bar"><div class="qls-bar-cats">'
                + ''.join(buttons) + '</div>' + BAR_TAIL
                + '</div><main id="qls-main">' + ''.join(cards) + '</main>'
                + '<script>var QLS_DATA = '
                + json.dumps(payload, ensure_ascii=False) + ';</script>'
                + '<script>' + PIPELINE_JS + '</script>'
                + '<script>' + SHELL_JS + '</script></body></html>')


HEAD = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Разбор починок — {{TITLE}} ({{BUNDLE}})</title>
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
  <button id="qls-save" class="qls-save">Скачать оценки (JSON)</button>
  <span id="qls-progress" class="qls-progress"></span>
</div>
<div class="qls-cmtbox">
  <input id="qls-comment" type="text"
         placeholder="Комментарий ко всей задаче (Enter — дальше)">
</div>
"""

EXTRA_CSS = """
.qls-out{border:1px solid var(--qls-line);background:#fff;border-radius:6px;
         padding:3px 8px;font-size:13px;cursor:pointer}
.qls-out.qls-on{background:var(--qls-acc);color:#fff;border-color:var(--qls-acc)}
.qls-out[data-key="fixed_perfect"]{border-color:var(--qls-ok);color:var(--qls-ok)}
.qls-out[data-key="fixed_perfect"].qls-on{background:var(--qls-ok);color:#fff;
         border-color:var(--qls-ok)}
.qls-out[data-key="broke"]{border-color:#b00020;color:#b00020}
.qls-out[data-key="broke"].qls-on{background:#b00020;color:#fff;border-color:#b00020}
.qls-act{color:var(--qls-dim);font-size:13px}
.qls-model{background:#eef4ff;border-left:3px solid #2f5fb3;
           border-radius:0 6px 6px 0;padding:7px 10px;margin-bottom:6px}
.qls-model-h{font-size:11px;letter-spacing:.06em;text-transform:uppercase;
             color:#2f5fb3;margin-bottom:2px}
.qls-model-b{font-size:14px}
.qls-gate{font-size:13px;padding:5px 10px;border-radius:6px;margin-bottom:8px;
          border:1px solid var(--qls-line)}
.qls-gate--ok{background:#eef8f1;border-color:#bfe0cb;color:#14522e}
.qls-gate--bad{background:#fdeef0;border-color:#f0c2c9;color:#8a1024}
.qls-gate--none{background:#f2f4f7;color:var(--qls-dim)}
.qls-changed{background:#fffbe9;border-radius:6px;padding:4px 6px;margin:0 -6px 10px}
"""

# Оболочка разбора починок. Состояние, кнопки, цитаты, выгрузка. Механика
# цитат и хранения — как в defect_review_export.SHELL_JS; отличается словарь
# (исходы вместо категорий) и формат выгрузки.
SHELL_JS = r"""
var KEY = 'qls-repair-' + QLS_DATA.bundle;
var state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }
var cur = 0;
try { cur = parseInt(localStorage.getItem(KEY + '-pos') || '0', 10) || 0; } catch (e) { cur = 0; }
var screens = [].slice.call(document.querySelectorAll('.qls-screen'));
var hotkeys = {};
QLS_DATA.outcomes.forEach(function (o) { hotkeys[o.hotkey] = o.key; });

function rec(pid) {
  if (!state[pid]) state[pid] = { outcome: '', comment: '', quotes: [] };
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
function renderScreenSafe(el) { if (el) renderScreen(el); }
function paint() {
  screens.forEach(function (s, i) { s.classList.toggle('qls-cur', i === cur); });
  var el = curScreen(); if (!el) return;
  renderScreenSafe(el);
  var r = rec(curPid());
  document.querySelectorAll('.qls-out').forEach(function (b) {
    b.classList.toggle('qls-on', r.outcome === b.dataset.key);
  });
  document.getElementById('qls-comment').value = r.comment || '';
  var done = Object.keys(state).filter(function (k) { return state[k].outcome; }).length;
  document.getElementById('qls-progress').textContent =
    (cur + 1) + ' / ' + screens.length + ' · оценено ' + done;
  paintQuotes();
  el.scrollIntoView({ block: 'start' });
  renderScreenSafe(screens[cur + 1]);
}
function go(step) {
  cur = Math.max(0, Math.min(screens.length - 1, cur + step));
  save(); paint();
}
/* Исход у задачи ОДИН: это ответ на один вопрос «что вышло у починки»,
   а не набор свойств. Нажатие ставит его и листает дальше; повторное
   нажатие того же исхода снимает оценку и никуда не листает. */
function setOutcome(key) {
  var r = rec(curPid());
  if (r.outcome === key) { r.outcome = ''; save(); paint(); return; }
  r.outcome = key;
  save(); paint(); go(1);
}

/* Вставка цитаты отделена от чтения выделения, а сборка файла — от его
   скачивания. Причина не в красоте: Node в этом окружении нет, и единственный
   способ прогнать оболочку «как ревьюер» — сценарий в настоящем браузере.
   Через prompt() и Blob сценарий не пройдёт, поэтому наружу торчит
   window.QLS_SHELL. Боевой путь (клавиши, мышь, кнопка) идёт через те же
   функции — проверяется ровно то, чем пользуется человек. */
function pushQuote(text, note, side, field, view) {
  rec(curPid()).quotes.push({
    text: text, note: note, side: side || '', field: field || '',
    view: view || 'rendered', at: new Date().toISOString()
  });
  save(); paintQuotes();
}
function attachQuote() {
  var sel = window.getSelection();
  var text = selectionText(sel);
  if (!text) { alert('Сначала выделите кусок текста мышью.'); return; }
  var node = sel.anchorNode;
  var host = node && (node.nodeType === 1 ? node : node.parentNode);
  var field = host && host.closest ? host.closest('.qls-field') : null;
  var body = host && host.closest ? host.closest('.qls-body') : null;
  var note = prompt('Что модель не поняла или где не заметила ошибку?', '');
  if (note === null) return;
  pushQuote(text, note,
            field ? field.dataset.side : '',
            field ? field.dataset.field : '',
            body && body.classList.contains('qls-raw') ? 'raw' : 'rendered');
  if (sel.removeAllRanges) sel.removeAllRanges();
}

function buildDoc(reviewer) {
  var out = [];
  Object.keys(state).forEach(function (pid) {
    var r = state[pid];
    if (!r.outcome && !(r.quotes || []).length && !r.comment) return;
    out.push({
      problem_id: parseInt(pid, 10),
      outcome: r.outcome || '',
      comment: r.comment || '',
      origin_categories: QLS_DATA.origin[pid] || [],
      quotes: r.quotes || [],
      at: new Date().toISOString()
    });
  });
  out.sort(function (a, b) { return a.problem_id - b.problem_id; });
  return {
    format: QLS_DATA.format,
    bundle_id: QLS_DATA.bundle,
    source_bundle: QLS_DATA.source_bundle,
    reviewer: reviewer || 'анич',
    exported_at: new Date().toISOString(),
    count: out.length,
    verdicts: out
  };
}
function download() {
  var doc = buildDoc(prompt('Ваше имя для файла оценок:', 'анич') || 'анич');
  var blob = new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'repairs_' + QLS_DATA.bundle + '.json';
  document.body.appendChild(a); a.click(); a.remove();
}

document.querySelectorAll('.qls-out').forEach(function (b) {
  b.onclick = function () { setOutcome(b.dataset.key); };
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
  if (hotkeys[e.key] !== undefined) { e.preventDefault(); setOutcome(hotkeys[e.key]); return; }
  /* Клавиша цитаты — по event.code: буква зависит от раскладки, код нет. */
  if (e.code === 'KeyC') { e.preventDefault(); attachQuote(); return; }
  if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); go(1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
});
/* Шов для сценария проверки — см. комментарий у pushQuote. */
window.QLS_SHELL = {
  buildDoc: buildDoc, attachQuote: attachQuote, go: go,
  at: function () { return cur; },
  pid: function () { return curPid(); },
  reset: function () { state = {}; cur = 0; save(); paint(); }
};
paint();
"""
