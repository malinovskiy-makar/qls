"""Страница проверки кандидатов экзамена: один самодостаточный HTML на пачку.

Образец — `dedup_human_review_html`: открывается двойным щелчком с file://
без сети, KaTeX вшит, ответы копятся в localStorage, выгрузка одним JSON
в формате `ai_exam_review/1` (`problems/ai_exam/review.py`).
`katex_head` и `render_field` берутся оттуда импортом: отрисовка задачи
на странице обязана совпадать с той, что видит ученик.

⚠️ ПРОВЕРКА СЛЕПАЯ. На странице нет ни мнения модели (второго мнения по
ответу), ни согласованности ответа с решением из обогащения, ни вердикта
ручного ревью: человек должен проверять задачу, а не согласие с машиной.
Карточка собирается только из полей условия, ответа и решения.
"""
import json

from django.utils.html import escape

from problems.ai_exam.review import FORMAT, REASONS
from problems.management.commands.dedup_human_review_html import (
    katex_head, render_field,
)

SITE = 'https://weconomics.ai/catalog/problem/%s/'

INSTRUCTION = (
    'Задача годится для экзамена, если: 1) условие полное и понятно без '
    'картинки; 2) вы согласны с ответом банка — решили сами или проверили '
    'решение; 3) ответ — число (или по числу на пункт), и ясно, в каких '
    'единицах; 4) это расчёт, а не «объясните». Хоть одно не так — «Не '
    'годится» и причина. Ключ: число без единиц; проценты — числом '
    'процентов (25, а не 0,25) и галочка. Сомневаетесь — «Пропустить» и '
    'комментарий.'
)

PAGE_CSS = """
:root{--ink:#2c2925;--muted:#6f675d;--line:#ded7cb;--bg:#f6f3ec;--card:#fffdf8;
--ok:#1f7a6a;--bad:#a8552f;--skip:#6f675d;--hint:#9a6a00;--hintbg:#fff4d6}
*{box-sizing:border-box}
body{margin:0;padding:0 0 40px;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.qx-bar{position:sticky;top:0;z-index:5;background:var(--card);
border-bottom:1px solid var(--line);padding:10px 20px}
.qx-head{padding:4px 20px 0}
.qx-row{display:flex;flex-wrap:wrap;gap:12px;align-items:center;max-width:1100px;margin:0 auto}
.qx-row h1{font-size:18px;margin:0}
.qx-reserve{background:var(--hintbg);color:var(--hint);border-radius:4px;padding:1px 8px;
font-size:13px;font-weight:600}
.qx-sp{flex:1}
.qx-lead{max-width:1100px;margin:8px auto 0;color:var(--muted);font-size:14px}
.qx-warn{max-width:1100px;margin:6px auto 0;color:var(--bad);font-size:13px}
.qx-wrap{max-width:1100px;margin:0 auto;padding:18px 20px}
.qx-card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin:0 0 18px;scroll-margin-top:140px}
.qx-card.qx-active{box-shadow:0 0 0 2px var(--ink)}
.qx-card[data-verdict="ok"]{border-left:5px solid var(--ok)}
.qx-card[data-verdict="bad"]{border-left:5px solid var(--bad)}
.qx-card[data-verdict="skip"]{border-left:5px solid var(--skip)}
.qx-meta{display:flex;flex-wrap:wrap;gap:10px;color:var(--muted);font-size:13px;
margin:0 0 10px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.qx-meta b{color:var(--ink)}
.qx-url{font-family:ui-monospace,monospace;user-select:all}
.qx-lbl{color:var(--muted);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
margin:12px 0 2px}
.qx-part{margin:8px 0 0;padding-left:12px;border-left:2px solid var(--line)}
.qx-answer{background:#fff;border:1px dashed var(--line);border-radius:6px;padding:4px 8px}
details{margin:10px 0 0}
summary{cursor:pointer;color:var(--muted)}
.qx-form{margin:14px 0 0;padding-top:10px;border-top:1px solid var(--line)}
.qx-verdicts{display:flex;flex-wrap:wrap;gap:8px}
button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;
background:#fff;cursor:pointer;color:var(--ink)}
button:hover{border-color:var(--ink)}
button.qx-on[data-v="ok"]{background:var(--ok);border-color:var(--ok);color:#fff}
button.qx-on[data-v="bad"]{background:var(--bad);border-color:var(--bad);color:#fff}
button.qx-on[data-v="skip"]{background:var(--skip);border-color:var(--skip);color:#fff}
.qx-why{display:none;gap:8px;flex-wrap:wrap;margin:8px 0 0}
.qx-card[data-verdict="bad"] .qx-why{display:flex}
select,input[type=text],textarea{font:inherit;padding:4px 6px;border:1px solid var(--line);
border-radius:6px;background:#fff;color:var(--ink)}
textarea{width:100%;min-height:34px;margin:8px 0 0}
.qx-keys{margin:10px 0 0;display:grid;gap:6px}
.qx-key{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.qx-key .qx-plabel{min-width:60px;font-weight:600}
.qx-key input.qx-v{width:130px}
.qx-key input.qx-u{width:110px}
.qx-key input.qx-t{width:90px}
.qx-hint{background:var(--hintbg);color:var(--hint);font-size:12px;border-radius:4px;
padding:1px 6px}
.qx-figure{max-width:100%;height:auto}
table{border-collapse:collapse}
td,th{border:1px solid var(--line);padding:3px 7px}
"""

