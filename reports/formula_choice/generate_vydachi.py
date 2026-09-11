"""Собирает reports/formula_choice/vydachi.html — просмотр выдач (НЕ слепой).

По каждому из 10 запросов подряд топ-10 каждой из 16 формул: id, заголовок,
начало условия, и — если размечено — вердикт владельца цветом. Формулы
здесь ПОДПИСАНЫ: слепота нужна только на этапе разметки (razmetka.html),
а это страница для чтения готового результата.

Запуск (после того как владелец скачал разметку из razmetka.html):
    venv313/Scripts/python.exe reports/formula_choice/generate_vydachi.py razmetka.json

Без аргумента строит демо-версию с пометкой «нет разметки» везде — годится
только чтобы проверить, что страница вообще собирается корректно.
"""
import html as html_mod
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / 'vydachi.html'

VERDICT_LABEL = {'good': 'годится', 'unsure': 'спорно', 'bad': 'не годится', None: 'нет разметки'}
VERDICT_CLASS = {'good': 'v-good', 'unsure': 'v-unsure', 'bad': 'v-bad', None: 'v-none'}

TAG_RE = re.compile(r'<[^>]+>')


def load_markup(path):
    import json
    if path is None:
        return {}
    with open(path, encoding='utf-8') as fh:
        rows = json.load(fh)
    return {(r['query_id'], int(r['problem_id'])): r['verdict'] for r in rows}


def plain_preview(statement_html, limit=170):
    text = TAG_RE.sub(' ', statement_html or '')
    text = html_mod.unescape(text)
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[:limit].rstrip() + '…'
    return text


def build_section_html(pool, problems, verdicts, qid):
    q = next(qq for qq in pool['queries'] if qq['query_id'] == qid)
    merged = pool['pool_per_query'][qid]
    parts = [
        '<section class="query-block">',
        '<h2>', html_mod.escape(q['text']), '</h2>',
        '<div class="qmeta">Тема: ', html_mod.escape(q.get('topic', '')),
        '  ·  Тип: ', html_mod.escape(q.get('kind', '')), '</div>',
    ]
    for name in pool['formulas']:
        ranked = sorted(
            ((int(pid), info[name]['rank'], info[name]['score'])
             for pid, info in merged.items() if name in info),
            key=lambda t: t[1],
        )
        parts.append('<h3 class="formula-name">' + html_mod.escape(name) + '</h3>')
        parts.append('<table class="results"><thead><tr>'
                      '<th>#</th><th>id</th><th>заголовок</th>'
                      '<th>начало условия</th><th>вердикт</th></tr></thead><tbody>')
        for pid, rank, score in ranked:
            p = problems.get(str(pid), {})
            title = p.get('title') or '(без заголовка)'
            preview = plain_preview(p.get('statement_html', ''))
            verdict = verdicts.get((qid, pid))
            parts.append(
                '<tr><td>%d</td><td>%d</td><td>%s</td><td class="prev">%s</td>'
                '<td><span class="badge %s">%s</span></td></tr>' % (
                    rank, pid, html_mod.escape(title), html_mod.escape(preview),
                    VERDICT_CLASS[verdict], VERDICT_LABEL[verdict],
                )
            )
        parts.append('</tbody></table>')
    parts.append('</section>')
    return ''.join(parts)


PAGE_CSS = """
:root { --bg:#f7f5f2; --surface:#fff; --ink:#262220; --ink-dim:#6b6360; --border:#e4dfd9;
  --good:#3f8f5f; --good-bg:#e9f5ee; --unsure:#b98a2e; --unsure-bg:#fbf1e0;
  --bad:#b04a3f; --bad-bg:#fbeae7; --none:#9a938d; --none-bg:#efece7; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system, Segoe UI, Arial, sans-serif; }
#wrap { max-width: 1100px; margin: 0 auto; padding: 20px 16px 80px; }
#toc { background: var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:12px 16px; margin-bottom: 24px; }
#toc a { display:inline-block; margin:2px 8px 2px 0; font-size:13px; }
.query-block { background: var(--surface); border:1px solid var(--border); border-radius:12px;
  padding: 16px 20px; margin-bottom: 24px; }
.query-block h2 { margin: 0 0 4px; font-size:18px; }
.qmeta { color: var(--ink-dim); font-size:13px; margin-bottom: 10px; }
.formula-name { margin: 18px 0 6px; font-size:13.5px; color: var(--ink-dim);
  text-transform: none; border-top: 1px dashed var(--border); padding-top: 10px; }
table.results { width:100%; border-collapse: collapse; font-size: 13px; margin-bottom: 4px; }
table.results th, table.results td { border-bottom: 1px solid var(--border);
  padding: 4px 6px; text-align: left; vertical-align: top; }
table.results th { color: var(--ink-dim); font-weight: 600; }
td.prev { color: var(--ink-dim); }
.badge { display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; }
.badge.v-good { background: var(--good-bg); color: var(--good); }
.badge.v-unsure { background: var(--unsure-bg); color: var(--unsure); }
.badge.v-bad { background: var(--bad-bg); color: var(--bad); }
.badge.v-none { background: var(--none-bg); color: var(--none); }
"""


def main():
    markup_path = sys.argv[1] if len(sys.argv) > 1 else None
    pool = common.load_pool()
    problems = common.load_problems_data()
    verdicts = load_markup(markup_path)

    toc = ''.join(
        '<a href="#%s">%s</a>' % (q['query_id'], html_mod.escape(q['query_id']))
        for q in pool['queries']
    )
    sections = []
    for q in pool['queries']:
        qid = q['query_id']
        sections.append('<a name="%s"></a>' % qid)
        sections.append(build_section_html(pool, problems, verdicts, qid))

    html = ''.join([
        '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<title>Выдачи 16 формул — просмотр результата</title>\n',
        '<style>', PAGE_CSS, '</style>\n</head>\n<body>\n<div id="wrap">\n',
        '<div id="toc"><b>Запросы:</b> ', toc, '</div>\n',
        ''.join(sections),
        '</div>\n</body>\n</html>\n',
    ])
    OUT_PATH.write_text(html, encoding='utf-8')
    marked_n = len(verdicts)
    print(f'Записано: {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} КБ), '
          f'известно вердиктов: {marked_n}'
          + ('' if markup_path else ' (демо без разметки — передайте JSON аргументом)'))


if __name__ == '__main__':
    main()
