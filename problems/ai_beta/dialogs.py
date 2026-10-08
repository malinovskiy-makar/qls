"""Выгрузка разговоров чата и читалка для людей (сессия «Данные беты 1»).

Основа — `chat_export`: строка на разговор (`thread`), реплики по времени;
реплика без номера разговора — отдельный разговор `turn-<pk>`. Сверх неё:
отметка «сотрудник», темы задачи, пути файлов ОТНОСИТЕЛЬНО папки media.

Читалка (`reader_html`) — по образцу `dedup_human_review_html`: открывается
с file:// без сети, KaTeX вшит, отметки копятся в localStorage и выгружаются
одним JSON `ai_beta_marks/1`. Фото — по относительному пути `media/chat/…`
рядом со страницей.

⚠️ ИЗ ПРОФИЛЯ — ТОЛЬКО НОМЕР. Ни имени, ни логина, ни почты в выгрузку и на
страницу не попадает; сторож — `problems/tests/test_ai_beta_dialogs.py`.
Тексты учеников в выгрузке есть — ради них она и делается, — поэтому файлы
живут только вне репозитория.
"""
import json

from django.utils.html import escape

from problems.management.commands.dedup_human_review_html import katex_head, render_field

MARKS_FORMAT = 'ai_beta_marks/1'
#: Вид ситуации для «Репетитор-30»: код → подпись.
KINDS = (
    ('answer_request', 'просит готовый ответ'),
    ('stuck', 'застрял на шаге'),
    ('wrong_solution', 'прислал неверное решение'),
    ('theory', 'вопрос по теории'),
    ('photo', 'прислал фото'),
    ('other', 'другое'),
)


def _rel(path):
    """Путь файла относительно папки media: прямые слэши, без ведущего."""
    return str(path or '').replace('\\', '/').lstrip('/')


def _files(turn):
    attachments = {a.pk: a for a in turn.attachments.all()}
    if turn.attachment_id and turn.attachment_id not in attachments and turn.attachment:
        attachments[turn.attachment_id] = turn.attachment
    return [{'path': _rel(a.file.name), 'mime': a.mime,
             'pages': [_rel(p) for p in (a.pages_json or [])]}
            for _pk, a in sorted(attachments.items())]


def collect_threads(turns, staff=frozenset(), topics=None):
    """Реплики (QuerySet ChatTurn по времени) → список разговоров."""
    topics = topics or {}
    threads = {}
    for turn in turns:
        key = str(turn.thread) if turn.thread else 'turn-%d' % turn.pk
        entry = threads.setdefault(key, {
            'thread': key, 'user_id': turn.user_id, 'staff': turn.user_id in staff,
            'problem_id': turn.problem_id, 'topics': topics.get(turn.problem_id, []),
            'turns': []})
        entry['turns'].append({
            'id': turn.pk,
            'time': turn.created_at.isoformat(),
            'problem_id': turn.problem_id,
            'mode': turn.mode,
            'user_text': turn.user_text,
            'quote': turn.quote,
            'quote_source': turn.quote_source,
            'files': _files(turn),
            'vision_text': turn.vision_text,
            'reply': turn.reply,
            'error': turn.error,
            'latency_ms': turn.latency_ms,
            'cost_usd': str(turn.cost_usd),
        })
    for entry in threads.values():
        entry['turns'].sort(key=lambda t: (t['time'], t['id']))
    return sorted(threads.values(), key=lambda e: (e['turns'][0]['time'], e['thread']))


def statement_html(problem):
    """Условие задачи с подпунктами — та же отрисовка, что в каталоге
    (картинки условия не вшиваются: страница про разговор, а не про задачу)."""
    html = render_field(problem.statement, {})
    for part in problem.parts.all():
        label = '<b>%s)</b> ' % escape(part.label) if part.label else ''
        html += '<div class="rd-part">%s%s</div>' % (label, render_field(part.statement, {}))
    return html