PAGE_JS = r"""
var DATA = JSON.parse(document.getElementById('qx-data').textContent);
var KEY = 'qls-ai-exam-v0-' + DATA.seed + '-chunk' + DATA.chunk;
var state = {reviewer: '', rows: {}};
try {
  var saved = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (saved && saved.rows) state = saved;
} catch (e) {}
var CARDS = {};
DATA.cards.forEach(function (c) { CARDS[c.id] = c; });
var current = 0;

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  refresh();
}

function proposal(card) {
  return card.asks.map(function (a) {
    return {part_id: a.part_id, value: a.value, unit: a.unit,
            percent: !!a.percent, tol: ''};
  });
}

function row(id) {
  if (!state.rows[id]) {
    state.rows[id] = {verdict: null, reason: '', comment: '', key: proposal(CARDS[id])};
  }
  return state.rows[id];
}

function setVerdict(id, v) {
  var r = row(id);
  r.verdict = (r.verdict === v) ? null : v;
  paint(id); save();
}

function setField(el) {
  var card = el.closest('.qx-card');
  var r = row(Number(card.dataset.id));
  var f = el.dataset.f;
  if (f === 'reason' || f === 'comment') { r[f] = el.value; }
  else {
    var k = r.key[Number(el.dataset.i)];
    k[f] = (f === 'percent') ? el.checked : el.value;
  }
  save();
}

function paint(id) {
  var box = document.querySelector('.qx-card[data-id="' + id + '"]');
  var r = state.rows[id];
  if (!box) return;
  box.dataset.verdict = (r && r.verdict) || '';
  box.querySelectorAll('button[data-v]').forEach(function (b) {
    b.classList.toggle('qx-on', !!r && r.verdict === b.dataset.v);
  });
  if (!r) return;
  box.querySelectorAll('[data-f]').forEach(function (el) {
    var f = el.dataset.f, val;
    if (f === 'reason' || f === 'comment') val = r[f] || '';
    else val = (r.key[Number(el.dataset.i)] || {})[f];
    if (f === 'percent') el.checked = !!val;
    else if (el.value !== (val == null ? '' : String(val))) el.value = val == null ? '' : val;
  });
}

function refresh() {
  var done = 0, good = 0;
  DATA.cards.forEach(function (c) {
    var r = state.rows[c.id];
    if (r && r.verdict) { done++; if (r.verdict === 'ok') good++; }
  });
  document.getElementById('qx-count').textContent =
    'проверено ' + done + ' из ' + DATA.cards.length + ', годится ' + good;
  var name = document.getElementById('qx-name');
  if (name.value !== state.reviewer) name.value = state.reviewer || '';
}

function problems() {
  var out = [];
  DATA.cards.forEach(function (c) {
    var r = state.rows[c.id];
    if (!r || r.verdict !== 'ok') return;
    if (r.key.some(function (k) { return !String(k.value || '').trim(); }))
      out.push('№' + c.n + ' (#' + c.id + '): «Годится», но ключ пустой');
  });
  if (!String(state.reviewer || '').trim()) out.unshift('не указано имя проверяющего');
  return out;
}

function payload() {
  var rows = [];
  DATA.cards.forEach(function (c) {
    var r = state.rows[c.id];
    if (!r || !r.verdict) return;
    rows.push({id: c.id, verdict: r.verdict, reason: r.verdict === 'bad' ? (r.reason || '') : '',
               comment: r.comment || '', key: r.key});
  });
  return {format: DATA.format, seed: DATA.seed, chunk: DATA.chunk,
          reviewer: String(state.reviewer || '').trim(),
          exported_at: new Date().toISOString(), rows: rows};
}

function download() {
  var data = payload();
  var name = data.reviewer.replace(/[^0-9A-Za-zА-Яа-яЁё-]+/g, '_') || 'без_имени';
  var blob = new Blob([JSON.stringify(data, null, 1)], {type: 'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'ai_exam_review_chunk' + DATA.chunk + '_' + name + '.json';
  document.body.appendChild(a); a.click(); a.remove();
  // Выгрузка не блокируется никогда: проблемы только перечисляются.
  var warn = problems();
  document.getElementById('qx-warn').textContent =
    warn.length ? 'Файл скачан. Обратите внимание: ' + warn.join('; ') : '';
}

function activate(i) {
  var boxes = document.querySelectorAll('.qx-card');
  if (!boxes.length) return;
  current = Math.max(0, Math.min(boxes.length - 1, i));
  boxes.forEach(function (b, j) { b.classList.toggle('qx-active', j === current); });
  boxes[current].scrollIntoView({block: 'start', behavior: 'smooth'});
}

document.addEventListener('keydown', function (ev) {
  var tag = ev.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' ||
      ev.metaKey || ev.ctrlKey || ev.altKey) return;
  var boxes = document.querySelectorAll('.qx-card');
  var box = boxes[current];
  if (ev.key === '1' || ev.key === '2' || ev.key === '3') {
    setVerdict(Number(box.dataset.id), {'1': 'ok', '2': 'bad', '3': 'skip'}[ev.key]);
    ev.preventDefault();
  } else if (ev.key === 'ArrowDown' || ev.key === 'ArrowRight') {
    activate(current + 1); ev.preventDefault();
  } else if (ev.key === 'ArrowUp' || ev.key === 'ArrowLeft') {
    activate(current - 1); ev.preventDefault();
  }
});

document.querySelectorAll('.qx-card').forEach(function (box, j) {
  box.addEventListener('mousedown', function () {
    current = j;
    document.querySelectorAll('.qx-card').forEach(function (b, k) {
      b.classList.toggle('qx-active', k === j);
    });
  });
});
document.querySelectorAll('[data-f]').forEach(function (el) {
  el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input',
                      function () { setField(el); });
});
document.getElementById('qx-name').addEventListener('input', function () {
  state.reviewer = this.value; save();
});

DATA.cards.forEach(function (c) { paint(c.id); });
refresh();
var first = document.querySelector('.qx-card');
if (first) first.classList.add('qx-active');
if (window.renderMathInElement) {
  renderMathInElement(document.body, {delimiters: [
    {left: '$$', right: '$$', display: true},
    {left: '\\[', right: '\\]', display: true},
    {left: '$', right: '$', display: false},
    {left: '\\(', right: '\\)', display: false}], throwOnError: false});
}
"""


