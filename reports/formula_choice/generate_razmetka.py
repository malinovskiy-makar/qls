"""Собирает reports/formula_choice/razmetka.html — слепую страницу разметки.

Вход: pool.json (Фаза 1) + problems_data.json (данные задач, уже
отрендеренные тем же путём, что и страница сайта). Ничего не отправляет по
сети, ничего не тянет из базы сама — только читает эти два файла и статику
KaTeX с диска, и пишет один самодостаточный .html.

Запуск:
    venv313/Scripts/python.exe reports/formula_choice/generate_razmetka.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / 'razmetka.html'


def build_queries(pool):
    """Список запросов с ПЕРЕМЕШАННЫМ (зерно фиксировано) порядком id —
    порядок карточек не должен намекать на ранг ни одной формулы."""
    queries = []
    for q in pool['queries']:
        qid = q['query_id']
        ids = sorted(int(pid) for pid in pool['pool_per_query'][qid].keys())
        rnd = random.Random('razmetka-' + qid)
        rnd.shuffle(ids)
        queries.append({
            'query_id': qid,
            'text': q['text'],
            'topic': q.get('topic', ''),
            'kind': q.get('kind', ''),
            'ids': ids,
        })
    return queries


def main():
    pool = common.load_pool()
    problems = common.load_problems_data()
    queries = build_queries(pool)

    total_pairs = sum(len(q['ids']) for q in queries)
    print(f'Запросов: {len(queries)}, карточек всего: {total_pairs}')

    katex_css = common.katex_css_inline()
    katex_js = common.katex_js_inline()
    katex_autorender_js = common.katex_autorender_js_inline()
    katex_dollars_js = common.katex_dollars_js_inline()

    html = build_html(
        katex_css=katex_css,
        page_css=PAGE_CSS,
        katex_js=katex_js,
        katex_autorender_js=katex_autorender_js,
        katex_dollars_js=katex_dollars_js,
        page_js=PAGE_JS,
        queries_json=common.json_for_script(queries),
        problems_json=common.json_for_script(problems),
    )
    OUT_PATH.write_text(html, encoding='utf-8')
    print('Записано:', OUT_PATH, f'({OUT_PATH.stat().st_size / 1024:.0f} КБ)')


PAGE_CSS = """
:root {
  --bg: #f7f5f2; --surface: #ffffff; --ink: #262220; --ink-dim: #6b6360;
  --border: #e4dfd9; --accent: #4f8a8b; --accent-ink: #1f4d4e;
  --good: #3f8f5f; --unsure: #b98a2e; --bad: #b04a3f;
  --good-bg: #e9f5ee; --unsure-bg: #fbf1e0; --bad-bg: #fbeae7;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, Segoe UI, Arial, sans-serif; }
#topbar { position: sticky; top: 0; z-index: 20; background: var(--surface);
  border-bottom: 1px solid var(--border); padding: 10px 16px; }
#topbar .row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
#progress-total { font-weight: 600; }
#qnav { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.qpill { border: 1px solid var(--border); background: var(--surface);
  border-radius: 999px; padding: 4px 10px; font-size: 12.5px; cursor: pointer;
  color: var(--ink-dim); }
.qpill.active { border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
.qpill.done { background: var(--good-bg); border-color: var(--good); color: var(--good); }
#tools { margin-left: auto; display: flex; gap: 8px; }
button.btn { border: 1px solid var(--border); background: var(--surface);
  border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 13.5px; }
button.btn:hover { border-color: var(--accent); }
#querybar { position: sticky; top: 64px; z-index: 15; background: #fbfaf8;
  border-bottom: 1px solid var(--border); padding: 12px 16px; }
#querybar .qtext { font-size: 17px; font-weight: 600; }
#querybar .qmeta { color: var(--ink-dim); font-size: 13px; margin-top: 2px; }
#querybar .qcount { color: var(--ink-dim); font-size: 13px; margin-top: 4px; }
#card-wrap { max-width: 820px; margin: 20px auto 80px; padding: 0 16px; }
#card { background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px; }
#card .pid { color: var(--ink-dim); font-size: 13px; }
#card .ptitle { font-size: 18px; font-weight: 600; margin: 4px 0 10px; }
#card .hidden-banner { background: #fbf1e0; border: 1px solid #e8cf9c;
  color: #7a5a12; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 12px; }
