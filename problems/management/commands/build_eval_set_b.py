# -*- coding: utf-8 -*-
"""Набор B измерителя (С14) — обратная генерация запросов. СТОИТ ДЕНЕГ.

Модель читает настоящую задачу и пишет три фразы, которыми репетитор искал бы
такую. Правильный ответ известен заранее — это та самая задача.

⚠️⚠️ ЖЁСТКОЕ ПРАВИЛО НАБОРА B. Нарушать нельзя, и оно записано здесь, а не
только в голове у того, кто набор заказывал:

    По набору B РАЗРЕШЕНО утверждать «вариант Б лучше варианта А».
    По набору B ЗАПРЕЩЕНО утверждать «наш поиск даёт качество 0,85».

Синтетика систематически ЗАВЫШАЕТ абсолютные цифры: nDCG@10 примерно на 0,2
против человеческой разметки. Относительный порядок систем при этом
сохраняется (корреляция Кендалла 0,73–0,92), поэтому сравнивать между собой
варианты формулы — можно, называть абсолютное качество поиска — нет. Для
абсолютных цифр есть набор C: живые формулировки владельца.

⚠️ `--dry-run` ПО УМОЛЧАНИЮ, БОЕВОЙ ПРОГОН — ТОЛЬКО ПО `--apply`. Регламент
слоя команд (`problems/management/commands/CLAUDE.md`) требует этого от любой
массовой команды; здесь причина ещё прямее — команда тратит деньги. Случайный
запуск обязан ничего не сделать, а не потратить бюджет.

⚠️ ФОРМАТ СРАЗУ ОБУЧАЮЩИЙ. В файле лежат `query`, `relevant_ids` и
`hard_negative_ids: null`. Тот же материал понадобится для дообучения модели
(уровень 5 `EMBEDDINGS.md`), и платить за генерацию второй раз незачем.

Запуск:
    manage.py build_eval_set_b                  # смета, ничего не тратит
    manage.py build_eval_set_b --limit 1000 --apply
"""
import random

from django.core.management.base import BaseCommand, CommandError

from problems.ai import core
from problems.eval_sets import DATA_DIR, save_eval_set
from problems.models import Problem
from problems.search_eval_metrics import EvalCase

ПРОФИЛЬ = 'search_query_backgen'

СХЕМА = {
    'type': 'object',
    'properties': {
        'queries': {
            'type': 'array',
            'minItems': 3,
            'maxItems': 3,
            'items': {'type': 'string'},
        },
    },
    'required': ['queries'],
    'additionalProperties': False,
}

# Сколько символов условия отдаём модели. Больше не нужно: заход к задаче
# виден по первым абзацам, а каждый лишний символ — деньги на каждой из
# тысячи задач.
СИМВОЛОВ_УСЛОВИЯ = 1800

# Грубая смета: символов на токен для русского текста. Считаем с запасом.
СИМВОЛОВ_НА_ТОКЕН = 3.0
ТОКЕНОВ_ОТВЕТА = 120        # три короткие фразы плюс обвязка JSON