def _block(label, html, cls=''):
    if not html:
        return ''
    inner = '<div class="%s">%s</div>' % (cls, html) if cls else html
    return '<div class="qx-lbl">%s</div>%s' % (label, inner)


def _key_rows(candidate):
    rows = []
    for i, ask in enumerate(candidate['asks']):
        label = ask['label'] and escape(ask['label']) or ('ответ' if len(candidate['asks']) == 1 else '—')
        hint = ''
        if ask['kind'] != 'exact':
            hint = '<span class="qx-hint">ключ извлечён программой — проверьте</span>'
        rows.append(
            '<div class="qx-key"><span class="qx-plabel">%(label)s</span>'
            '<input type="text" class="qx-v" data-f="value" data-i="%(i)d" '
            'placeholder="число" value="%(value)s">'
            '<input type="text" class="qx-u" data-f="unit" data-i="%(i)d" '
            'placeholder="единицы" value="%(unit)s">'
            '<label><input type="checkbox" data-f="percent" data-i="%(i)d"%(checked)s> '
            'это проценты</label>'
            '<input type="text" class="qx-t" data-f="tol" data-i="%(i)d" '
            'placeholder="допуск">%(hint)s</div>'
            % {'label': label, 'i': i, 'value': escape(ask['value']),
               'unit': escape(ask['unit']),
               'checked': ' checked' if ask['percent'] else '', 'hint': hint})
    return ''.join(rows)


