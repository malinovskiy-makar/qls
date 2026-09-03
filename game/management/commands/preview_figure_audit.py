u"""preview_figure_audit — предпросмотр сюжетов режима «График».

Главный артефакт приёмки: все сюжеты × все виды внедрённой ошибки, по
нескольку примеров на комбинацию. У каждой карточки — сам чертёж (то, что
увидит игрок), рядом эталонный (то, как правильно), подпись «внедрена
ошибка» и «верный ответ».

В базу НЕ пишет: генерирует свежие примеры на лету. Инлайнит те же
figure.js/figure.css, что и боевая игра, — второго рисователя нет.

Запуск:  ./venv/bin/python manage.py preview_figure_audit --per 4
Выход:   reports/econ_rush_figure/preview.html
"""
import json
import os
import random
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand

from game import config
from game.figures import base as fbase
from game.figures.registry import SCENARIOS, SCENARIO_ORDER

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'econ_rush_figure')
STATIC = os.path.join(settings.BASE_DIR, 'game', 'static', 'game')

PAGE = u"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Сюжеты режима «График» — предпросмотр</title>
<style>
  body {{ font: 15px/1.55 system-ui, -apple-system, 'Segoe UI', sans-serif;
         margin: 0; padding: 24px 28px 60px; background: #f4f5f7;
         color: #1f2430; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }}
  h2 {{ font-size: 19px; margin: 34px 0 2px; }}
  .sub {{ color: #5e6675; margin: 0 0 18px; max-width: 82ch; }}
  .toc {{ background: #fff; border: 1px solid #e2e5ea; border-radius: 10px;
          padding: 14px 18px; margin: 0 0 22px; }}
  .toc a {{ color: #BE185D; text-decoration: none; margin-right: 16px; }}
  table.sum {{ border-collapse: collapse; background: #fff; margin: 8px 0 6px;
               font-size: 14px; }}
  table.sum th, table.sum td {{ border: 1px solid #e2e5ea; padding: 5px 10px;
                                text-align: left; }}
  table.sum th {{ background: #f0f2f5; }}
  .card {{ background: #fff; border: 1px solid #e2e5ea; border-radius: 12px;
           padding: 14px 16px; margin: 14px 0; }}
  .stem {{ margin: 0 0 8px; }}
  .meta {{ font-size: 13px; color: #5e6675; margin: 0 0 10px; }}
  .badge {{ display: inline-block; font-size: 12px; font-weight: 700;
            padding: 2px 8px; border-radius: 999px; margin-right: 8px; }}
  .b-err {{ background: #fde7ef; color: #9d1246; }}
  .b-ok {{ background: #e3f3e9; color: #1d7e45; }}
  .pair {{ display: flex; gap: 14px; flex-wrap: wrap; }}
  .pane {{ flex: 1 1 430px; }}
  .pane b {{ display: block; font-size: 12px; color: #8a92a1;
             margin-bottom: 2px; }}
  .sol {{ font-size: 13px; color: #3d4453; margin-top: 8px;
          border-left: 3px solid #e2e5ea; padding-left: 10px; }}
{css}
</style></head><body>
<h1>Сюжеты режима «График» — аудит чужого решения</h1>
<p class="sub">Игроку показывают ЛЕВЫЙ чертёж и просят найти первый неверный
шаг. Правый чертёж — эталон, он нужен только для сверки глазами и в игре
показывается лишь в разборе ошибок. Страница собрана командой
<code>manage.py preview_figure_audit</code> и рисует теми же
<code>figure.js</code>/<code>figure.css</code>, что и боевая игра.</p>
{summary}
<div class="toc"><b>Сюжеты:</b> {toc}</div>
{body}
<script>{js}</script>
<script>
var DATA = {data};
DATA.forEach(function (d) {{
  ['shown', 'ref'].forEach(function (which) {{
    var host = document.getElementById(d.id + '-' + which);
    if (!host) return;
    var node = window.drawFigure(d[which]);
    if (node) host.appendChild(node);
  }});
}});
</script>
</body></html>
"""


class Command(BaseCommand):
    help = u'Предпросмотр сюжетов режима «График» (HTML).'

    def add_arguments(self, parser):
        parser.add_argument('--per', type=int, default=4,
                            help=u'сколько примеров на каждую комбинацию')
        parser.add_argument('--seed', type=int, default=20260726)
        parser.add_argument('--stats', type=int, default=2000,
                            help=u'сколько сэмплов для сводки распределения')

    def handle(self, *args, **options):
        per = options['per']
        rng = random.Random(options['seed'])
        css = open(os.path.join(STATIC, 'figure.css'), encoding='utf-8').read()
        js = open(os.path.join(STATIC, 'figure.js'), encoding='utf-8').read()

        blocks, data, toc = [], [], []
        for key in SCENARIO_ORDER:
            sc = SCENARIOS[key]
            toc.append(u'<a href="#s-%s">%s</a>' % (key, sc.title))
            blocks.append(
                u'<h2 id="s-%s">%s <small style="font-weight:400;color:#8a92a1">'
                u'· ключ <code>%s</code> · сложность %d · %s</small></h2>'
                % (key, sc.title, key, sc.difficulty, u', '.join(sc.topics)))
            variants = [None] + list(sc.injectors())
            for inj in variants:
                for n in range(per):
                    params = sc.sample(rng)
                    ref = sc.solve(params)
                    shown = sc.inject(params, inj, rng)
                    step = inj.step if inj else fbase.STEP_CLEAN
                    idx = fbase.ANSWER_INDEX[step]
                    cid = 'c%d' % len(data)
                    data.append({'id': cid,
                                 'shown': sc.draw(params, shown),
                                 'ref': sc.draw(params, ref)})
                    if inj:
                        badge = (u'<span class="badge b-err">внедрена ошибка: '
                                 u'%s</span>' % inj.title)
                    else:
                        badge = (u'<span class="badge b-ok">ошибки нет — '
                                 u'решение верное</span>')
                    blocks.append(
                        u'<div class="card"><p class="stem">%s</p>'
                        u'<p class="meta">%s верный ответ: <b>%s</b> '
                        u'(вариант %d)</p>'
                        u'<div class="pair">'
                        u'<div class="pane"><b>что видит игрок</b>'
                        u'<div id="%s-shown"></div></div>'
                        u'<div class="pane"><b>эталон (для сверки)</b>'
                        u'<div id="%s-ref"></div></div></div>'
                        u'<p class="sol">%s</p></div>'
                        % (sc.statement(params), badge,
                           fbase.ANSWER_OPTIONS[idx], idx + 1, cid, cid,
                           sc.explain(params, ref, inj)))

        summary = self._summary(options['stats'], options['seed'])
        html = PAGE.format(css=css, js=js, body=u'\n'.join(blocks),
                           toc=u' '.join(toc), summary=summary,
                           data=json.dumps(data, ensure_ascii=False))
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, 'preview.html')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(html)
        self.stdout.write(self.style.SUCCESS(
            u'Предпросмотр: {} ({} карточек, {} сюжетов)'.format(
                path, len(data), len(SCENARIOS))))

    def _summary(self, n, seed):
        u"""Сводка: доля целых чисел по сюжетам и фактическое распределение."""
        rng = random.Random(seed + 1)
        rows, answers = [], Counter()
        keys = list(SCENARIO_ORDER)
        for key in keys:
            sc = SCENARIOS[key]
            nice = 0
            per_scenario = max(200, n // max(len(keys), 1))
            for _ in range(per_scenario):
                params = sc.sample(rng)
                sol = sc.solve(params)
                ok = sol.value.denominator == 1 and all(
                    x.denominator == 1 and y.denominator == 1
                    for x, y in sol.points.values())
                nice += 1 if ok else 0
            rows.append((sc.title, per_scenario,
                         100.0 * nice / per_scenario, len(sc.injectors())))
        for i in range(n):
            sc = SCENARIOS[keys[i % len(keys)]]
            q = fbase.build_question(sc, rng, config.FIGURE_CLEAN_SHARE)
            answers[q['correct_index']] += 1

        head = (u'<table class="sum"><tr><th>сюжет</th><th>сэмплов</th>'
                u'<th>целых чисел</th><th>видов ошибки</th></tr>')
        body = u''.join(u'<tr><td>%s</td><td>%d</td><td>%.1f %%</td>'
                        u'<td>%d</td></tr>' % r for r in rows)
        dist = (u'<table class="sum"><tr><th>верный ответ</th>'
                u'<th>доля из %d</th></tr>' % n)
        dist += u''.join(
            u'<tr><td>%s</td><td>%.1f %%</td></tr>'
            % (fbase.ANSWER_OPTIONS[i], 100.0 * answers[i] / n)
            for i in range(4)) + u'</table>'
        return (u'<p class="sub"><b>Сводка.</b> Числа считаются свежими '
                u'сэмплами при каждой сборке страницы.</p>'
                + head + body + u'</table>' + dist)
