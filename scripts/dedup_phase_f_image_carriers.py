# -*- coding: utf-8 -*-
"""ФАЗА 0 пишущей сессии — где ещё, кроме `ProblemFigure`, живут картинки.

Зачем. Правило картинки из фазы B («двойник с картинкой против approved без
картинки — в ручную очередь») опирается на ОДИН носитель — `ProblemFigure`.
Прошлая сессия замерила: `FileAsset` и связь `files` пусты, а среди задач с
фигурой в условии approved-задач ноль. Отсюда открытый вопрос: у approved
картинок правда нет, или носитель другой и мы его просто не искали?

Здесь ищем вставку картинки ПРЯМО В ТЕКСТЕ: markdown-синтаксис, LaTeX
`\\includegraphics` и окружения рисунков, тег `<img>`, прямые ссылки на файлы
изображений, пути в `/media/`. Отдельно — словесные упоминания («на рисунке»),
они картинкой не являются, но показывают, сколько условий на картинку
ссылаются, не неся её.

Только чтение.
"""
import argparse
import io
import json
import re
import sqlite3
import sys
from collections import Counter

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                                  errors='replace')

#: Паттерны настоящих носителей картинки в тексте.
CARRIERS = {
    'markdown_img': r'!\[[^\]]*\]\([^)]*\)',
    'includegraphics': r'\\includegraphics',
    'html_img': r'<img\b',
    'url_image': r'https?://\S+\.(?:png|jpe?g|gif|svg|webp|bmp)',
    'media_path': r'/media/\S+',
    'latex_figure_env': r'\\begin\{(?:figure|tikzpicture|picture)\}',
    'latex_graphics_other': r'\\(?:graphicspath|epsfig|psfig|includesvg)',
}
#: Не носитель, а УПОМИНАНИЕ картинки — считаем отдельно и не смешиваем.
MENTIONS = {
    'словами про рисунок': r'(?:рис\.|рисунк|на рисунке|см\. график|'
                           r'на графике|изображен|по графику)',
}

FIGURE_STATEMENT_FIELDS = ('statement', 'import')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='db.sqlite3')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    con = sqlite3.connect('file:%s?mode=ro' % args.db.replace('\\', '/'),
                          uri=True)
    carriers = {k: re.compile(v, re.I) for k, v in CARRIERS.items()}
    mentions = {k: re.compile(v, re.I) for k, v in MENTIONS.items()}

    подпункты = {}
    for pid, txt in con.execute(
            "SELECT problem_id, COALESCE(statement,'') || ' ' || "
            "COALESCE(answer,'') FROM problems_problempart"):
        подпункты.setdefault(pid, []).append(txt)

    фигуры = {}
    for pid, всего in con.execute(
            "SELECT problem_id, COUNT(*) FROM problems_problemfigure "
            "WHERE source_field IN (%s) GROUP BY problem_id"
            % ','.join('?' * len(FIGURE_STATEMENT_FIELDS)),
            FIGURE_STATEMENT_FIELDS):
        фигуры[pid] = всего

    всего_счёт = Counter()
    approved_счёт = Counter()
    approved_без_фигуры = Counter()
    примеры = {}
    n_всего = n_approved = 0
    approved_с_фигурой = 0

    for pid, st, hr in con.execute(
            "SELECT id, COALESCE(statement,''), COALESCE(human_review,'') "
            "FROM problems_problem"):
        n_всего += 1
        одобрено = hr == 'approved'
        if одобрено:
            n_approved += 1
            if фигуры.get(pid):
                approved_с_фигурой += 1
        текст = st + ' ' + ' '.join(подпункты.get(pid, ()))
        for имя, rx in list(carriers.items()) + list(mentions.items()):
            if rx.search(текст):
                всего_счёт[имя] += 1
                if одобрено:
                    approved_счёт[имя] += 1
                    if not фигуры.get(pid):
                        approved_без_фигуры[имя] += 1
                        примеры.setdefault(имя, []).append(pid)
    con.close()

    отчёт = {
        'задач всего': n_всего,
        'approved всего': n_approved,
        'approved с ProblemFigure в условии': approved_с_фигурой,
        'носители': {
            имя: {
                'всего задач': всего_счёт[имя],
                'из них approved': approved_счёт[имя],
                'approved БЕЗ ProblemFigure': approved_без_фигуры[имя],
                'примеры id': sorted(примеры.get(имя, ()))[:10],
            } for имя in CARRIERS
        },
        'упоминания (НЕ носитель)': {
            имя: {
                'всего задач': всего_счёт[имя],
                'из них approved': approved_счёт[имя],
                'approved БЕЗ ProblemFigure': approved_без_фигуры[имя],
            } for имя in MENTIONS
        },
    }
    json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps(отчёт, ensure_ascii=False, indent=1))
    print('\nзаписано: %s' % args.out)


if __name__ == '__main__':
    main()
