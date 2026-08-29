# -*- coding: utf-8 -*-
"""Числовые инварианты импорта (Фаза 3 брифа import-new-sources).

ТОЛЬКО ЧТЕНИЕ. Ничего не создаёт, не правит и не удаляет.

Импорт обязан быть чистой вставкой, и это утверждение проверяется, а не
декларируется. Снимок снимается ДО импорта (`--save-baseline`), сверка —
после (`--baseline`):

1. **Ни одна задача, существовавшая ДО, не изменилась.** Отпечаток —
   md5 от `statement`, `answer`, `solution`, `human_review`,
   `content_format`, `status`, `title`. Свип идёт по ВСЕМ старым id, а не
   по выборке.
2. **Ни один подпункт, существовавший ДО, не изменился** (`statement`,
   `answer`, `solution`).
3. **Ни одна старая задача не пропала.** Импорт не удаляет; исчезнувшая
   задача — отдельная беда, а не «0 изменённых».
4. **У каждой НОВОЙ задачи есть `Source`.** Задача без источника — брак
   импорта: непонятно, откуда она взялась и как её откатить.
5. Опционально: ожидаемое итоговое число задач (`--expect-total`) и
   ожидаемое число новых по каждому источнику (`--expect-new`).

⚠️ Свип идёт итератором и сравнивает по словарю, а НЕ через
`filter(id__in=[...])`: у SQLite потолок на число переменных в запросе
(63 250 подпунктов его уже пробивают — `too many SQL variables`).

Любое расхождение — `CommandError` с поимённым списком id, а не
предупреждение в конце вывода.
"""
import hashlib
import json

from django.core.management.base import BaseCommand, CommandError

from problems.models import (
    FileAsset, Problem, ProblemPart, Rubric, Source, SourceReference,
)

#: сколько id показывать в сообщении об ошибке, чтобы вывод остался читаемым
SHOW_IDS = 20


def problem_fingerprint(problem):
    raw = '\x1f'.join([
        problem.statement or '', problem.answer or '', problem.solution or '',
        problem.human_review or '', problem.content_format or '',
        problem.status or '', problem.title or '',
    ])
    return hashlib.md5(raw.encode('utf-8'), usedforsecurity=False).hexdigest()


def part_fingerprint(part):
    raw = '\x1f'.join([part.statement or '', part.answer or '', part.solution or ''])
    return hashlib.md5(raw.encode('utf-8'), usedforsecurity=False).hexdigest()


def counts():
    return {
        'Problem': Problem.objects.count(),
        'ProblemPart': ProblemPart.objects.count(),
        'Rubric': Rubric.objects.count(),
        'FileAsset': FileAsset.objects.count(),
        'Source': Source.objects.count(),
        'SourceReference': SourceReference.objects.count(),
    }


def snapshot():
    problems = {}
    for problem in Problem.objects.only(
        'id', 'statement', 'answer', 'solution', 'human_review',
        'content_format', 'status', 'title',
    ).iterator(chunk_size=2000):
        problems[str(problem.id)] = problem_fingerprint(problem)
    parts = {}
    for part in ProblemPart.objects.only(
        'id', 'statement', 'answer', 'solution',
    ).iterator(chunk_size=4000):
        parts[str(part.id)] = part_fingerprint(part)
    return {'counts': counts(), 'problems': problems, 'parts': parts}


def _parse_expect_new(values):
    expected = {}
    for item in values or []:
        if '=' not in item:
            raise CommandError(
                f'--expect-new ждёт «Название источника=число», получено: {item!r}')
        name, _, number = item.rpartition('=')
        try:
            expected[name] = int(number)
        except ValueError:
            raise CommandError(f'--expect-new: «{number}» не число (из {item!r})')
    return expected


