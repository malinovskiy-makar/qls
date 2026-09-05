# -*- coding: utf-8 -*-
"""Слепое сравнение sol и GLM для владельца — сессия 03.09.2026.

Собирает `reports/enrich_pilot/sol_vs_glm_blind.html`: 40 задач, из них
ровно 10 с растровой картинкой. По каждой задаче — условие, картинка (если
есть) и ДВЕ колонки полей, подписанные «А» и «Б».

⚠️ КОЛОНКИ ОБЕЗЛИЧЕНЫ И ПЕРЕМЕШАНЫ СВОИМ ЖРЕБИЕМ У КАЖДОЙ ЗАДАЧИ. «А» на
задаче 1 и «А» на задаче 2 — не обязательно одна и та же модель, угадать по
позиции нельзя. В прошлый раз колонки были подписаны, и оценка оказалась
недостоверной — поэтому это не формальность.

Соответствие «задача → где какая модель» пишется ОТДЕЛЬНО в
`sol_vs_glm_key.json` и не печатается ни в отчёт, ни на экран. Открывать
его можно только после того, как владелец вынес суждение.
"""
import base64
import html
import json
import os
import random
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from problems.enrich import taxonomy  # noqa: E402
from problems.enrich.text import images_for_call1, problem_full_text  # noqa: E402
from problems.models import Problem  # noqa: E402

GLM_PARSED = Path(
    r'C:\Users\shipu\qls-models\reports\enrich_pilot\run300_parsed.jsonl')
SOL_PARSED = Path('reports/enrich_pilot/sol300_parsed.jsonl')
OUT_HTML = Path('reports/enrich_pilot/sol_vs_glm_blind.html')
OUT_KEY = Path('reports/enrich_pilot/sol_vs_glm_key.json')

TOTAL = 40
WITH_RASTER = 10
SEED = 20260903

CSS = """
body{font-family:-apple-system,'Segoe UI',sans-serif;font-size:14px;
     margin:24px auto;max-width:1400px;color:#1d1d1f;line-height:1.5}
h1{font-size:22px;margin-bottom:4px}
.howto{background:#fff6d5;border:1px solid #e2cf7a;padding:14px 16px;
       border-radius:6px;font-size:15px;margin:16px 0}
.meta{color:#6b6b70;font-size:12px}
table{border-collapse:collapse;width:100%;margin:10px 0 34px}
td,th{border:1px solid #d2d2d7;padding:10px;vertical-align:top;text-align:left}
th{background:#f4f4f6;font-size:13px}
.stmt{white-space:pre-wrap;font-size:13px;background:#fafafa;width:32%}
.col{width:34%}
.field{margin-bottom:7px}
.field b{color:#4b4b52;font-weight:600}
.empty{color:#9a9aa0}
h2{margin-top:34px;font-size:17px;border-top:2px solid #e5e5ea;padding-top:14px}
img.fig{max-width:100%;border:1px solid #e0e0e5;border-radius:4px;margin-top:8px}
.tagline{color:#6b6b70;font-size:12px;margin-top:-6px}
"""


def load(path):
    return {r['problem_id']: r
            for r in (json.loads(line) for line in
                      open(path, encoding='utf-8') if line.strip())}


def esc(value):
    return html.escape(str(value if value is not None else ''))


def theme_label(identifier):
    if not identifier:
        return ''
    try:
        return '%s — %s' % (identifier, taxonomy.theme_name_from_id(identifier))
    except KeyError:
        return str(identifier)


def tag_label(identifier):
    try:
        return '%s (%s)' % (taxonomy.tag_name_from_id(identifier), identifier)
    except KeyError:
        return str(identifier)


def field(name, value):
    """Одно поле колонки. Пустое показывается словом, а не исчезает: «модель
    промолчала» — это тоже результат, и он обязан быть виден рядом с чужим
    заполненным полем."""
    if value in (None, '', [], {}):
        body = '<span class="empty">— пусто</span>'
    elif isinstance(value, (list, tuple)):
        body = esc(', '.join(str(v) for v in value))
    else:
        body = esc(value)
    return '<div class="field"><b>%s:</b> %s</div>' % (esc(name), body)


def column_html(row):
    parts = [
        field('Тема', theme_label(row.get('topic_primary'))),
        field('Уверенность', row.get('topic_confidence')),
        field('Доп. темы', [theme_label(t) for t in (row.get('topics_secondary') or [])]),
        field('Теги', [tag_label(t) for t in (row.get('tags') or [])]),
        field('Дано', row.get('given')),
        field('Найти', row.get('find')),
        field('Понятия', row.get('econ_concepts')),
        field('Понятия вне словаря', row.get('concepts_offlist')),
        field('Характер', row.get('task_nature')),
        field('Признаки', row.get('features_1')),
        field('Графическое решение', row.get('graphical_solution')),
        field('Тип', row.get('problem_type')),
        field('Сложность', row.get('difficulty')),
        field('Почему такая сложность', row.get('difficulty_note')),
        field('Качество текста', row.get('text_quality')),
        field('Замечание к тексту', row.get('text_quality_note')),
        field('Ответ согласован', row.get('answer_consistency')),
        field('Заголовок', row.get('title_candidate')),
        field('Поисковые запросы', row.get('search_queries')),
        field('График к решению', row.get('plot')),
        field('Подсказки', row.get('hints')),
    ]
    return ''.join(parts)


