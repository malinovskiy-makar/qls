# -*- coding: utf-8 -*-
u"""generated_audit: разбор сгенерированных вопросов пула по архетипам.

Ничего не меняет. Собирает reports/game/generated_audit.html: сводка по
архетипам с вердиктом и причиной, полный список вопросов, и отдельная
таблица найденных дефектов с числами.

⚠️ ГЛАВНОЕ, ЧТО НУЖНО ЗНАТЬ ПЕРЕД ЧТЕНИЕМ. Это НЕ вопросы, сочинённые
моделью. Это параметрические генераторы: ответ сэмплируется первым и
красивым, коэффициенты условия считаются обратным ходом, арифметика
точная (fractions.Fraction), дистракторы не выдумываются, а вычисляются
из типовых ошибок. Поэтому критерий «нейрослоп» к ним почти не применим,
и вердикты стоят по другим основаниям: единицы измерения, грамматика,
порядок вариантов, повторяемость сюжетов.

Запуск: manage.py generated_audit
"""
import collections
import html
import os
import re

from django.core.management.base import BaseCommand

from game.models import GameQuestion

KEEP = 'оставить'
FIX = 'доработать'
DROP = 'удалить'

# Вердикт по архетипу и причина в одну строку. Основание вердикта: ручная
# проверка математики (по два вопроса на архетип пересчитаны вручную),
# 56 зелёных тестов генераторов и замеры дефектов ниже.
VERDICTS = {
    'equilibrium': (FIX, 'математика верна, но у 45 вопросов условие в «ден. ед.», '
                         'а спрашивают «(в руб.)»'),
    'shift_equilibrium': (KEEP, 'сдвиг спроса и предложения посчитан верно, '
                                'дистракторы это исходное равновесие'),
    'tax_subsidy': (KEEP, 'распределение бремени и клин налога верны, '
                          'субсидия считается симметрично'),
    'price_control': (KEEP, 'короткая сторона рынка определена верно и для '
                            'потолка, и для пола'),
    'elasticity_point': (KEEP, 'точечная эластичность в равновесии верна, '
                               'единичная эластичность отличается от эластичной'),
    'elasticity_arc': (KEEP, 'дуговая эластичность по формуле середины, '
                             'проверка через выручку сходится'),
    'surplus': (KEEP, 'излишки считаются от цен отсечения, дистракторы это '
                      'CS и PS по отдельности, что и есть типовая ошибка'),
    'costs_tc': (KEEP, 'AVC, ATC и минимум ATC в точке ATC равно MC верны'),
    'comp_firm': (KEEP, 'оптимум по P равно MC, постоянные издержки его не двигают'),
    'monopoly': (KEEP, 'MR вдвое круче спроса, цена берётся со спроса, '
                       'эталон утверждён преподавателем'),
    'perfect_price_discrimination': (KEEP, 'прирост прибыли к простой монополии '
                                           'считается верно, не путается с самой прибылью'),
    'ppf_single': (FIX, 'КПВ и положение точки верны, но у 16 вопросов единица '
                        'ответа «ед. пшеницы» при условии в центнерах'),
    'ppf_joint': (KEEP, 'излом суммарной КПВ и максимумы по каждому товару верны'),
    'comparative_advantage': (FIX, 'сравнительное преимущество определено верно, '
                                   'но в 97 решениях падеж «по мёда» вместо «по мёду»'),
    'mpc_multiplier': (KEEP, 'мультипликатор госзакупок верен, '
                             'дистрактор это ошибка «умножить на MPC»'),
    'labor_minwage': (KEEP, 'занятость по короткой стороне при связывающем МРОТ верна'),
    'price_index': (KEEP, 'индекс цен и темп инфляции разведены, '
                          'это и есть классическая ловушка'),
    'figure_choice': (KEEP, 'выбор верного чертежа, ошибочные чертежи строятся '
                            'из вычисленных ошибок'),
    'cs_triangle': (KEEP, 'излишек потребителя как треугольник, аудит чужого решения'),
    'ceiling_dwl': (KEEP, 'потолок цены, дефицит и потери общества верны'),
    'tax_dwl': (KEEP, 'клин налога и распределение бремени верны'),
    'monopoly_profit': (KEEP, 'прибыль монополиста через ATC в оптимуме верна'),
    'ppf_joint_kink': (KEEP, 'излом совместной КПВ и площадь допустимого множества верны'),
    'unit_elasticity': (KEEP, 'середина линейного спроса как точка единичной '
                              'эластичности и максимума выручки'),
}