class Command(BaseCommand):
    help = ('Проверить инварианты импорта по снимку, снятому до него. '
            'Только чтение.')

    def add_arguments(self, parser):
        parser.add_argument('--save-baseline',
                            help='снять снимок корпуса в указанный файл и выйти')
        parser.add_argument('--baseline',
                            help='файл снимка, снятого ДО импорта')
        parser.add_argument('--expect-total', type=int,
                            help='ожидаемое итоговое число задач')
        parser.add_argument('--expect-new', action='append', default=[],
                            help='ожидаемое число новых задач: «Источник=N» '
                                 '(можно повторять)')

    def handle(self, *args, **options):
        if options['save_baseline']:
            data = snapshot()
            with open(options['save_baseline'], 'w', encoding='utf-8') as f:
                json.dump(data, f)
            self.stdout.write(self.style.SUCCESS(
                f'Снимок: задач {len(data["problems"])}, подпунктов '
                f'{len(data["parts"])}, счётчики {data["counts"]} -> '
                f'{options["save_baseline"]}'))
            return

        if not options['baseline']:
            raise CommandError('нужен --baseline (или --save-baseline для снимка)')
        with open(options['baseline'], encoding='utf-8') as f:
            base = json.load(f)
        old_problems = base['problems']
        old_parts = base['parts']

        problems_changed = []
        problems_seen = set()
        new_ids = []
        for problem in Problem.objects.only(
            'id', 'statement', 'answer', 'solution', 'human_review',
            'content_format', 'status', 'title',
        ).iterator(chunk_size=2000):
            key = str(problem.id)
            expected = old_problems.get(key)
            if expected is None:
                new_ids.append(problem.id)
                continue
            problems_seen.add(key)
            if problem_fingerprint(problem) != expected:
                problems_changed.append(problem.id)

        parts_changed = []
        parts_seen = set()
        for part in ProblemPart.objects.only(
            'id', 'statement', 'answer', 'solution',
        ).iterator(chunk_size=4000):
            key = str(part.id)
            expected = old_parts.get(key)
            if expected is None:
                continue
            parts_seen.add(key)
            if part_fingerprint(part) != expected:
                parts_changed.append(part.id)

        vanished_problems = sorted(set(old_problems) - problems_seen, key=int)
        vanished_parts = sorted(set(old_parts) - parts_seen, key=int)

        with_source = set(
            SourceReference.objects.values_list('problem_id', flat=True))
        orphans = [pid for pid in new_ids if pid not in with_source]

        # Разбивка новых задач по источникам. Считается перебором, а не
        # `filter(problem_id__in=new_ids)`: новых задач тут почти десять
        # тысяч, и SQLite упал бы на «too many SQL variables».
        new_id_set = set(new_ids)
        new_by_source = {}
        for problem_id, name in SourceReference.objects.values_list(
                'problem_id', 'source__name').iterator(chunk_size=4000):
            if problem_id in new_id_set:
                new_by_source[name] = new_by_source.get(name, 0) + 1

        problems = []
        if problems_changed:
            problems.append(
                f'изменено старых задач: {len(problems_changed)} — '
                f'id {problems_changed[:SHOW_IDS]}')
        if parts_changed:
            problems.append(
                f'изменено старых подпунктов: {len(parts_changed)} — '
                f'id {parts_changed[:SHOW_IDS]}')
        if vanished_problems:
            problems.append(
                f'пропало старых задач: {len(vanished_problems)} — '
                f'id {vanished_problems[:SHOW_IDS]}')
        if vanished_parts:
            problems.append(
                f'пропало старых подпунктов: {len(vanished_parts)} — '
                f'id {vanished_parts[:SHOW_IDS]}')
        if orphans:
            problems.append(
                f'новых без Source: {len(orphans)} — id {orphans[:SHOW_IDS]}')

        total = Problem.objects.count()
        if options['expect_total'] is not None and total != options['expect_total']:
            problems.append(
                f'ожидалось задач {options["expect_total"]}, в базе {total}')

        for name, number in _parse_expect_new(options['expect_new']).items():
            actual = new_by_source.get(name, 0)
            if actual != number:
                problems.append(
                    f'источник «{name}»: ожидалось новых {number}, найдено {actual}')

        lines = [
            'Инварианты импорта (только чтение)',
            f'  снимок: {options["baseline"]}',
            f'  старых задач в снимке: {len(old_problems)}, сверено: {len(problems_seen)}',
            f'  изменено старых задач: {len(problems_changed)}',
            f'  старых подпунктов в снимке: {len(old_parts)}, сверено: {len(parts_seen)}',
            f'  изменено старых подпунктов: {len(parts_changed)}',
            f'  новых задач: {len(new_ids)}',
            f'  новых без Source: {len(orphans)}',
            f'  задач в базе: {total} (было {base["counts"]["Problem"]})',
            f'  новых по источникам: '
            f'{ {k: v for k, v in sorted(new_by_source.items()) if v} }',
            f'  счётчики сейчас: {counts()}',
        ]
        if problems:
            raise CommandError(
                'ИНВАРИАНТЫ НАРУШЕНЫ:\n  ' + '\n  '.join(problems)
                + '\n\n' + '\n'.join(lines))
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))