def reader_html(threads, statements, media_prefix='media/'):
    """Самодостаточная страница: список разговоров слева, разговор справа."""
    data = {'format': MARKS_FORMAT, 'media': media_prefix, 'kinds': KINDS,
            'threads': threads, 'statements': {str(k): v for k, v in statements.items()}}
    blob = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Бета: разговоры с ИИ</title>%(katex)s<style>%(css)s</style></head><body>'
        '<div class="rd-bar"><b>Разговоры беты</b><span id="rd-count"></span>'
        '<span class="rd-sp"></span><span id="rd-marked"></span>'
        '<button type="button" id="rd-dl">Скачать отметки (JSON)</button></div>'
        '<div class="rd-wrap"><aside class="rd-side"><div class="rd-filters">'
        '<label>Режим <select id="f-mode"><option value="">любой</option>'
        '<option value="free">free</option><option value="theory">theory</option>'
        '<option value="method">method</option><option value="check">check</option></select></label>'
        '<label>Длина <select id="f-len"><option value="">любая</option>'
        '<option value="1">1 реплика</option><option value="2-3">2–3</option>'
        '<option value="4+">4 и больше</option></select></label>'
        '<label>Кто <select id="f-staff"><option value="">все</option>'
        '<option value="no">без сотрудников</option><option value="yes">только сотрудники</option>'
        '</select></label>'
        '<label><input type="checkbox" id="f-photo"> есть фото</label>'
        '<label><input type="checkbox" id="f-error"> есть ошибка</label>'
        '<label><input type="checkbox" id="f-cand"> только кандидаты</label>'
        '</div><ol class="rd-list" id="rd-list"></ol></aside>'
        '<main class="rd-main" id="rd-main"><p class="rd-empty">Выберите разговор слева.</p></main>'
        '</div><script type="application/json" id="rd-data">%(data)s</script>'
        '<script>%(js)s</script></body></html>'
    ) % {'katex': katex_head(), 'css': CSS, 'data': blob, 'js': JS}


CSS = """
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;color:#1d1d1f;background:#f6f5f2}
.rd-bar{position:sticky;top:0;z-index:2;display:flex;gap:12px;align-items:center;padding:10px 16px;
background:#fff;border-bottom:1px solid #ddd}.rd-sp{flex:1}
.rd-bar button{font:inherit;padding:6px 12px;border-radius:8px;border:1px solid #2b5;background:#2b5;color:#fff;cursor:pointer}
.rd-wrap{display:flex;height:calc(100vh - 50px)}
.rd-side{width:340px;flex:none;overflow:auto;border-right:1px solid #ddd;background:#fff}
.rd-filters{display:flex;flex-wrap:wrap;gap:6px 12px;padding:10px;border-bottom:1px solid #eee;font-size:13px}
.rd-list{list-style:none;margin:0;padding:0}
.rd-list li{padding:8px 10px;border-bottom:1px solid #f0f0f0;cursor:pointer;font-size:13px}
.rd-list li:hover{background:#f4f8ff}.rd-list li.on{background:#e6efff}
.rd-list li.cand{border-left:4px solid #2b5}.rd-tag{display:inline-block;margin-right:6px;color:#666}
.rd-main{flex:1;overflow:auto;padding:16px 24px;max-width:980px}
.rd-meta{color:#555;font-size:13px;margin-bottom:8px}
.rd-marks{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px;background:#fff;
border:1px solid #ddd;border-radius:10px;margin:10px 0}
.rd-marks textarea{flex:1 1 100%;font:inherit;min-height:48px}
details.rd-stmt{background:#fff;border:1px solid #ddd;border-radius:10px;padding:8px 12px;margin:8px 0}
.rd-turn{margin:14px 0}.rd-q,.rd-a{white-space:pre-wrap;padding:10px 12px;border-radius:10px}
.rd-q{background:#e9f2ff}.rd-a{background:#fff;border:1px solid #e3e3e3;margin-top:6px}
.rd-err{color:#b00020;font-size:13px;margin-top:4px}
.rd-quote{border-left:3px solid #999;padding-left:8px;color:#555;white-space:pre-wrap;margin-bottom:4px}
.rd-info{color:#777;font-size:12px}.rd-photo{display:flex;gap:10px;align-items:flex-start;margin-top:6px}
.rd-photo img{max-width:420px;border:1px solid #ccc;border-radius:6px}
.rd-vision{flex:1;white-space:pre-wrap;font-size:13px;background:#fffbe8;padding:8px;border-radius:6px}
"""

