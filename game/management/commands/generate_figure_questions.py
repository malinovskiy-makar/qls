u"""generate_figure_questions — наполнить пул вопросами режима «График».

Вопрос аудита обязан быть строкой `GameQuestion`: выбор вопроса читает пул
плоским запросом, и генерировать на лету было бы негде.

⚠️ `is_generated=True` обязателен: `build_game_pool` сносит все строки с
is_generated=False, и без флага сюжеты умерли бы при первой же пересборке
пула. При этом выдача «Графика» управляется СВОИМ флагом
GAME_FIGURE_ENABLED (см. views._pool_qs).

Без --confirm — сухой прогон (ничего не пишет). Повторный запуск сначала
удаляет прежние вопросы тех же сюжетов: пул — кэш, дублировать его незачем.

Запуск:
  ./venv/bin/python manage.py generate_figure_questions --per-scenario 60 --confirm
"""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from game import config
from game.figures import base as fbase
from game.figures.registry import SCENARIOS, SCENARIO_ORDER
from game.models import GameQuestion


class Command(BaseCommand):
    help = u'Генерирует вопросы режима «График» (аудит чужого решения).'

    def add_arguments(self, parser):
        parser.add_argument('--per-scenario', type=int, default=60)
        parser.add_argument('--seed', type=int, default=20260727)
        parser.add_argument('--only', default='',
                            help=u'ключи сюжетов через запятую')
        parser.add_argument('--confirm', action='store_true',
                            help=u'без него — только сухой прогон')

    def handle(self, *args, **options):
        keys = [k.strip() for k in options['only'].split(',') if k.strip()] \
            or list(SCENARIO_ORDER)
        unknown = [k for k in keys if k not in SCENARIOS]
        if unknown:
            self.stderr.write(u'Неизвестные сюжеты: %s' % ', '.join(unknown))
            return

        rng = random.Random(options['seed'])
        per = options['per_scenario']
        rows, by_step = [], {}
        for key in keys:
            sc = SCENARIOS[key]
            made = 0
            # Уникальность — по (текст условия + показанный чертёж): два
            # экземпляра с одинаковыми параметрами и одинаковой ошибкой это
            # один и тот же вопрос.
            seen = set()
            for _ in range(per * 40):
                if made >= per:
                    break
                try:
                    q = fbase.build_question(sc, rng, config.FIGURE_CLEAN_SHARE)
                except fbase.SampleError:
                    break
                import json
                sig = (q['statement'],
                       json.dumps(q['figure'], sort_keys=True))
                if sig in seen:
                    continue
                seen.add(sig)
                rows.append(q)
                made += 1
                step = q['params']['_step']
                by_step[step] = by_step.get(step, 0) + 1
            self.stdout.write(u'  %-18s %d вопросов' % (key, made))

        total = len(rows)
        self.stdout.write(u'Всего собрано: %d' % total)
        for step in (fbase.STEP_POINTS, fbase.STEP_REGION, fbase.STEP_VALUE,
                     fbase.STEP_CLEAN):
            n = by_step.get(step, 0)
            self.stdout.write(u'  %-8s %4d (%.1f %%)'
                              % (step, n, 100.0 * n / total if total else 0))

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                u'Сухой прогон. Повторите с --confirm, чтобы записать.'))
            return

        with transaction.atomic():
            gone, _ = GameQuestion.objects.filter(
                question_type=fbase.QUESTION_TYPE,
                generator_key__in=keys).delete()
            GameQuestion.objects.bulk_create([
                GameQuestion(
                    problem=None, part=None,
                    question_type=fbase.QUESTION_TYPE,
                    question=q['statement'],
                    options=q['options'],
                    correct_index=q['correct_index'],
                    correct_value='',
                    difficulty=q['difficulty'],
                    topics=q['topics'],
                    lang='ru',
                    is_generated=True,          # иначе снесёт build_game_pool
                    generator_key=q['generator_key'],
                    gen_params=q['params'],
                    gen_solution=q['solution_text'],
                    figure=q['figure'],         # что видит игрок
                    figure_ref=q['figure_ref'],  # как правильно
                ) for q in rows], batch_size=200)
        self.stdout.write(self.style.SUCCESS(
            u'Удалено прежних: %d, записано: %d' % (gone, total)))
