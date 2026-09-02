u"""game_pool_report — диагностика игрового пула Econ Rush.

Печатает, что РЕАЛЬНО видит сервер прямо сейчас:
- сколько вопросов доступно на каждый режим — через ту же `_pool_qs()`,
  которой пользуется сама игра (см. game/views.py); отдельный подсчёт мимо
  неё мог бы соврать, если пул фильтруется не так, как думает диагностика;
- как Django видит оба флага выдачи — через `settings`, а не `os.environ`:
  процесс сервера мог получить флаг иначе, чем кажется из терминала (другая
  вкладка, другой профиль оболочки, значение не экспортировано);
- для режима «График» отдельно — сколько сюжетов зарегистрировано в
  `game/figures/registry.py` и генерируется ли хотя бы один экземпляр
  каждого без ошибки (`SampleError` — сюжет не собрал параметры за
  отведённые попытки).

Ничего не пишет в базу. Запуск:
  ./venv/bin/python manage.py game_pool_report
  GAME_FIGURE_ENABLED=1 ./venv/bin/python manage.py game_pool_report
"""
import random

from django.conf import settings
from django.core.management.base import BaseCommand

from game import config
from game.figures import base as fbase
from game.figures.registry import SCENARIOS, SCENARIO_ORDER
from game.views import _pool_qs


class Command(BaseCommand):
    help = (u'Диагностика игрового пула: сколько вопросов доступно на '
            u'режим, состояние флагов выдачи, генерация сюжетов «Графика».')

    def handle(self, *args, **options):
        self.stdout.write(u'=== Флаги выдачи (как их видит Django settings) ===')
        figure_flag = getattr(settings, 'GAME_FIGURE_ENABLED', False)
        generated_flag = getattr(settings, 'GAME_GENERATED_ENABLED', False)
        self.stdout.write(u'  GAME_FIGURE_ENABLED     = %r' % figure_flag)
        self.stdout.write(u'  GAME_GENERATED_ENABLED  = %r' % generated_flag)
        self.stdout.write('')

        self.stdout.write(u'=== Доступно вопросов на режим (пул целиком, без фильтров забега) ===')
        qs = _pool_qs()
        type_counts = {}
        for qtype in qs.values_list('question_type', flat=True):
            type_counts[qtype] = type_counts.get(qtype, 0) + 1
        for key, m in config.MODES.items():
            n = type_counts.get(m['question_type'], 0)
            marker = '' if n else '  <-- ПУСТО, карточка режима не покажется'
            self.stdout.write(u'  %-8s %-10s тип=%-14s — %5d%s'
                              % (key, m['title'], m['question_type'], n, marker))
        self.stdout.write('')

        self.stdout.write(u'=== Режим «График» (game/figures/) ===')
        self.stdout.write(u'  Сюжетов в реестре: %d — %s'
                          % (len(SCENARIOS), ', '.join(SCENARIO_ORDER)))
        self.stdout.write(u'  Строк figure_audit в базе (is_generated=True): %d'
                          % qs.model.objects.filter(
                              question_type=fbase.QUESTION_TYPE,
                              is_generated=True).count())
        rng = random.Random(20260727)
        for key in SCENARIO_ORDER:
            sc = SCENARIOS[key]
            try:
                fbase.build_question(sc, rng, config.FIGURE_CLEAN_SHARE)
            except fbase.SampleError as e:
                self.stdout.write(self.style.ERROR(
                    u'  %-18s ОШИБКА генерации (SampleError): %s' % (key, e)))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    u'  %-18s ИСКЛЮЧЕНИЕ: %r' % (key, e)))
            else:
                self.stdout.write(u'  %-18s сгенерирован 1 экземпляр — ок' % key)