#card .statement p { margin: 0 0 10px; }
#card .statement table { border-collapse: collapse; margin: 10px 0; }
#card .statement td, #card .statement th { border: 1px solid var(--border);
  padding: 4px 8px; }
#card .part { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); }
#card .part .label { font-weight: 600; }
#card .meta-line { margin-top: 14px; font-size: 13px; color: var(--ink-dim); }
#card .problem-figure { max-width: 100%; margin: 8px 0; }
#verdicts { display: flex; gap: 10px; margin: 18px auto 0; max-width: 820px; padding: 0 16px; }
.vbtn { flex: 1; border-radius: 10px; padding: 14px; font-size: 15px; font-weight: 600;
  border: 2px solid var(--border); background: var(--surface); cursor: pointer; }
.vbtn .hk { opacity: .55; font-weight: 400; font-size: 12.5px; margin-left: 6px; }
.vbtn.good.selected { border-color: var(--good); background: var(--good-bg); color: var(--good); }
.vbtn.unsure.selected { border-color: var(--unsure); background: var(--unsure-bg); color: var(--unsure); }
.vbtn.bad.selected { border-color: var(--bad); background: var(--bad-bg); color: var(--bad); }
#navrow { display: flex; justify-content: space-between; max-width: 820px;
  margin: 14px auto 0; padding: 0 16px; }
#footer-note { max-width: 820px; margin: 30px auto; padding: 0 16px; color: var(--ink-dim);
  font-size: 12.5px; }
#storage-warning { background: var(--bad-bg); color: var(--bad); border: 1px solid var(--bad);
  border-radius: 8px; padding: 8px 12px; margin: 10px 16px; font-size: 13px; display: none; }
input[type=file] { font-size: 12.5px; }
"""

PAGE_JS = """
var STORAGE_KEY = 'ekz_razmetka_v1';
var state = { verdicts: {} };  // key `${qid}::${pid}` -> 'good'|'unsure'|'bad'

function loadState() {
  try {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && parsed.verdicts) state.verdicts = parsed.verdicts;
    }
  } catch (e) {
    showStorageWarning();
  }
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    showStorageWarning();
  }
}

function showStorageWarning() {
  var el = document.getElementById('storage-warning');
  if (el) {
    el.style.display = 'block';
    el.textContent = 'Локальное хранилище недоступно — прогресс не сохранится '
      + 'между перезагрузками страницы. Чаще скачивайте разметку кнопкой ниже.';
  }
}

function vkey(qid, pid) { return qid + '::' + pid; }

var curQueryIdx = 0;
var curCardIdx = 0;

function totalMarked() { return Object.keys(state.verdicts).length; }
function totalPairs() {
  var n = 0;
  for (var i = 0; i < QUERIES.length; i++) n += QUERIES[i].ids.length;
  return n;
}

function queryMarkedCount(q) {
  var n = 0;
  for (var i = 0; i < q.ids.length; i++) {
    if (state.verdicts[vkey(q.query_id, q.ids[i])]) n++;
  }
  return n;
}

function renderTopbar() {
  document.getElementById('progress-total').textContent =
    'Размечено ' + totalMarked() + ' из ' + totalPairs();
  var nav = document.getElementById('qnav');
  nav.innerHTML = '';
  for (var i = 0; i < QUERIES.length; i++) {
    var q = QUERIES[i];
    var marked = queryMarkedCount(q);
    var pill = document.createElement('div');
    pill.className = 'qpill' + (i === curQueryIdx ? ' active' : '')
      + (marked === q.ids.length ? ' done' : '');
    pill.textContent = (i + 1) + '. ' + marked + '/' + q.ids.length;
    pill.title = q.topic;
    pill.onclick = (function (idx) {
      return function () { goToQuery(idx); };
    })(i);
    nav.appendChild(pill);
  }
}

function firstUnmarkedIndex(q) {
  for (var i = 0; i < q.ids.length; i++) {
    if (!state.verdicts[vkey(q.query_id, q.ids[i])]) return i;
  }
  return 0;
}

function goToQuery(idx) {
  curQueryIdx = idx;
  curCardIdx = firstUnmarkedIndex(QUERIES[idx]);
  renderAll();
}

function renderQuerybar() {
  var q = QUERIES[curQueryIdx];
  document.getElementById('qtext').textContent = q.text;
  document.getElementById('qmeta').textContent =
    (q.topic ? 'Тема: ' + q.topic : '') + (q.kind ? '  ·  Тип: ' + q.kind : '');
  document.getElementById('qcount').textContent =
    'Карточка ' + (curCardIdx + 1) + ' из ' + q.ids.length
    + ' в этом запросе  ·  размечено ' + queryMarkedCount(q) + ' из ' + q.ids.length;
}