CSS = """
body{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;
     background:#f7f7f8;color:#1c1c1e}
main{max-width:1080px;margin:0 auto;padding:32px 24px 80px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:20px;margin:34px 0 10px}
h3{font-size:16px;margin:22px 0 8px;color:#3c3c43}
.lead{color:#5c5c62;margin:0 0 22px}
.note{background:#fff;border-left:3px solid #9a6700;padding:12px 15px;
      margin:0 0 20px}
table{border-collapse:collapse;width:100%;background:#fff;margin:10px 0 18px;
      box-shadow:0 1px 2px rgba(0,0,0,.07)}
th,td{padding:8px 11px;border-bottom:1px solid #e6e6ea;text-align:left;
      vertical-align:top;font-size:14px}
th{background:#efeff2;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.card{background:#fff;border:1px solid #e6e6ea;border-radius:7px;
      padding:9px 12px;margin:0 0 7px;font-size:13.5px}
.meta{font-size:12.5px;color:#5c5c62;margin:2px 0}
.keep{color:#1a7f37;font-weight:600}
.fix{color:#9a6700;font-weight:600}
.drop{color:#b3261e;font-weight:600}
code{background:#f0f0f3;padding:1px 5px;border-radius:4px;font-size:12.5px}
"""

VERDICT_CSS = {KEEP: 'keep', FIX: 'fix', DROP: 'drop'}


def esc(value):
    return html.escape(str(value if value is not None else ''))


def cut(value, limit=260):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text if len(text) <= limit else text[:limit] + '…'