def card_html(candidate, record):
    """Карточка: метаданные, условие, подпункты, ответ и решение банка, форма."""
    parts_html = []
    for part in record['parts']:
        label = part['label'] and '<b>%s)</b> ' % escape(part['label']) or ''
        parts_html.append(
            '<div class="qx-part">%s%s%s</div>'
            % (label, render_field(part['statement'], {}),
               _block('ответ банка', render_field(part['answer'], {}), 'qx-answer')))
    answer = render_field(record['answer'], {})
    solution = render_field(record['solution'], {})
    reasons = ''.join('<option value="%s">%s</option>' % (key, escape(label))
                      for key, label in REASONS)
    title = render_field(record['title'], {})
    return (
        '<section class="qx-card" data-id="%(id)s">'
        '<div class="qx-meta"><b>№ %(n)s</b><span>#%(id)s</span>'
        '<span>%(topic)s</span><span>%(level)s</span>'
        '<span class="qx-url">%(url)s</span></div>'
        '%(title)s%(statement)s%(parts)s%(answer)s'
        '<details><summary>Решение банка</summary>%(solution)s</details>'
        '<div class="qx-form">'
        '<div class="qx-verdicts">'
        '<button data-v="ok" onclick="setVerdict(%(id)s,\'ok\')">1 — Годится</button>'
        '<button data-v="bad" onclick="setVerdict(%(id)s,\'bad\')">2 — Не годится</button>'
        '<button data-v="skip" onclick="setVerdict(%(id)s,\'skip\')">3 — Пропустить</button>'
        '</div>'
        '<div class="qx-why"><select data-f="reason">'
        '<option value="">— причина —</option>%(reasons)s</select></div>'
        '<div class="qx-lbl">ключ</div><div class="qx-keys">%(keys)s</div>'
        '<textarea data-f="comment" rows="1" placeholder="комментарий"></textarea>'
        '</div></section>'
    ) % {
        'id': candidate['id'], 'n': candidate['n'],
        'topic': escape(candidate['topic']), 'level': escape(candidate['level']),
        'url': SITE % candidate['id'],
        'title': title and '<div><b>%s</b></div>' % title or '',
        'statement': _block('условие', render_field(record['statement'], {})),
        'parts': ''.join(parts_html),
        'answer': _block('ответ банка', answer, 'qx-answer'),
        'solution': solution or '<p>решения нет</p>',
        'reasons': reasons, 'keys': _key_rows(candidate),
    }


def build_page(candidates, records_by_id, chunk, chunks, seed):
    """HTML одной пачки. `candidates` — строки candidates.jsonl этой пачки
    в порядке номера, `records_by_id` — записи банка (условие, решение)."""
    reserve = chunks > 1 and chunk == chunks
    data = {
        'format': FORMAT, 'seed': seed, 'chunk': chunk, 'reserve': reserve,
        'cards': [{'id': c['id'], 'n': c['n'],
                   'asks': [{k: a[k] for k in ('part_id', 'label', 'value', 'unit',
                                                'percent', 'kind')}
                            for a in c['asks']]}
                  for c in candidates],
    }
    blob = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    title = 'Экзамен ИИ v0 — пачка %d%s' % (chunk, ' (резерв)' if reserve else '')
    body = ''.join(card_html(c, records_by_id[c['id']]) for c in candidates)
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%(title)s</title>%(katex)s<style>%(css)s</style></head><body>'
        '<div class="qx-bar"><div class="qx-row">'
        '<h1>Пачка %(chunk)d из %(chunks)d</h1>%(reserve)s'
        '<label>Проверяющий: <input type="text" id="qx-name" placeholder="имя"></label>'
        '<span id="qx-count"></span><span class="qx-sp"></span>'
        '<button onclick="download()">Скачать разметку (JSON)</button></div>'
        '<div class="qx-warn" id="qx-warn"></div></div>'
        '<header class="qx-head"><p class="qx-lead">%(instruction)s<br>Клавиши: '
        '<b>1</b> — годится, <b>2</b> — не годится, <b>3</b> — пропустить, '
        'стрелки — соседняя карточка. Ответы сохраняются в браузере сами.</p></header>'
        '<main class="qx-wrap">%(body)s</main>'
        '<script type="application/json" id="qx-data">%(data)s</script>'
        '<script>%(js)s</script></body></html>'
    ) % {
        'title': title, 'katex': katex_head(), 'css': PAGE_CSS,
        'chunk': chunk, 'chunks': chunks,
        'reserve': ('<span class="qx-reserve">резерв — проверять, только если '
                    'после трёх пачек годных меньше 150</span>' if reserve else ''),
        'instruction': escape(INSTRUCTION), 'body': body, 'data': blob,
        'js': PAGE_JS,
    }