function escapeAttr(s) { return String(s == null ? '' : s); }

function renderCard() {
  var q = QUERIES[curQueryIdx];
  var pid = q.ids[curCardIdx];
  var p = PROBLEMS[String(pid)];
  var el = document.getElementById('card');
  if (!p) {
    el.innerHTML = '<p>Нет данных о задаче id=' + pid + '</p>';
    return;
  }
  var html = '';
  html += '<div class="pid">id ' + p.id + (p.difficulty ? '  ·  сложность ' + p.difficulty : '') + '</div>';
  if (p.title) html += '<div class="ptitle">' + escapeAttr(p.title) + '</div>';
  if (!p.visible_in_catalog) {
    html += '<div class="hidden-banner">Сейчас скрыта из каталога'
      + (p.hidden_reason ? ': ' + escapeAttr(p.hidden_reason) : '') + '</div>';
  }
  html += '<div class="statement">' + p.statement_html + '</div>';
  for (var i = 0; i < p.parts.length; i++) {
    var part = p.parts[i];
    html += '<div class="part"><span class="label">(' + escapeAttr(part.label) + ')</span> '
      + part.statement_html + '</div>';
  }
  var metaBits = [];
  if (p.topics && p.topics.length) metaBits.push('Темы: ' + p.topics.join(', '));
  if (p.tags && p.tags.length) metaBits.push('Теги: ' + p.tags.join(', '));
  if (metaBits.length) html += '<div class="meta-line">' + metaBits.join(' · ') + '</div>';
  el.innerHTML = html;
  renderMathIn(el);
}

function renderVerdictButtons() {
  var q = QUERIES[curQueryIdx];
  var pid = q.ids[curCardIdx];
  var current = state.verdicts[vkey(q.query_id, pid)];
  ['good', 'unsure', 'bad'].forEach(function (v) {
    var btn = document.getElementById('vbtn-' + v);
    btn.classList.toggle('selected', current === v);
  });
}

function setVerdict(v) {
  var q = QUERIES[curQueryIdx];
  var pid = q.ids[curCardIdx];
  state.verdicts[vkey(q.query_id, pid)] = v;
  saveState();
  renderTopbar();
  renderVerdictButtons();
  renderQuerybar();
  // Автопереход к следующей неразмеченной карточке этого запроса.
  setTimeout(function () {
    var nextIdx = curCardIdx + 1;
    if (nextIdx < q.ids.length) {
      curCardIdx = nextIdx;
      renderAll();
    } else {
      renderAll();
    }
  }, 120);
}

function goBack() {
  if (curCardIdx > 0) { curCardIdx -= 1; renderAll(); }
  else if (curQueryIdx > 0) {
    curQueryIdx -= 1;
    curCardIdx = QUERIES[curQueryIdx].ids.length - 1;
    renderAll();
  }
}

function goNext() {
  var q = QUERIES[curQueryIdx];
  if (curCardIdx < q.ids.length - 1) { curCardIdx += 1; renderAll(); }
  else if (curQueryIdx < QUERIES.length - 1) { goToQuery(curQueryIdx + 1); }
}

function renderAll() {
  renderTopbar();
  renderQuerybar();
  renderCard();
  renderVerdictButtons();
}

function downloadMarkup() {
  var rows = [];
  for (var i = 0; i < QUERIES.length; i++) {
    var q = QUERIES[i];
    for (var j = 0; j < q.ids.length; j++) {
      var pid = q.ids[j];
      var v = state.verdicts[vkey(q.query_id, pid)];
      if (v) rows.push({ query_id: q.query_id, problem_id: pid, verdict: v });
    }
  }
  var blob = new Blob([JSON.stringify(rows, null, 1)], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'razmetka_' + rows.length + '.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function loadMarkupFile(file) {
  var reader = new FileReader();
  reader.onload = function () {
    try {
      var rows = JSON.parse(reader.result);
      rows.forEach(function (r) {
        if (r && r.query_id && r.problem_id != null && r.verdict) {
          state.verdicts[vkey(r.query_id, r.problem_id)] = r.verdict;
        }
      });
      saveState();
      renderAll();
      alert('Загружено ' + rows.length + ' отметок.');
    } catch (e) {
      alert('Не удалось прочитать файл: ' + e);
    }
  };
  reader.readAsText(file, 'utf-8');
}

// ── KaTeX: та же последовательность, что и на сайте (_katex_dollars.html) ──
function renderMathIn(root) {
  if (typeof maskEscapedDollars === 'function') maskEscapedDollars(root);
  if (typeof renderMathInElement === 'function') {
    renderMathInElement(root, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\\\[', right: '\\\\]', display: true },
        { left: '\\\\(', right: '\\\\)', display: false }
      ],
      throwOnError: false,
      trust: false
    });
  }
  if (typeof fixCurrencyDollars === 'function') fixCurrencyDollars(root);
}