class Command(BaseCommand):
    help = 'Отчёт по сгенерированным вопросам пула. Ничего не меняет.'

    def add_arguments(self, parser):
        parser.add_argument('--out', type=str,
                            default=os.path.join('reports', 'game',
                                                 'generated_audit.html'))

    def measure(self, questions):
        u"""Дефекты, найденные замером, а не на глаз."""
        units = [q for q in questions
                 if 'ден. ед.' in q.question and re.search(r'\(в руб\.\)', q.question)]
        centner = [q for q in questions
                   if (q.unit or '').startswith('ед. ') and 'центнер' in q.question]
        grammar = [q for q in questions
                   if re.search(r'\bпо (мёда|риса|стали|кофе|сахара|нефти|зерна|хлеба)\b',
                                q.gen_solution or '')]
        # Длинное тире записано escape-последовательностью намеренно:
        # сам символ в текстах сайта под запретом, и сканер
        # scripts/check_em_dash.py стережёт каталог game на нуле.
        dashes = [q for q in questions if u'\u2014' in q.question]
        return {
            'единица в условии и в вопросе разошлись': units,
            'единица ответа не та, что в тексте': centner,
            'падеж товара в решении': grammar,
            'длинное тире в тексте, который видит игрок': dashes,
        }

    def handle(self, *args, **options):
        questions = list(GameQuestion.objects.filter(is_generated=True)
                         .order_by('generator_key', 'id'))
        parts = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
                 '<title>Аудит сгенерированных вопросов</title>',
                 '<style>%s</style><main>' % CSS,
                 '<h1>Аудит сгенерированных вопросов Wecon Rush</h1>']
        add = parts.append

        add('<p class="lead">Всего сгенерированных вопросов: <b>%d</b> в '
            '<b>%d</b> архетипах. Отчёт ничего не меняет.</p>'
            % (len(questions), len(set(q.generator_key for q in questions))))

        add('<div class="note"><b>На проде сгенерированные вопросы выключены:</b> '
            '<code>GAME_GENERATED_ENABLED=False</code>. Всё, что ниже, живёт '
            'сейчас только в локальной базе.</div>')

        add('<div class="note"><b>Это не вопросы, сочинённые моделью.</b> '
            'Это параметрические генераторы: ответ сэмплируется первым и '
            'красивым, коэффициенты условия считаются обратным ходом, '
            'арифметика точная на <code>fractions.Fraction</code>, дистракторы '
            'не выдумываются, а вычисляются из типовых ошибок. Поэтому мерка '
            '«нейрослоп» к ним почти не прикладывается: сомнительной '
            'корректности не нашлось ни в одном архетипе, и вердикты стоят по '
            'другим основаниям.</div>')

        # ── Сводка по архетипам ──────────────────────────────────────────
        add('<h2>1. Сводка по архетипам</h2>')
        by_key = collections.defaultdict(list)
        for question in questions:
            by_key[question.generator_key].append(question)
        rows = []
        for key in sorted(by_key):
            verdict, why = VERDICTS.get(key, (FIX, 'вердикт не проставлен'))
            types = collections.Counter(q.question_type for q in by_key[key])
            rows.append([
                '<code>%s</code>' % esc(key), len(by_key[key]),
                esc(', '.join('%s %d' % (t, n) for t, n in sorted(types.items()))),
                '<span class="%s">%s</span>' % (VERDICT_CSS[verdict], esc(verdict)),
                esc(why)])
        add('<table><tr><th>Архетип</th><th class="num">Сколько</th>'
            '<th>Типы</th><th>Вердикт</th><th>Причина</th></tr>')
        for row in rows:
            add('<tr><td>%s</td><td class="num">%s</td><td>%s</td>'
                '<td>%s</td><td>%s</td></tr>' % tuple(row))
        add('</table>')

        counts = collections.Counter(
            VERDICTS.get(k, (FIX, ''))[0] for k in by_key)
        add('<p>Оставить: <b>%d</b> архетипов. Доработать: <b>%d</b>. '
            'Удалить: <b>%d</b>.</p>'
            % (counts[KEEP], counts[FIX], counts[DROP]))

        # ── Дефекты числом ───────────────────────────────────────────────
        add('<h2>2. Дефекты, найденные замером</h2>')
        found = self.measure(questions)
        add('<table><tr><th>Дефект</th><th class="num">Вопросов</th>'
            '<th>Архетипы</th></tr>')
        for name, group in found.items():
            keys = collections.Counter(q.generator_key for q in group)
            add('<tr><td>%s</td><td class="num">%d</td><td>%s</td></tr>'
                % (esc(name), len(group),
                   esc(', '.join('%s (%d)' % (k, n) for k, n in keys.most_common(6)))))
        add('</table>')
        for name, group in found.items():
            if not group:
                continue
            add('<h3>%s: примеры</h3>' % esc(name))
            for question in group[:5]:
                add('<div class="card">#%s <code>%s</code><br>%s</div>'
                    % (esc(question.id), esc(question.generator_key),
                       esc(cut(question.question))))

        # ── Полный список ────────────────────────────────────────────────
        add('<h2>3. Полный список вопросов</h2>')
        add('<p class="lead">Вердикт стоит на архетипе: у параметрического '
            'генератора все экземпляры отличаются только числами, и решение '
            'принимается о генераторе, а не о строке кэша.</p>')
        for key in sorted(by_key):
            verdict, why = VERDICTS.get(key, (FIX, 'вердикт не проставлен'))
            add('<h3><code>%s</code> (%d) '
                '<span class="%s">%s</span>: %s</h3>'
                % (esc(key), len(by_key[key]), VERDICT_CSS[verdict],
                   esc(verdict), esc(why)))
            for question in by_key[key]:
                bits = ['<div class="card"><b>#%s</b> [%s, %s звёзд] %s'
                        % (esc(question.id), esc(question.question_type),
                           esc(question.difficulty), esc(cut(question.question)))]
                if question.options and question.question_type != 'figure_choice':
                    bits.append('<p class="meta">Варианты: %s</p>'
                                % esc(' | '.join(str(o)[:70]
                                                 for o in question.options)))
                if question.correct_index is not None:
                    bits.append('<p class="meta">Верный: #%s</p>'
                                % esc(question.correct_index))
                if question.correct_value:
                    bits.append('<p class="meta">Ответ: <code>%s</code> %s</p>'
                                % (esc(question.correct_value), esc(question.unit)))
                if question.gen_solution:
                    bits.append('<p class="meta">Решение: %s</p>'
                                % esc(cut(question.gen_solution, 200)))
                bits.append('</div>')
                add(''.join(bits))

        # ── Выводы за пределами вердиктов по архетипам ───────────────────
        bank = GameQuestion.objects.filter(is_generated=False)
        five_bank = bank.filter(difficulty=5).count()
        five_gen = sum(1 for q in questions if q.difficulty == 5)
        wrappers = collections.Counter(q.generator_key for q in questions)
        add('<h2>4. Три вывода, которые важнее вердиктов</h2>')
        add('<div class="note"><b>Все вопросы на 5 звёзд сгенерированные.</b> '
            'В банке их <b>%d</b>, среди сгенерированных <b>%d</b>. Эвристика '
            'сложности для банка выдаёт максимум 4. Значит при выключенных '
            'сгенерированных вопросах верхняя ступень экономики очков v2 '
            '(BASE = 250 за 5 звёзд) недостижима в принципе, и шкала '
            'заканчивается на 170.</div>' % (five_bank, five_gen))
        add('<div class="note"><b>Повторяемость сюжетов.</b> На архетип '
            'приходится от %d до %d вопросов, а сюжетных обёрток у каждого '
            'единицы. За забег игрок видит десятки вопросов, поэтому один и '
            'тот же сюжет с другими числами будет узнаваться быстро. Это не '
            'дефект генератора, а предел формата: чинится числом обёрток, '
            'а не удалением архетипа.</div>'
            % (min(wrappers.values()), max(wrappers.values())))
        add('<div class="note"><b>Порядок вариантов у категориальных вопросов '
            'не тасуется.</b> В движке генераторов ветка '
            '<code>asked.kind == \'class\'</code> отдаёт варианты в объявленном '
            'порядке, без <code>rng.shuffle</code>: у числовых вопросов тасовка '
            'есть, у категориальных нет. Сегодня перекос мягкий (у '
            '3-вариантных 50 / 32 / 30, у 2-вариантных 26 / 27, у 4-вариантных '
            'перекос незначим), но он ничем не удерживается и зависит только '
            'от того, как часто верен тот или иной класс. Правится одной '
            'строкой и тестом.</div>')

        add('</main></html>')
        folder = os.path.dirname(options['out'])
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(options['out'], 'w', encoding='utf-8') as fh:
            fh.write(''.join(parts))
        self.stdout.write('Отчёт: %s' % options['out'])
        self.stdout.write('Архетипов: %d, вопросов: %d'
                          % (len(by_key), len(questions)))
        for name, group in found.items():
            self.stdout.write('  %-46s %d' % (name, len(group)))