JS = r"""
var DATA = JSON.parse(document.getElementById('rd-data').textContent);
var KEY = DATA.format;
var marks = {};
try { marks = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { marks = {}; }
function save() { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} counts(); }
function mark(id) { return marks[id] || (marks[id] = {candidate: false, kind: '', note: ''}); }
function el(tag, cls, text) {
  var n = document.createElement(tag); if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text; return n;
}
function has(t, f) { return t.turns.some(f); }
var current = null;

function passes(t) {
  var mode = document.getElementById('f-mode').value;
  var len = document.getElementById('f-len').value;
  var staff = document.getElementById('f-staff').value;
  var n = t.turns.length;
  if (mode && !has(t, function (x) { return x.mode === mode; })) return false;
  if (len === '1' && n !== 1) return false;
  if (len === '2-3' && (n < 2 || n > 3)) return false;
  if (len === '4+' && n < 4) return false;
  if (staff === 'no' && t.staff) return false;
  if (staff === 'yes' && !t.staff) return false;
  if (document.getElementById('f-photo').checked && !has(t, function (x) { return x.files.length; })) return false;
  if (document.getElementById('f-error').checked && !has(t, function (x) { return x.error; })) return false;
  if (document.getElementById('f-cand').checked && !(marks[t.thread] || {}).candidate) return false;
  return true;
}

function counts() {
  var shown = document.querySelectorAll('#rd-list li').length;
  document.getElementById('rd-count').textContent = 'показано ' + shown + ' из ' + DATA.threads.length;
  var c = Object.keys(marks).filter(function (k) { return marks[k].candidate; }).length;
  document.getElementById('rd-marked').textContent = 'кандидатов: ' + c;
}

function list() {
  var ol = document.getElementById('rd-list'); ol.innerHTML = '';
  DATA.threads.forEach(function (t, i) {
    if (!passes(t)) return;
    var li = el('li'); li.dataset.thread = t.thread;
    if ((marks[t.thread] || {}).candidate) li.classList.add('cand');
    if (current === t.thread) li.classList.add('on');
    var modes = {}; t.turns.forEach(function (x) { modes[x.mode] = 1; });
    li.appendChild(el('span', 'rd-tag', '№' + (i + 1)));
    li.appendChild(el('span', 'rd-tag', 'задача ' + (t.problem_id || '—')));
    li.appendChild(el('span', 'rd-tag', t.turns.length + ' репл.'));
    li.appendChild(el('span', 'rd-tag', Object.keys(modes).join('/')));
    if (has(t, function (x) { return x.files.length; })) li.appendChild(el('span', 'rd-tag', 'фото'));
    if (has(t, function (x) { return x.error; })) li.appendChild(el('span', 'rd-tag', 'ошибка'));
    if (t.staff) li.appendChild(el('span', 'rd-tag', 'сотрудник'));
    li.appendChild(el('div', 'rd-info', t.turns[0].time.slice(0, 16).replace('T', ' ') + ' · ученик №' + t.user_id));
    li.onclick = function () { show(t.thread); };
    ol.appendChild(li);
  });
  counts();
}

function show(id) {
  current = id;
  var t = DATA.threads.filter(function (x) { return x.thread === id; })[0];
  var main = document.getElementById('rd-main'); main.innerHTML = '';
  main.appendChild(el('div', 'rd-meta', 'Разговор ' + t.thread + ' · ученик №' + t.user_id +
    (t.staff ? ' (сотрудник)' : '') + ' · задача ' + (t.problem_id || '—') +
    (t.topics.length ? ' · ' + t.topics.join(', ') : '')));
  var m = mark(t.thread), box = el('div', 'rd-marks');
  var lab = el('label'), cb = el('input'); cb.type = 'checkbox'; cb.checked = !!m.candidate;
  cb.onchange = function () { m.candidate = cb.checked; save(); list(); };
  lab.appendChild(cb); lab.appendChild(document.createTextNode(' кандидат в «Репетитор-30»'));
  var sel = el('select'); sel.appendChild(el('option', '', '— вид ситуации —')).value = '';
  DATA.kinds.forEach(function (k) { var o = el('option', '', k[1]); o.value = k[0]; sel.appendChild(o); });
  sel.value = m.kind || ''; sel.onchange = function () { m.kind = sel.value; save(); };
  var note = el('textarea'); note.placeholder = 'заметка'; note.value = m.note || '';
  note.oninput = function () { m.note = note.value; save(); };
  box.appendChild(lab); box.appendChild(sel); box.appendChild(note); main.appendChild(box);
  var stmt = DATA.statements[String(t.problem_id)];
  if (stmt) {
    var d = el('details', 'rd-stmt'); d.appendChild(el('summary', '', 'Условие задачи'));
    var body = el('div'); body.innerHTML = stmt; d.appendChild(body); main.appendChild(d);
  }
  t.turns.forEach(function (x) {
    var box = el('div', 'rd-turn');
    box.appendChild(el('div', 'rd-info', x.time.slice(0, 19).replace('T', ' ') + ' · режим ' + x.mode +
      ' · ' + (x.latency_ms / 1000).toFixed(1) + ' с · $' + x.cost_usd));
    var q = el('div', 'rd-q');
    if (x.quote) q.appendChild(el('div', 'rd-quote', x.quote));
    q.appendChild(document.createTextNode(x.user_text || '(без текста)'));
    box.appendChild(q);
    x.files.forEach(function (f) {
      var pics = f.pages.length ? f.pages : (f.mime.indexOf('image/') === 0 ? [f.path] : []);
      var row = el('div', 'rd-photo'), col = el('div');
      pics.forEach(function (p) { var img = el('img'); img.src = DATA.media + p; img.alt = 'фото решения'; col.appendChild(img); });
      if (!pics.length) col.appendChild(el('div', 'rd-info', f.mime + ': ' + f.path));
      row.appendChild(col);
      row.appendChild(el('div', 'rd-vision', x.vision_text ? 'Расшифровка: ' + x.vision_text : 'Расшифровка пустая'));
      box.appendChild(row);
    });
    if (x.reply) box.appendChild(el('div', 'rd-a', x.reply));
    if (x.error) box.appendChild(el('div', 'rd-err', 'Ошибка: ' + x.error));
    main.appendChild(box);
  });
  if (window.renderMathInElement) {
    renderMathInElement(main, {delimiters: [
      {left: '$$', right: '$$', display: true}, {left: '\\[', right: '\\]', display: true},
      {left: '$', right: '$', display: false}, {left: '\\(', right: '\\)', display: false}],
      throwOnError: false});
  }
  list();
}

document.getElementById('rd-dl').onclick = function () {
  var rows = Object.keys(marks).filter(function (k) {
    var m = marks[k]; return m.candidate || m.kind || m.note;
  }).map(function (k) { return {thread: k, candidate: !!marks[k].candidate, kind: marks[k].kind || '', note: marks[k].note || ''}; });
  var blob = new Blob([JSON.stringify({format: DATA.format, rows: rows}, null, 1)], {type: 'application/json'});
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'ai_beta_marks.json';
  document.body.appendChild(a); a.click(); a.remove();
};
['f-mode', 'f-len', 'f-staff', 'f-photo', 'f-error', 'f-cand'].forEach(function (id) {
  document.getElementById(id).onchange = list;
});
list();
"""
