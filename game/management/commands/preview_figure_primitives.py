u"""preview_figure_primitives — витрина примитивов рисователя чертежей.

Одна страница со всеми примитивами в СВЕТЛОЙ и ТЁМНОЙ теме. Нужна затем же,
зачем нужен предпросмотр генераторов: «тесты зелёные» доказывают геометрию,
но не доказывают, что чертёж красив и читаем. Это решает глаз.

Страница инлайнит ТЕ ЖЕ `figure.js` и `figure.css`, что и боевая игра —
второго рисователя в проекте нет и не будет.

Запуск: ./venv/bin/python manage.py preview_figure_primitives
Выход:  reports/econ_rush_figure/primitives.html
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from game.generators._figure import (area, broken_line, callout, figure, line,
                                     mark, point, rect_area)

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'econ_rush_figure')
STATIC = os.path.join(settings.BASE_DIR, 'game', 'static', 'game')


def demos():
    u"""Шесть примитивов, каждый — своим чертежом, чтобы было видно именно его."""
    out = []

    # 1. point — точка с координатной подписью в тесном соседстве
    out.append((u'1. point — точка с подписью «E₀ (40; 60)»',
                u'Подпись отодвигается в свободную сторону: рисователь считает, '
                u'где меньше занятого, и ставит её туда. Точки нарочно посажены '
                u'близко.',
                figure('точки', 100, 120, 'Q, шт.', 'P, руб.',
                       lines=[line('d', 'D', (0, 100), (100, 0)),
                              line('s', 'S', (0, 40), (40, 120))],
                       points=[point(20, 80, 'E_0', 'd', coords=True),
                               point(26, 74, 'E_1', 's', coords=True),
                               point(50, 50, 'A', 'mr', coords=True)])))

    # 2. polygon — заштрихованная область с контуром
    out.append((u'2. polygon — заштрихованная область',
                u'Заливка заметно прозрачнее контура (0,25 против сплошной '
                u'линии): иначе область съедает кривые, которые под ней. '
                u'Слева — область с контуром, справа тот же треугольник без него.',
                figure('область', 100, 120, 'Q', 'P',
                       lines=[line('d', 'D', (0, 100), (100, 0)),
                              line('s', 'S', (0, 40), (40, 120))],
                       areas=[area('cs', [(0, 100), (0, 80), (20, 80)],
                                   outline=True),
                              area('ps', [(0, 40), (0, 80), (20, 80)])],
                       points=[point(20, 80, 'E', 'd', coords=True)])))

    # 3. rect_area — прямоугольник прибыли
    out.append((u'3. rect_area — прямоугольник области',
                u'Прибыль монополиста: (P − ATC) · Q. Углы можно задавать в '
                u'любом порядке — «бабочки» не получится.',
                figure('прибыль', 100, 120, 'Q', 'P',
                       lines=[line('d', 'D', (0, 100), (100, 0)),
                              line('mr', 'MR', (0, 100), (50, 0)),
                              line('mc', 'MC', (0, 20), (100, 20)),
                              line('atc', 'ATC', (10, 60), (100, 24))],
                       areas=[rect_area('zone', 0, 30, 40, 60)],
                       points=[point(40, 60, 'M', 'd', coords=True)],
                       marks=[mark('y', 60, 'P^*'), mark('y', 30, 'ATC'),
                              mark('x', 40, 'Q^*')])))

    # 4. callout — выноска с числом внутри и снаружи
    out.append((u'4. callout — выноска с числом',
                u'Слева число помещается внутрь области, справа — нет, и оно '
                u'выносится наружу с хвостиком. Решает рисователь: только он '
                u'знает ширину надписи в пикселях.',
                figure('выноски', 100, 100, 'Q', 'P',
                       areas=[rect_area('zone', 5, 40, 45, 90),
                              area('dwl', [(70, 40), (78, 40), (74, 48)],
                                   outline=True)],
                       callouts=[callout('1200', [(5, 40), (45, 40), (45, 90),
                                                  (5, 90)]),
                                 callout(u'потери общества = 150',
                                         [(70, 40), (78, 40), (74, 48)],
                                         role='dwl')])))

    # 5. mark — засечки с подписями значений
    out.append((u'5. tick — засечка на оси с подписью значения',
                u'Без засечек сюжет «монополия» не проверить глазом: игрок '
                u'обязан видеть, на какой высоте проходит ATC. При тесноте '
                u'подписи на оси Q опускаются на строку ниже, а на оси P '
                u'уходят вправо: строка ниже там — это соседняя цена.',
                figure('засечки', 100, 120, 'Q', 'P',
                       lines=[line('d', 'D', (0, 100), (100, 0)),
                              line('s', 'S', (0, 30), (100, 90))],
                       marks=[mark('y', 100, ''), mark('y', 65, 'P_b'),
                              mark('y', 60, 'P_0'), mark('y', 55, 'P_s'),
                              mark('x', 35, 'Q_1'), mark('x', 40, 'Q_0'),
                              mark('x', 80, '')])))

    # 6. broken_line — ломаная
    out.append((u'6. broken_line — ломаная (совместная КПВ)',
                u'Двумя отрезками это не собрать: в изломе они разошлись бы, '
                u'а подпись встала бы дважды.',
                figure('кпв', 120, 90, 'X, шт.', 'Y, шт.',
                       polylines=[broken_line('ppf', u'КПВ',
                                              [(0, 70), (60, 40), (100, 0)])],
                       areas=[area('feasible',
                                   [(0, 0), (0, 70), (60, 40), (100, 0)],
                                   outline=True)],
                       points=[point(60, 40, u'излом', 'd', coords=True)],
                       callouts=[callout(u'допустимо',
                                         [(0, 0), (0, 70), (60, 40), (100, 0)],
                                         role='feasible')])))
    return out


HTML = u"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Примитивы рисователя чертежей — Econ Rush</title>
<style>
  body {{ font: 15px/1.5 system-ui, -apple-system, 'Segoe UI', sans-serif;
         margin: 0; padding: 24px; background: #f4f5f7; color: #1f2430; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .lead {{ color: #5e6675; margin: 0 0 24px; max-width: 70ch; }}
  .demo {{ margin: 0 0 30px; }}
  .demo h2 {{ font-size: 16px; margin: 0 0 4px; }}
  .demo p {{ margin: 0 0 10px; color: #5e6675; max-width: 78ch; }}
  .pair {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .cell {{ flex: 1 1 420px; border-radius: 10px; padding: 10px;
           background: #fff; border: 1px solid #e2e5ea; }}
  .cell.dark {{ background: #0b0e14; border-color: #232a36; }}
  .cell b {{ display: block; font-size: 12px; color: #8a92a1;
             margin-bottom: 4px; font-weight: 600; }}
{css}
</style></head><body>
<h1>Примитивы рисователя чертежей</h1>
<p class="lead">Страница собрана командой <code>manage.py
preview_figure_primitives</code> и инлайнит те же <code>figure.js</code> и
<code>figure.css</code>, что и боевая игра. Каждый примитив показан в светлой
и тёмной теме: цвета кривых зафиксированы в обеих, по теме меняются только
оси, подписи и фон — поэтому чертёж перекрашивается сам.</p>
{body}
<script>{js}</script>
<script>
var DEMOS = {data};
DEMOS.forEach(function (d, i) {{
  ['light', 'dark'].forEach(function (theme) {{
    var host = document.getElementById('fig-' + i + '-' + theme);
    var node = window.drawFigure(d);
    if (node) host.appendChild(node);
  }});
}});
</script>
</body></html>
"""


class Command(BaseCommand):
    help = u'Витрина примитивов рисователя чертежей (HTML).'

    def handle(self, *args, **options):
        css = open(os.path.join(STATIC, 'figure.css'), encoding='utf-8').read()
        js = open(os.path.join(STATIC, 'figure.js'), encoding='utf-8').read()

        blocks, figs = [], []
        for i, (title, note, fig) in enumerate(demos()):
            figs.append(fig)
            blocks.append(
                u'<div class="demo"><h2>{t}</h2><p>{n}</p><div class="pair">'
                u'<div class="cell"><b>светлая тема</b>'
                u'<div id="fig-{i}-light"></div></div>'
                u'<div class="cell dark" data-theme="dark"><b>тёмная тема</b>'
                u'<div id="fig-{i}-dark"></div></div>'
                u'</div></div>'.format(t=title, n=note, i=i))

        html = HTML.format(css=css, js=js, body=u'\n'.join(blocks),
                           data=json.dumps(figs, ensure_ascii=False))
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, 'primitives.html')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(html)
        self.stdout.write(self.style.SUCCESS(
            u'Витрина примитивов: {} ({} чертежей × 2 темы)'.format(
                path, len(figs))))