class Command(BaseCommand):
    help = ('Собрать эталонный набор B (обратная генерация запросов). '
            'ТРАТИТ ДЕНЬГИ: боевой прогон только с --apply.')

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=1000,
                            help='Сколько задач взять (по умолчанию 1000).')
        parser.add_argument('--seed', type=int, default=20260828,
                            help='Зерно выборки: тот же seed — та же выборка.')
        parser.add_argument(
            '--scope', default='all', choices=['prod', 'all'],
            help='Откуда брать задачи: all — весь банк с вектором '
                 '(по умолчанию), prod — только видимое на сайте.')
        parser.add_argument('--apply', action='store_true',
                            help='БОЕВОЙ прогон: обращается к модели и тратит '
                                 'деньги. Без него — только смета.')
        parser.add_argument('--out', default=str(DATA_DIR / 'eval_set_b.json'))

    def handle(self, *args, **options):
        from catalog.semantic import index_queryset

        задачи = self._выборка(index_queryset(options['scope']),
                               options['limit'], options['seed'])
        if not задачи:
            raise CommandError('В выборке нет ни одной задачи.')

        смета = self._смета(задачи)
        self._показать_смету(задачи, смета, options)

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                '\nЭто СМЕТА. Ничего не потрачено и не записано.\n'
                'Боевой прогон: добавьте --apply'))
            return

        self._прогон(задачи, options)

    # ── внутреннее ────────────────────────────────────────────────────

    def _выборка(self, qs, limit, seed):
        """Случайные задачи с фиксированным зерном, по всем источникам.

        Выборка детерминированная: тот же seed даёт тот же набор задач, иначе
        повторный прогон стоил бы денег и дал бы другой эталон — сравнивать
        замеры между собой стало бы нельзя.

        Отбираются задачи с осмысленным по длине условием: на огрызке в
        полсотни символов модель напишет три одинаковые общие фразы, и мы
        заплатим за мусор.
        """
        ids = list(qs.exclude(statement='')
                   .filter(statement__isnull=False)
                   .values_list('id', flat=True))
        rng = random.Random(seed)
        rng.shuffle(ids)
        отобранные = []
        for пачка_начало in range(0, len(ids), 2000):
            пачка = ids[пачка_начало:пачка_начало + 2000]
            строки = dict(Problem.objects.filter(pk__in=пачка)
                          .values_list('id', 'statement'))
            for pid in пачка:
                текст = (строки.get(pid) or '').strip()
                if len(текст) < 200:
                    continue
                отобранные.append((pid, текст[:СИМВОЛОВ_УСЛОВИЯ]))
                if len(отобранные) >= limit:
                    return отобранные
        return отобранные

    def _смета(self, задачи):
        from problems.ai.core import DEFAULT_MODEL, DEFAULT_PRICES
        from problems.ai.prompts import system_blocks

        системных = len(' '.join(system_blocks(ПРОФИЛЬ)))
        символов = sum(len(т) for _, т in задачи) + системных * len(задачи)
        вход = символов / СИМВОЛОВ_НА_ТОКЕН
        выход = ТОКЕНОВ_ОТВЕТА * len(задачи)
        цена_вход, цена_выход = DEFAULT_PRICES.get(DEFAULT_MODEL, (1.0, 5.0))
        return {
            'модель': DEFAULT_MODEL,
            'вход_токенов': int(вход),
            'выход_токенов': int(выход),
            'доллары': вход / 1e6 * цена_вход + выход / 1e6 * цена_выход,
        }

    def _показать_смету(self, задачи, смета, options):
        self.stdout.write('')
        self.stdout.write('── СМЕТА НАБОРА B ──')
        self.stdout.write(f'  Задач в выборке:      {len(задачи)}')
        self.stdout.write(f'  Запросов на выходе:   {len(задачи) * 3} '
                          f'(по 3 на задачу)')
        self.stdout.write(f'  Модель:               {смета["модель"]}')
        self.stdout.write(f'  Срез выборки:         {options["scope"]}')
        self.stdout.write(f'  Зерно (повторяемость): {options["seed"]}')
        self.stdout.write(f'  Токенов входа  ~      {смета["вход_токенов"]:,}'
                          .replace(',', ' '))
        self.stdout.write(f'  Токенов выхода ~      {смета["выход_токенов"]:,}'
                          .replace(',', ' '))
        self.stdout.write(self.style.WARNING(
            f'  ОЦЕНКА СТОИМОСТИ:     ${смета["доллары"]:.2f}'))

    def _прогон(self, задачи, options):
        случаи, ошибок, потрачено = [], 0, 0.0
        for н, (pid, текст) in enumerate(задачи, start=1):
            try:
                # ⚠️ ЕДИНСТВЕННАЯ ДВЕРЬ НАРУЖУ — core.run. Прямого обращения к
                # anthropic здесь нет и быть не должно: кэш, суточные лимиты и
                # учёт расхода живут только там (problems/ai/CLAUDE.md).
                # Наружу уходит ТОЛЬКО текст задачи: полей профиля
                # пользователя в запросе нет ни одного.
                итог = core.run(ПРОФИЛЬ, текст, СХЕМА, user=None,
                                check_limit=False)
            except Exception as ошибка:
                ошибок += 1
                if ошибок <= 3:
                    self.stdout.write(self.style.ERROR(
                        f'  задача #{pid}: {ошибка}'))
                if ошибок >= 20 and ошибок >= н // 2:
                    raise CommandError(
                        f'Слишком много ошибок ({ошибок} из {н}) — '
                        f'останавливаюсь, чтобы не жечь бюджет впустую.')
                continue

            потрачено += getattr(итог.usage, 'cost', 0.0) or 0.0
            for фраза in (итог.data or {}).get('queries', []):
                фраза = (фраза or '').strip()
                if фраза:
                    случаи.append(EvalCase(
                        query=фраза, relevant_ids={pid},
                        meta={'source_problem_id': pid}))
            if н % 50 == 0:
                self.stdout.write(f'  {н}/{len(задачи)} задач, '
                                  f'{len(случаи)} запросов, ошибок {ошибок}')

        путь = save_eval_set(
            options['out'], name='B',
            description='Обратная генерация: модель написала фразы, которыми '
                        'репетитор искал бы эту задачу. Набор СРАВНЕНИЯ '
                        'вариантов, не набор абсолютных цифр.',
            cases=случаи, mode='text',
            warnings=[
                'РАЗРЕШЕНО: «вариант Б лучше варианта А». ЗАПРЕЩЕНО: «поиск '
                'даёт качество 0,85». Синтетика завышает nDCG@10 примерно на '
                '0,2 против человеческой разметки; относительный порядок '
                'систем при этом сохраняется (Кендалл 0,73–0,92).',
                f'Выборка детерминирована: seed={options["seed"]}, '
                f'срез={options["scope"]}. Тот же seed даёт тот же набор.',
                f'Ошибок при генерации: {ошибок} из {len(задачи)} задач.',
            ])
        self.stdout.write(self.style.SUCCESS(
            f'\nГотово: {len(случаи)} запросов по {len(задачи) - ошибок} '
            f'задачам, ошибок {ошибок}.\nЗаписано: {путь}'))
