# -*- coding: utf-8 -*-
"""Контактный лист снимков ревью 17.08 — одна страница на всю сессию.

    ./venv/bin/python scripts/r17_index.py

Кладёт `reports/review/index_r17.html`: снимки по фазам, в каждой строке
светлая тема, тёмная и 380 пикселей рядом. Смотреть глазами удобно, когда
три состояния одного экрана стоят в ряд, а не в трёх разных папках.
"""
import os
import re

FOLDER = os.path.join('reports', 'review')
OUT = os.path.join(FOLDER, 'index_r17.html')

PHASES = {
    'ф8': ('Фаза 8', 'Шаг 1 «Что кладём»: пять вкладок, чипы, корзина внизу'),
    'ф9': ('Фаза 9', 'Шаг 2 «Что нашлось» встроен в поток (лента шагов)'),
    'ф10': ('Фаза 10', 'Шаг 3 «Состав»: порядок, баллы, задача целиком'),
    'ф11': ('Фаза 11', 'Шаг 4 «Выдача»: настройки и лист, который уйдёт'),
    'ф12': ('Фаза 12', 'Вход в поток из занятия'),
    'ф13': ('Фаза 13', 'Экран «Написать свою»: поля пунктов и живое превью'),
    'ф14': ('Фаза 14', 'Печать с ответами: состав однородной работы'),
}

VIEWS = (('light', 'светлая'), ('dark', 'тёмная'), ('380', '380 px'))


def shots():
    """Снимки, сгруппированные по экрану: имя → {вид: файл}."""
    found = {}
    for name in sorted(os.listdir(FOLDER)):
        match = re.match(r'^р17-(.+)-(light|dark|380)\.png$', name)
        if not match:
            continue
        found.setdefault(match.group(1), {})[match.group(2)] = name
    return found


def main():
    groups = {}
    for screen, files in shots().items():
        phase = screen.split('-')[0]
        groups.setdefault(phase, []).append((screen, files))

    parts = ["""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Ревью 16.08 — снимки</title>
<style>
 body { font: 15px/1.6 system-ui, sans-serif; margin: 0; padding: 28px 32px;
        background: #f5f5f3; color: #1a1a1a; }
 h1 { font-size: 22px; margin: 0 0 4px; }
 .sub { color: #5b6472; margin-bottom: 26px; font-size: 14px; }
 h2 { font-size: 17px; margin: 30px 0 2px; }
 .why { color: #5b6472; font-size: 13px; margin-bottom: 14px; }
 .screen { background: #fff; border: 1px solid rgba(22,26,38,.12);
           border-radius: 12px; padding: 14px 16px; margin-bottom: 16px; }
 .name { font-weight: 600; font-size: 14px; margin-bottom: 10px; }
 .row { display: grid; grid-template-columns: 1fr 1fr 300px; gap: 12px;
        align-items: start; }
 figure { margin: 0; }
 figcaption { font-size: 12px; color: #687180; margin-bottom: 4px; }
 img { width: 100%; border: 1px solid rgba(22,26,38,.12); border-radius: 8px;
       display: block; background: #fff; }
 @media (max-width: 1000px) { .row { grid-template-columns: 1fr; } }
</style></head><body>
<h1>Ревью 16.08 — что смотреть глазами</h1>
<div class="sub">Каждый экран в трёх состояниях: светлая тема, тёмная и узкий
экран. Снимки сняты со сверкой кода ответа — страница ошибки в лист не
попадает.</div>"""]

    for phase in sorted(groups):
        title, why = PHASES.get(phase, (phase, ''))
        parts.append('<h2>%s</h2><div class="why">%s</div>' % (title, why))
        for screen, files in sorted(groups[phase]):
            parts.append('<div class="screen"><div class="name">%s</div>'
                         '<div class="row">' % screen)
            for key, caption in VIEWS:
                name = files.get(key)
                if not name:
                    continue
                parts.append(
                    '<figure><figcaption>%s</figcaption>'
                    '<a href="%s"><img src="%s" alt="%s, %s"></a></figure>'
                    % (caption, name, name, screen, caption))
            parts.append('</div></div>')

    parts.append('</body></html>')
    with open(OUT, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(parts))
    print('Готово: %s (экранов: %d)' % (OUT, len(shots())))


if __name__ == '__main__':
    main()