def pick(ids, glm, sol, rng):
    """40 задач: ровно 10 с растровой картинкой, 30 без. Обе доли берутся
    жребием, чтобы выбор не зависел от порядка id."""
    raster = sorted(i for i in ids if glm[i].get('has_raster'))
    plain = sorted(i for i in ids if not glm[i].get('has_raster'))
    chosen = rng.sample(raster, min(WITH_RASTER, len(raster)))
    chosen += rng.sample(plain, min(TOTAL - len(chosen), len(plain)))
    rng.shuffle(chosen)
    return chosen


def main():
    glm, sol = load(GLM_PARSED), load(SOL_PARSED)
    ids = sorted(set(glm) & set(sol))
    rng = random.Random(SEED)
    chosen = pick(ids, glm, sol, rng)

    problems = {p.id: p for p in Problem.objects.filter(id__in=chosen)
                .prefetch_related('parts', 'figures')}

    out = ['<!doctype html>', '<html lang="ru"><head><meta charset="utf-8">',
           '<title>Слепое сравнение двух моделей — 40 задач</title>',
           '<style>%s</style></head><body>' % CSS,
           '<h1>Слепое сравнение: две модели на одних и тех же задачах</h1>',
           '<p class="howto">По каждой задаче отметьте, какая колонка '
           'разобрала задачу лучше — <b>А</b>, <b>Б</b> или «одинаково». '
           'Смотрите на смысл: та ли тема, те ли теги, не выдумано ли '
           '«Дано», годится ли заголовок, осмысленны ли поисковые запросы.</p>',
           '<p class="meta">Задач: %d, из них с растровой картинкой: %d. '
           'Колонки обезличены, и жребий свой у каждой задачи — «А» на '
           'разных задачах это разные модели, угадать по позиции нельзя. '
           'Соответствие лежит отдельным файлом и до конца разметки не '
           'открывается. Обе модели получили побайтно одинаковый промпт и '
           'одинаковые шорт-листы понятий. База не менялась.</p>' % (
               len(chosen), sum(1 for i in chosen if glm[i].get('has_raster')))]

    key = {}
    for order, pid in enumerate(chosen, 1):
        problem = problems.get(pid)
        if problem is None:
            continue
        # ⚠️ Жребий на КАЖДУЮ задачу отдельно — иначе «А» везде одна и та
        # же модель, и слепота держится ровно до второй задачи.
        first = rng.choice(('glm', 'sol'))
        second = 'sol' if first == 'glm' else 'glm'
        key[str(pid)] = {'А': first, 'Б': second, 'order': order}
        rows = {'glm': glm[pid], 'sol': sol[pid]}

        statement = problem_full_text(problem.statement, problem.parts.all())
        figures = images_for_call1(problem.figures.all())
        images = ''
        for content_type, data in figures:
            images += ('<img class="fig" src="data:%s;base64,%s" alt="чертёж">'
                       % (content_type,
                          base64.b64encode(bytes(data)).decode('ascii')))

        out.append('<h2>Задача %d из %d &nbsp;<span class="meta">'
                   'id %d</span></h2>' % (order, len(chosen), pid))
        out.append('<table><tr><th>Условие</th><th>Колонка А</th>'
                   '<th>Колонка Б</th></tr><tr>')
        out.append('<td class="stmt">%s%s</td>' % (esc(statement), images))
        out.append('<td class="col">%s</td>' % column_html(rows[first]))
        out.append('<td class="col">%s</td>' % column_html(rows[second]))
        out.append('</tr></table>')

    out.append('</body></html>')
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text('\n'.join(out), encoding='utf-8')
    OUT_KEY.write_text(json.dumps(key, ensure_ascii=False, indent=2),
                       encoding='utf-8')

    # ⚠️ Печатается ТОЛЬКО факт записи. Ни одной строки самого ключа —
    # ни в лог, ни в отчёт: увиденное однажды соответствие уже не
    # «слепое».
    print('слепое сравнение: %s (%d задач, из них с картинкой %d)'
          % (OUT_HTML, len(key),
             sum(1 for i in chosen if glm[i].get('has_raster'))))
    print('ключ записан отдельно: %s — НЕ ОТКРЫВАТЬ до вынесения суждения'
          % OUT_KEY)


if __name__ == '__main__':
    main()
