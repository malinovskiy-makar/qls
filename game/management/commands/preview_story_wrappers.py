u"""
preview_story_wrappers — превью сюжетных обёрток. НИЧЕГО НЕ ПИШЕТ.

Зачем. Аудит 2026-09-02 назвал повторяемость главным, что портит впечатление
от сгенерированных вопросов: 60-400 вопросов на архетип при ЕДИНИЦАХ сюжетных
обёрток. Чинится это числом обёрток, а не удалением архетипа.

Команда показывает, сколько обёрток у каждого архетипа сейчас и как читается
каждая: по три примера на обёртку, полная форма и сжатая. Числа и экономика
в примерах настоящие, сгенерированные тем же кодом, что и вопросы игры.

⚠️ Перегенерация пула — ОТДЕЛЬНЫЙ шаг и отдельное решение владельца:
`generate_game_questions --confirm`. Эта команда только рисует отчёт.

Запуск:
    manage.py preview_story_wrappers
    manage.py preview_story_wrappers --only price_index,ppf_joint
"""
import io
import os
import random

from django.core.management.base import BaseCommand, CommandError

from game.generators import base as gbase
from game.generators.registry import ARCHETYPES

DEFAULT_OUT = os.path.join('reports', 'game', 'story_wrappers_preview.html')
CSS = """
body{font:15px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;margin:0 auto;
 max-width:1000px;padding:24px;color:#1c1c1c;background:#fbfbf9}
h1{font-size:24px;margin:0 0 6px}
h2{font-size:19px;margin:34px 0 4px;padding-top:14px;border-top:1px solid #e6e6e0}
h3{font-size:15px;margin:18px 0 6px;color:#555}
p.lead{color:#555;margin:0 0 18px}
table{border-collapse:collapse;width:100%;margin:10px 0}
td,th{border:1px solid #e0e0da;padding:7px 10px;font-size:14px;
 vertical-align:top}
th{background:#f3f3ee;text-align:left}
.num{text-align:right;white-space:nowrap}
.ex{background:#fff;border:1px solid #e6e6e0;border-radius:9px;
 padding:10px 13px;margin:0 0 8px}
.ex small{display:block;color:#888;font-size:12px;margin-bottom:4px}
.short{color:#666;font-size:13px;margin-top:6px}
.warn{background:#fff6e5}
"""


def esc(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;') \
        .replace('>', '&gt;')


class Command(BaseCommand):
    help = u'Превью сюжетных обёрток архетипов. Ничего не меняет.'

    def add_arguments(self, parser):
        parser.add_argument('--out', default=DEFAULT_OUT)
        parser.add_argument('--only', default='',
                            help=u'ключи архетипов через запятую')
        parser.add_argument('--examples', type=int, default=3,
                            help=u'примеров на обёртку')
        parser.add_argument('--seed', type=int, default=20260902)

    def handle(self, *args, **options):
        only = [k.strip() for k in options['only'].split(',') if k.strip()]
        keys = only or sorted(ARCHETYPES)
        unknown = [k for k in keys if k not in ARCHETYPES]
        if unknown:
            raise CommandError(u'неизвестные архетипы: %s' % unknown)

        rng = random.Random(options['seed'])
        parts = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
                 '<title>Сюжетные обёртки генераторов</title>',
                 '<style>%s</style><main>' % CSS,
                 u'<h1>Сюжетные обёртки генераторов</h1>',
                 u'<p class="lead">Ничего не записано: это превью. Числа и '
                 u'экономика в примерах настоящие, их считает тот же код, '
                 u'что и вопросы игры. Меняется только рассказ вокруг '
                 u'них.</p>']

        # Сводка: у кого сколько обёрток.
        rows = []
        for key in keys:
            arch = ARCHETYPES[key]
            rows.append((key, len(arch.wrappers())))
        rows.sort(key=lambda r: (r[1], r[0]))
        parts.append(u'<h2>Сколько обёрток у архетипа</h2><table>'
                     u'<tr><th>архетип</th><th class="num">обёрток</th></tr>')
        for key, n in rows:
            cls = ' class="warn"' if n < 3 else ''
            parts.append(u'<tr%s><td>%s</td><td class="num">%d</td></tr>'
                         % (cls, esc(key), n))
        parts.append(u'</table><p class="lead">Жёлтым помечены архетипы, '
                     u'у которых обёрток меньше трёх: сюжет там узнаётся '
                     u'с третьего вопроса.</p>')

        made = 0
        for key in keys:
            arch = ARCHETYPES[key]
            wrappers = arch.wrappers()
            parts.append(u'<h2>%s <span class="num">(%s, обёрток %d)</span>'
                         u'</h2>' % (esc(arch.title), esc(key),
                                     len(wrappers)))
            for wrapper in wrappers:
                parts.append(u'<h3>Обёртка «%s»</h3>' % esc(wrapper.key))
                shown = 0
                for _ in range(options['examples'] * 40):
                    if shown >= options['examples']:
                        break
                    params = arch.sample(rng)
                    solved = arch.solve(params)
                    try:
                        full = wrapper.full(params, solved)
                        short = wrapper.short(params, solved)
                    except (KeyError, TypeError, ValueError, ZeroDivisionError):
                        continue
                    parts.append(
                        u'<div class="ex"><small>полная форма, %d знаков'
                        u'</small>%s<div class="short">сжатая, %d знаков: %s'
                        u'</div></div>'
                        % (len(full), esc(full), len(short), esc(short)))
                    shown += 1
                    made += 1
        parts.append(u'</main></html>')

        out = options['out']
        os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
        with io.open(out, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(parts))
        self.stdout.write(u'Архетипов: %d, примеров: %d' % (len(keys), made))
        self.stdout.write(self.style.SUCCESS(u'Превью: %s' % out))
        self.stdout.write(self.style.WARNING(
            u'Ничего не записано. Перегенерация пула — отдельное решение: '
            u'generate_game_questions --confirm.'))
