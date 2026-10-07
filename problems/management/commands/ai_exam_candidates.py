# -*- coding: utf-8 -*-
"""ai_exam_candidates — разведка банка и отбор кандидатов экзамена для ИИ.

ТОЛЬКО ЧТЕНИЕ: в базу не пишет ни строки, к модели не обращается.
Всё, что получается, ложится ВНЕ репозитория (репозиторий публичный,
экзамен утечь не должен) — в `--dir`, по умолчанию
`<рядом с репозиторием>/weconomics-data/ai_exam/v0`.

    manage.py ai_exam_candidates --recon
        воронка двенадцати фильтров → RECON.md
    manage.py ai_exam_candidates --count 232 --chunks 4 --seed 20261007
        RECON.md, candidates.jsonl и review/chunk_<k>.html

candidates.jsonl без `--force` не перезаписывается: после раздачи страниц
проверяющим список меняться не должен. Правила отбора — docs/AI_EXAM.md.
"""
import hashlib
import io
import os
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.ai_exam import sampling
from problems.ai_exam.bank import bank_fingerprint, load_records, load_topics
from problems.ai_exam.page import build_page

DEFAULT_DIR = os.path.join(os.path.dirname(settings.BASE_DIR),
                           'weconomics-data', 'ai_exam', 'v0')


def recon_markdown(result, topics, seed=None):
    """RECON.md: воронка, ослабления, таблица пула. Только счётчики."""
    pool = result['pool']
    own = sampling.own_topics(pool, topics)
    lines = ['# Разведка банка для экзамена ИИ v0', '']
    lines.append('Основа — `catalog.filters.base_queryset(\'catalog\')`.')
    lines += ['', '## Воронка', '', '| # | Фильтр | Осталось |', '|---|---|---|']
    for i, (_key, label, left) in enumerate(result['funnel'], 1):
        lines.append('| %d | %s | %d |' % (i, label, left))
    lines += ['', '## Ослабления', '']
    lines += (['- ' + r for r in result['relaxed']] or ['- не понадобились'])
    lines += ['', '## Все попытки', '',
              'Правило: пул ≥ %d и тем с %d+ задачами ≥ %d; иначе следующее ослабление.'
              % (sampling.POOL_MIN, sampling.TOPIC_SIZE, sampling.TOPICS_MIN), '',
              '| Попытка | ' + ' | '.join(str(i) for i in range(1, 13))
              + ' | Тем 8+ | Тем 5+ |',
              '|---|' + '---|' * 14]
    for a in result['attempts']:
        name = 'строго' if not a['relaxed'] else '+' + ','.join(
            r.split(':')[0] for r in a['relaxed'])
        lines.append('| %s | %s | %d | %d |' % (
            name, ' | '.join(str(n) for _k, _l, n in a['funnel']),
            a['topics_8'], a['topics_5']))
    if result['stop']:
        lines += ['', '**СТОП: после всех трёх ослаблений пул меньше %d или тем с '
                  '%d+ задачами меньше %d — решает владелец.**'
                  % (sampling.STOP_POOL, sampling.STOP_TOPIC_SIZE, sampling.STOP_TOPICS)]

    lines += ['', '## Пул: своя тема × уровень', '',
              '| Тема | Блок | ' + ' | '.join(sampling.LEVELS) + ' | Всего |',
              '|---|---|' + '---|' * (len(sampling.LEVELS) + 1)]
    table = Counter((own[r['id']], sampling.level_of(r['difficulty'])) for r in pool)
    total = 0
    for t in sorted(topics, key=lambda t: (topics[t]['order'], t)):
        row = [table[(t, level)] for level in sampling.LEVELS]
        total += sum(row)
        lines.append('| %s | %s | %s | %d |' % (
            topics[t]['name'], sampling.section_of(topics[t]['name']),
            ' | '.join(str(n) for n in row), sum(row)))
    lines.append('| **Итого** | | %s | **%d** |' % (
        ' | '.join(str(sum(table[(t, level)] for t in topics))
                   for level in sampling.LEVELS), total))

    kinds = Counter(r['key_kind'] for r in pool)
    lines += ['', '## Вид ключа', '']
    lines += ['- %s: %d' % (k, kinds.get(k, 0)) for k in ('exact', 'extracted', 'none')]
    lines += ['', '## По problem_type', '']
    lines += ['- %s: %d' % (k or '(пусто)', n)
              for k, n in Counter(r['problem_type'] for r in pool).most_common()]
    lines += ['', '## Десять крупнейших источников', '']
    lines += ['- %s: %d' % (k or '(без источника)', n)
              for k, n in Counter(r['source'] for r in pool).most_common(10)]
    return '\n'.join(lines) + '\n', total


def _write(path, data, binary=False):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if binary:
        with open(path, 'wb') as handle:
            handle.write(data)
    else:
        with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(data)


