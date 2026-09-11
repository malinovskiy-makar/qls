# -*- coding: utf-8 -*-
"""Фаза 4: страница side-by-side для глаз владельца.

Четыре колонки на запрос, в каждой топ-10 карточек. Цвет — итоговая
метка, отдельная пометка — метка владельца, если она есть. Без внешних
библиотек и без backdrop-filter.

Файл локальный, в git не идёт: он весит мегабайты и пересобирается
отсюда одной командой.

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/build_side_by_side.py
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.getcwd())

import run_metrics  # noqa: E402

OUT = os.path.join(HERE, 'side_by_side.html')
SITE = 'http://127.0.0.1:8000/catalog/problem/%d/'

#: Колонки страницы. S4 появится, когда заработает ключ Anthropic.
COLUMNS = [('S0_dense', 'S0 плотный'), ('S2_rrf', 'S2 слияние'),
           ('S3_glm-flash', 'S3 GLM-5.3-Flash'), ('S3_glm', 'S3 GLM-5.3')]

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1c19;--muted:#6b6862;--line:#e2ded6;
--good:#1f7a4d;--goodbg:#e8f5ee;--maybe:#8a6d1f;--maybebg:#fbf3dd;
--bad:#7a2f2f;--badbg:#f7eaea;--card:#fff;--own:#2f5d7a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
padding:14px 20px;z-index:5}
h1{margin:0 0 8px;font-size:17px;font-weight:600}
.meta{color:var(--muted);font-size:13px}
.filters{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
button{font:inherit;padding:5px 12px;border:1px solid var(--line);
background:var(--card);border-radius:999px;cursor:pointer;color:var(--fg)}
button[aria-pressed="true"]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.query{padding:18px 20px;border-bottom:1px solid var(--line)}
.qtext{font-size:15px;font-weight:600;margin:0 0 4px}
.qmeta{color:var(--muted);font-size:12px;margin-bottom:12px}
.cols{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:1100px){.cols{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.cols{grid-template-columns:1fr}}
.col h3{margin:0 0 8px;font-size:12px;text-transform:uppercase;
letter-spacing:.04em;color:var(--muted);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-left-width:4px;
border-radius:8px;padding:8px 10px;margin-bottom:6px}
.card.l2{border-left-color:var(--good);background:var(--goodbg)}
.card.l1{border-left-color:var(--maybe);background:var(--maybebg)}
.card.l0{border-left-color:var(--bad);background:var(--badbg)}
.card.ln{border-left-color:var(--line)}
.card a{color:inherit;text-decoration:none;font-weight:600}
.card a:hover{text-decoration:underline}
.find{color:var(--muted);font-size:12px;margin-top:3px}
.tags{color:var(--muted);font-size:11px;margin-top:3px}
.badges{margin-top:4px;display:flex;gap:5px;flex-wrap:wrap}
.b{font-size:10px;padding:1px 6px;border-radius:999px;border:1px solid var(--line);
color:var(--muted);background:var(--card)}
.b.own{border-color:var(--own);color:var(--own)}
.why{font-size:12px;margin-top:4px;font-style:italic}
"""

JS = """
var buttons=document.querySelectorAll('[data-filter]');
function apply(kind){
 buttons.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.filter===kind)});
 document.querySelectorAll('.query').forEach(function(q){
  q.hidden = kind!=='все' && q.dataset.type!==kind;
 });
}
buttons.forEach(function(b){b.addEventListener('click',function(){apply(b.dataset.filter)})});
apply('все');
"""

NAMES = {2: 'годится', 1: 'спорно', 0: 'не годится'}


def card_html(pid, corpus, label, owner_label, why=None):
    row = corpus.get(pid, {})
    css = 'ln' if label is None else 'l%d' % label
    title = html.escape(row.get('title') or 'без названия')
    find = html.escape((row.get('find') or '')[:110])
    tags = html.escape(', '.join((row.get('topics') or [])[:1]
                                 + (row.get('tags') or [])[:3]))
    badges = ['<span class="b">%s</span>' % NAMES[label]] if label is not None else []
    if owner_label is not None:
        badges.append('<span class="b own">владелец: %s</span>'
                      % NAMES[owner_label])
    parts = ['<div class="card %s">' % css,
             '<a href="%s" target="_blank">%s</a>' % (SITE % pid, title)]
    if find:
        parts.append('<div class="find">%s</div>' % find)
    if tags:
        parts.append('<div class="tags">%s</div>' % tags)
    if badges:
        parts.append('<div class="badges">%s</div>' % ''.join(badges))
    if why:
        parts.append('<div class="why">%s</div>' % html.escape(why))
    parts.append('</div>')
    return ''.join(parts)


def main():
    pool = [json.loads(line) for line in
            open(os.path.join(HERE, 'pool.jsonl'), encoding='utf-8')]
    corpus = {}
    with open(os.path.join(HERE, 'corpus.jsonl'), encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            corpus[row['id']] = row

    runs = run_metrics.runs_for(pool)
    agreement = json.load(open(os.path.join(HERE, 'agreement.json'),
                               encoding='utf-8'))
    labels = run_metrics.load_labels(agreement['primary'])
    owner = {}
    with open(os.path.join(HERE, 'labels_final.jsonl'), encoding='utf-8') as h:
        for line in h:
            if not line.strip():
                continue
            row = json.loads(line)
            if row['source'] == 'владелец':
                owner.setdefault(row['query_id'], {})[row['problem_id']] = \
                    row['label']

    columns = [(key, title) for key, title in COLUMNS if runs.get(key)]
    body = []
    for row in pool:
        qid = row['query_id']
        cols = []
        for key, title in columns:
            ranked = runs[key].get(qid, [])[:10]
            cards = ''.join(
                card_html(pid, corpus, labels.get(qid, {}).get(pid),
                          owner.get(qid, {}).get(pid))
                for pid in ranked)
            cols.append('<div class="col"><h3>%s</h3>%s</div>'
                        % (html.escape(title), cards or '<div class="tags">пусто</div>'))
        body.append(
            '<section class="query" data-type="%s"><p class="qtext">%s</p>'
            '<p class="qmeta">%s · %s · пул %d · %s</p>'
            '<div class="cols">%s</div></section>'
            % (row['type'], html.escape(row['text']), qid, row['type'],
               len(row['pool']),
               ('якорь в пуле' if row['anchor_in_pool']
                else (row.get('anchor_why') or 'без якоря')),
               ''.join(cols)))

    page = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>LLM-слой над поиском: выдачи рядом</title>'
        '<style>%s</style></head><body>'
        '<header><h1>Выдачи систем рядом, %d запросов</h1>'
        '<p class="meta">Цвет карточки — итоговая метка судей по правилу '
        '«%s». Синяя пометка — ваша ручная метка, она сильнее машинной. '
        'Ссылка ведёт на задачу в локальном каталоге.</p>'
        '<div class="filters">'
        '<button data-filter="все" aria-pressed="true">все</button>'
        '<button data-filter="описательный">только описательные</button>'
        '<button data-filter="короткий">только короткие</button>'
        '</div></header>%s<script>%s</script></body></html>'
        % (CSS, len(pool), agreement['primary'], ''.join(body), JS))

    with open(OUT, 'w', encoding='utf-8') as handle:
        handle.write(page)
    print('Страница собрана: %s (%.1f МБ), колонок %d'
          % (OUT, os.path.getsize(OUT) / 1e6, len(columns)))


if __name__ == '__main__':
    main()
