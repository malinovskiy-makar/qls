"""
generate_game_questions — боевая генерация вопросов из архетипов
(game/generators/) в кэш GameQuestion.

Без --confirm — dry-run: полная генерация в память со сводкой, БЕЗ записи.
С --confirm — запись; прежние записи тех же generator_key сперва удаляются
(повторный запуск идемпотентен по ключу генератора).

Контент-таблицы (Problem/ProblemPart) не затрагиваются вообще; вопросы
из тестов (is_generated=False) не затрагиваются тоже.

Запуск: ./venv/bin/python manage.py generate_game_questions \
            --per-archetype 100 [--confirm] [--seed 20260714] [--only key,key]
"""
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.management.commands.apply_topic_mapping import CANONICAL
from game.models import GameQuestion
from game.generators.base import generate_batch
from game.generators.registry import ARCHETYPES

QUESTION_TYPES = ('numeric', 'single', 'boolean')
DEFAULT_SEED = 20260714


class Command(BaseCommand):
    help = ('Генерирует вопросы из параметрических архетипов в кэш '
            'GameQuestion (dry-run без --confirm).')

    def add_arguments(self, parser):
        parser.add_argument('--per-archetype', type=int, default=100,
                            help='Вопросов КАЖДОГО типа на архетип')
        parser.add_argument('--confirm', action='store_true',
                            help='Записать в базу (иначе dry-run)')
        parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                            help='Зерно генератора случайных чисел')
        parser.add_argument('--only', default='',
                            help='Список ключей архетипов через запятую')

    def handle(self, *args, **options):
        per = options['per_archetype']
        seed = options['seed']
        only = [k.strip() for k in options['only'].split(',') if k.strip()]
        keys = only or list(ARCHETYPES)
        unknown = [k for k in keys if k not in ARCHETYPES]
        if unknown:
            raise CommandError('Неизвестные архетипы: {}'.format(unknown))

        canonical_set = set(CANONICAL)
        rng = random.Random(seed)
        rows = []
        summary = []
        for key in keys:
            arch = ARCHETYPES[key]
            bad_topics = [t for t in arch.topics if t not in canonical_set]
            if bad_topics:
                raise CommandError(
                    '{}: неканонические темы {}'.format(key, bad_topics))
            counts = {}
            for qtype in QUESTION_TYPES:
                batch = generate_batch(arch, rng, qtype, per)
                counts[qtype] = len(batch)
                for q in batch:
                    rows.append(GameQuestion(
                        problem=None,
                        part=None,
                        question_type=q['question_type'],
                        question=q['statement'],
                        options=q['options'],
                        correct_index=q['correct_index'],
                        correct_indices=None,
                        correct_value=q['correct_value'],
                        difficulty=q['difficulty'],
                        topics=q['topics'],
                        lang='ru',
                        stage='', year=None, grade='',
                        unit=q['unit'] if q['question_type'] == 'numeric' else '',
                        is_generated=True,
                        generator_key=q['generator_key'],
                        gen_params=q['params'],
                        gen_solution=q['solution_text'],
                    ))
            summary.append((key, counts))
            short = [c for c in counts.values() if c < per]
            mark = '' if not short else '  ⚠ меньше запрошенного'
            self.stdout.write('  {:<24} numeric {:>4} · single {:>4} · '
                              'boolean {:>4}{}'.format(
                                  key, counts['numeric'], counts['single'],
                                  counts['boolean'], mark))

        total = len(rows)
        self.stdout.write('Итого сгенерировано: {} вопросов '
                          '({} архетипов × 3 типа × ≤{})'.format(
                              total, len(keys), per))

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                'Dry-run: в базу НЕ записано. Добавьте --confirm.'))
            return

        with transaction.atomic():
            deleted, _ = GameQuestion.objects.filter(
                is_generated=True, generator_key__in=keys).delete()
            GameQuestion.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            'Записано {} (удалено прежних сгенерированных этих архетипов: '
            '{}).'.format(total, deleted)))

        by_type = {}
        for g in GameQuestion.objects.filter(lang='ru').values_list(
                'question_type', 'is_generated'):
            by_type[g] = by_type.get(g, 0) + 1
        self.stdout.write('Пул (ru) после записи:')
        for qtype in ('boolean', 'single', 'multi', 'numeric'):
            base = by_type.get((qtype, False), 0)
            gen = by_type.get((qtype, True), 0)
            self.stdout.write('  {:<8} {:>5} (тесты {} + сгенерированные {})'
                              .format(qtype, base + gen, base, gen))