class Command(BaseCommand):
    help = 'Разведка банка и отбор кандидатов экзамена ИИ (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=DEFAULT_DIR,
                            help='папка экзамена (вне репозитория)')
        parser.add_argument('--recon', action='store_true',
                            help='только воронка и RECON.md')
        parser.add_argument('--count', type=int, default=232)
        parser.add_argument('--chunks', type=int, default=4)
        parser.add_argument('--seed', type=int, default=20261007)
        parser.add_argument('--force', action='store_true',
                            help='перезаписать существующий candidates.jsonl')

    def handle(self, *args, **options):
        directory = options['dir']
        count, chunks, seed = options['count'], options['chunks'], options['seed']
        if count < 1 or chunks < 1:
            raise CommandError('--count и --chunks должны быть положительными')
        target = os.path.join(directory, 'candidates.jsonl')
        if not options['recon'] and os.path.exists(target) and not options['force']:
            raise CommandError('%s уже есть: после раздачи страниц список меняться '
                               'не должен. Перезаписать — только с --force.' % target)

        before = bank_fingerprint()
        topics = load_topics()
        records = sampling.prepare(load_records())
        result = sampling.build_pool(records, topics)
        text, table_total = recon_markdown(result, topics)
        _write(os.path.join(directory, 'RECON.md'), text)

        self.stdout.write('Видимых задач: %d' % len(records))
        previous = len(records)
        for i, (_key, label, left) in enumerate(result['funnel'], 1):
            self.stdout.write('  %2d. %-70s %6d' % (i, label, left))
            if left > previous:
                raise CommandError('воронка выросла на шаге %d — ошибка отбора' % i)
            previous = left
        self.stdout.write('Ослабления: %s' % ('; '.join(result['relaxed']) or 'нет'))
        for a in result['attempts']:
            self.stdout.write('  попытка %-10s пул %4d, тем 8+: %2d, тем 5+: %2d; воронка %s' % (
                '+' + ','.join(r.split(':')[0] for r in a['relaxed']) if a['relaxed'] else 'строго',
                a['pool'], a['topics_8'], a['topics_5'],
                ' '.join(str(n) for _k, _l, n in a['funnel'])))
        pool = result['pool']
        counts = sampling.topic_counts(pool, topics)
        self.stdout.write('Пул: %d; тем с %d+ задачами: %d; с %d+: %d; сумма таблицы: %d'
                          % (len(pool), sampling.TOPIC_SIZE,
                             sum(1 for n in counts.values() if n >= sampling.TOPIC_SIZE),
                             sampling.STOP_TOPIC_SIZE,
                             sum(1 for n in counts.values() if n >= sampling.STOP_TOPIC_SIZE),
                             table_total))
        if table_total != len(pool):
            raise CommandError('сумма таблицы «тема × уровень» не равна пулу')
        self.stdout.write('RECON.md: %s' % os.path.join(directory, 'RECON.md'))
        if result['stop']:
            message = 'СТОП: пул мал даже после трёх ослаблений — решает владелец.'
            if options['recon']:
                self.stdout.write(self.style.ERROR(message))
                return
            raise CommandError(message)
        if options['recon']:
            self.stdout.write(self.style.SUCCESS('Разведка готова.'))
            return

        rows = sampling.select(pool, topics, count, chunks, seed)
        data = sampling.dump_jsonl(rows)
        again = sampling.dump_jsonl(sampling.select(pool, topics, count, chunks, seed))
        _write(target, data, binary=True)

        by_id = {r['id']: r for r in records}
        pages = []
        for chunk in range(1, chunks + 1):
            part = [r for r in rows if r['chunk'] == chunk]
            path = os.path.join(directory, 'review', 'chunk_%d.html' % chunk)
            _write(path, build_page(part, by_id, chunk, chunks, seed))
            pages.append((path, len(part), os.path.getsize(path)))

        after = bank_fingerprint()
        self._invariants(rows, by_id, count, len(pool), chunks, data, again,
                         before, after)
        for path, n, size in pages:
            self.stdout.write('  %s: %d карточек, %.1f КБ' % (path, n, size / 1024))
        self.stdout.write(self.style.SUCCESS('candidates.jsonl: %s' % target))

    def _invariants(self, rows, by_id, count, pool_size, chunks, data, again,
                    before, after):
        ids = [r['id'] for r in rows]
        groups = Counter(by_id[pk]['dup_group'] for pk in ids if by_id[pk]['dup_group'])
        sizes = Counter(r['chunk'] for r in rows)
        sizes = [sizes.get(c, 0) for c in range(1, chunks + 1)]
        sha = hashlib.sha256(data).hexdigest()
        checks = [
            ('кандидатов %d (нужно %d%s)' % (len(rows), count,
                                             ', пул %d' % pool_size if pool_size < count else ''),
             len(rows) == min(count, pool_size)),
            ('повторов id: %d' % (len(ids) - len(set(ids))), len(ids) == len(set(ids))),
            ('пар из одной группы копий: %d' % sum(n - 1 for n in groups.values()),
             all(n == 1 for n in groups.values())),
            ('размеры пачек: %s' % sizes, max(sizes) - min(sizes) <= 1),
            ('повтор с тем же seed: sha256 %s %s' % (
                sha[:16], '=' if again == data else '≠ ' + hashlib.sha256(again).hexdigest()[:16]),
             again == data),
            ('банк до/после: %s строк, updated_at %s / %s строк, %s'
             % (before[0], before[1], after[0], after[1]), before == after),
        ]
        self.stdout.write('Инварианты:')
        failed = False
        for label, ok in checks:
            self.stdout.write('  [%s] %s' % ('ok' if ok else 'НЕТ', label))
            failed = failed or not ok
        if failed:
            raise CommandError('нарушен инвариант отбора — файлы не годятся')
