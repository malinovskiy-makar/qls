u"""
game_economy_report — замер экономики очков v2 по живым забегам.

⚠️ ЭТО ПРИБОР, А НЕ ТЮНИНГ. Числа экономики правит человек и только по
замеру: правило проекта «пороги игры тюнить замером, а не на глаз». Пока
живых забегов десятки, крутить нечего — но мерить уже есть чем.

Ничего не меняет: только читает GameResult и статистику вопросов. Та же
сводка показывается на служебной странице /game/stats/ (вкладка
«Экономика»), и считает её ОДНА функция game/economy_report.py::report —
второй расчёт разошёлся бы с первым при первой правке.

Запуск:
    manage.py game_economy_report
    manage.py game_economy_report --min-attempts 5   # на маленькой выборке
"""
from django.core.management.base import BaseCommand

from game import config
from game.economy_report import report


class Command(BaseCommand):
    help = u'Сводка по экономике очков v2 (ничего не меняет).'

    def add_arguments(self, parser):
        parser.add_argument('--min-attempts', type=int, default=None,
                            help=u'порог попыток для долей верных')

    def handle(self, *args, **options):
        data = report(options['min_attempts'])
        w = self.stdout.write

        w(u'Забегов экономики v2: %d (незачётных %d)'
          % (data['total_runs'], data['unranked']))
        if not data['total_runs']:
            w(self.style.WARNING(
                u'Живых забегов v2 ещё нет — мерить нечего. Прибор готов.'))

        w('')
        w(u'ПО РЕЖИМАМ')
        w(u'  %-9s %5s %7s %7s %7s %6s %7s %7s %7s'
          % ('режим', 'заб.', 'p50', 'p90', 'макс', 'точн', '<1 мн.', 'множ.',
             'с/верн'))
        for m in data['by_mode']:
            w(u'  %-9s %5d %7s %7s %7s %5s%% %6s%% %6s%% %7s'
              % (m['title'], m['runs'],
                 _n(m['score_p50']), _n(m['score_p90']), _n(m['score_max']),
                 _n(m['accuracy_p50']), _n(m['penalized_share']),
                 _n(m['mult_gain']), _n(m['avg_correct_s'])))
        w(u'  «<1 мн.» — доля забегов, где точность СНИЗИЛА итог;')
        w(u'  «множ.» — насколько итог выше сырых очков;')
        w(u'  «с/верн» — медиана времени на верный ответ (секунды).')

        w('')
        w(u'ВРЕМЯ НА РАЗМЫШЛЕНИЕ: замер против константы THINK_S')
        for m in data['by_mode']:
            if m['avg_correct_s'] is None:
                continue
            w(u'  %-9s замер %5s с, в config %s с'
              % (m['title'], m['avg_correct_s'], m['think_s']))

        w('')
        w(u'ПРИЧИНЫ НЕЗАЧЁТНОСТИ')
        if not data['reasons']:
            w(u'  нет незачётных забегов')
        for r in data['reasons']:
            w(u'  %5d  %s' % (r['n'], r['text']))

        w('')
        w(u'ДОЛЯ ВЕРНЫХ ПО ЭФФЕКТИВНОЙ СЛОЖНОСТИ')
        for d in data['by_difficulty']:
            base = config.BASE_BY_DIFFICULTY.get(d['star'])
            w(u'  %d★  ответов %6d, верных %s%%   (BASE = %s)'
              % (d['star'], d['total'], _n(d['share']), base))
        five = next((d for d in data['by_difficulty'] if d['star'] == 5), None)
        if five and not five['total']:
            w(self.style.WARNING(
                u'  5★ по замеру ещё не появились: верхняя ступень шкалы '
                u'(BASE = %d) пока недостижима из банка.'
                % config.BASE_BY_DIFFICULTY[5]))

        w('')
        w(u'КАНДИДАТЫ НА ЧИСТКУ ПУЛА (от %d попыток)' % data['min_attempts'])
        w(u'  почти никто не решает (< %d %%):'
          % round(100 * config.STATS_BROKEN_BELOW))
        for r in data['hard']:
            w(u'    #%-6s %3s%%  %s' % (r['id'], r['share'], r['text'][:70]))
        if not data['hard']:
            w(u'    нет')
        w(u'  решают почти все (> %d %%):'
          % round(100 * config.STATS_TRIVIAL_ABOVE))
        for r in data['trivial']:
            w(u'    #%-6s %3s%%  %s' % (r['id'], r['share'], r['text'][:70]))
        if not data['trivial']:
            w(u'    нет')


def _n(value):
    return '–' if value is None else str(value)