document.addEventListener('DOMContentLoaded', function () {
  loadState();
  document.getElementById('vbtn-good').onclick = function () { setVerdict('good'); };
  document.getElementById('vbtn-unsure').onclick = function () { setVerdict('unsure'); };
  document.getElementById('vbtn-bad').onclick = function () { setVerdict('bad'); };
  document.getElementById('btn-back').onclick = goBack;
  document.getElementById('btn-next').onclick = goNext;
  document.getElementById('btn-download').onclick = downloadMarkup;
  document.getElementById('file-restore').addEventListener('change', function (e) {
    if (e.target.files[0]) loadMarkupFile(e.target.files[0]);
  });
  document.addEventListener('keydown', function (e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === '1') setVerdict('good');
    else if (e.key === '2') setVerdict('unsure');
    else if (e.key === '3') setVerdict('bad');
    else if (e.key === 'ArrowLeft') goBack();
    else if (e.key === 'ArrowRight') goNext();
  });
  goToQuery(0);
});
"""

def build_html(katex_css, page_css, katex_js, katex_autorender_js,
                katex_dollars_js, page_js, queries_json, problems_json):
    """Плоская конкатенация, НЕ .format()/Template: CSS и JS набиты фигурными
    скобками, и любой шаблонизатор с плейсхолдерами в {} на них подавится."""
    parts = [
        '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<title>Разметка пула — линейка выбора формулы</title>\n',
        '<style>', katex_css, '</style>\n',
        '<style>', page_css, '</style>\n',
        '</head>\n<body>\n',
        '<div id="topbar">\n  <div class="row">\n    <div id="progress-total"></div>\n',
        '    <div id="tools">\n      <input type="file" id="file-restore" accept="application/json">\n',
        '      <button class="btn" id="btn-download">Скачать разметку</button>\n    </div>\n  </div>\n',
        '  <div id="qnav"></div>\n</div>\n',
        '<div id="storage-warning"></div>\n',
        '<div id="querybar">\n  <div class="qtext" id="qtext"></div>\n',
        '  <div class="qmeta" id="qmeta"></div>\n  <div class="qcount" id="qcount"></div>\n</div>\n',
        '<div id="card-wrap"><div id="card"></div></div>\n',
        '<div id="verdicts">\n',
        '  <button class="vbtn good" id="vbtn-good">✅ Годится <span class="hk">1</span></button>\n',
        '  <button class="vbtn unsure" id="vbtn-unsure">❓ Спорно <span class="hk">2</span></button>\n',
        '  <button class="vbtn bad" id="vbtn-bad">❌ Не годится <span class="hk">3</span></button>\n',
        '</div>\n',
        '<div id="navrow">\n  <button class="btn" id="btn-back">← Назад</button>\n',
        '  <button class="btn" id="btn-next">Вперёд →</button>\n</div>\n',
        '<div id="footer-note">\n',
        '  Разметка слепая: какая формула нашла задачу и на каком месте — не показывается.\n',
        '  Прогресс сохраняется в этом браузере автоматически; кнопка «Скачать разметку»\n',
        '  выгружает JSON в любой момент (можно за несколько запросов до конца) — его же\n',
        '  можно загрузить обратно файлом выше, если открыть страницу на другой машине\n',
        '  или после очистки браузера.\n</div>\n',
        '<script>', katex_js, '</script>\n',
        '<script>', katex_autorender_js, '</script>\n',
        '<script>', katex_dollars_js, '</script>\n',
        '<script>\nvar QUERIES = ', queries_json, ';\nvar PROBLEMS = ', problems_json, ';\n</script>\n',
        '<script>', page_js, '</script>\n',
        '</body>\n</html>\n',
    ]
    return ''.join(parts)


if __name__ == '__main__':
    main()
