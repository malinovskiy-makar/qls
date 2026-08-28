# -*- coding: utf-8 -*-
"""Применить человеческий фикс-пак МатЭк (matek_fixed.json) к банку задач.

Пакет собрал и лично проверил владелец: 745 задач источника МатЭк, у
которых он исправил формулы, разметку и разбивку на подпункты. Это
ЕДИНСТВЕННОЕ основание для правки существующих statement/answer/solution
(P0 CLAUDE.md запрещает такую правку моделью — здесь правит человек, код
только переносит его правки в базу дословно).

Главное правило переноса: правка применяется, ТОЛЬКО если текст в базе
совпал с тем, что видел человек (`before`). Разошёлся — правка НЕ
применяется и попадает в список расхождений. Никакого «похоже, имелось
в виду вот это».

По умолчанию — сухой прогон (ничего не пишется). Запись — только с
`--apply`.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.core import convert_problem, may_render_as_markdown
from problems.models import Problem, ProblemPart

DEFAULT_PACK = os.path.join(
    os.path.dirname(settings.BASE_DIR), 'weconomics-data',
    'matek_fixed_20260826', 'matek_fixed.json',
)
MATEK_SOURCE_ID = 13
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')

#: имя поля в пакете -> имя поля модели. Сверено с problems/models.py по
#: verbose_name, а не по догадке: Problem.statement — «Условие»,
#: Problem.answer — «Ответ», Problem.solution — «Решение (необязательно)»,
#: Problem.problem_type — «Тип задачи», Problem.title — «Заголовок».
PROBLEM_FIELDS = {
    'Условие': 'statement',
    'Ответ': 'answer',
    'Решение': 'solution',
    'Тип задачи': 'problem_type',
    'title': 'title',
}
#: правки подпунктов: ProblemPart.statement — «Условие пункта»,
#: ProblemPart.answer — «Ответ».
PART_PREFIXES = {
    'Условие подпункта': 'statement',
    'Ответ подпункта': 'answer',
}
NEW_PART = 'Новый подпункт'
REMOVED_PART = 'УБРАН ЦЕЛИКОМ'
COLLAPSED_PART = 'СХЛОПНУТ В УСЛОВИЕ'


def _squash(text):
    """Текст с точностью до пробелов — для второй попытки сопоставления."""
    return ' '.join((text or '').split())


def _classify(field):
    """(вид, имя_поля_модели) по имени поля из пакета."""
    if field in PROBLEM_FIELDS:
        return 'problem', PROBLEM_FIELDS[field]
    if field.startswith(NEW_PART):
        return 'new_part', None
    if field.endswith(REMOVED_PART):
        return 'remove_part', None
    if field.endswith(COLLAPSED_PART):
        return 'collapse_part', None
    for prefix, attr in PART_PREFIXES.items():
        if field.startswith(prefix):
            return 'part', attr
    return 'unknown', None


def _match(current, before):
    """Как текст в базе соотносится с тем, что видел человек.

    Возвращает ('exact'|'substring'|'squashed'|'empty'|None, новое_значение_
    или None). None — расхождение, правку применять нельзя."""
    current = current or ''
    if before == '':
        # человек видел пустое поле. Если в базе не пусто — это уже другой
        # текст, дописывать вслепую нельзя.
        return ('empty', None) if current.strip() == '' else (None, None)
    if current == before:
        return 'exact', None
    if before in current:
        return 'substring', None
    if _squash(current) == _squash(before):
        return 'squashed', None
    return None, None


class Command(BaseCommand):
    help = (
        'Применить человеческий фикс-пак МатЭк (matek_fixed.json). Без '
        '--apply — сухой прогон: только считает и пишет отчёт о расхождениях.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--pack', default=DEFAULT_PACK)
        parser.add_argument('--apply', action='store_true',
                            help='реально записать в базу (по умолчанию сухой прогон)')

    def handle(self, *args, **options):
        pack_path = options['pack']
        do_apply = options['apply']
        if not os.path.exists(pack_path):
            raise CommandError(f'Пакет не найден: {pack_path}')
        with open(pack_path, encoding='utf-8') as f:
            pack = json.load(f)
        entries = pack['problems']
        self.stdout.write(f'Пакет: {pack_path}\nЗадач в пакете: {len(entries)}')

        # --- Шаг 1: все ли задачи есть в базе и все ли они МатЭк ---
        ids = [e['problem_id'] for e in entries]
        if len(set(ids)) != len(ids):
            raise CommandError('В пакете есть повторяющиеся problem_id')
        found = set(Problem.objects.filter(id__in=ids).values_list('id', flat=True))
        missing = sorted(set(ids) - found)
        if missing:
            raise CommandError(
                f'{len(missing)} задач из пакета НЕТ в базе, останавливаюсь: {missing[:30]}'
            )
        matek = set(
            Problem.objects.filter(id__in=ids, source_references__source_id=MATEK_SOURCE_ID)
            .values_list('id', flat=True)
        )
        alien = sorted(set(ids) - matek)
        if alien:
            raise CommandError(
                f'{len(alien)} задач из пакета не относятся к источнику МатЭк '
                f'(source_id={MATEK_SOURCE_ID}), останавливаюсь: {alien[:30]}'
            )
        self.stdout.write(self.style.SUCCESS(
            f'Все {len(ids)} задач найдены в базе и относятся к МатЭк.'
        ))

        problems = {
            p.id: p for p in
            Problem.objects.filter(id__in=ids).prefetch_related('parts')
        }

        # --- Шаг 2: бэкап текущих значений ДО единой записи ---
        os.makedirs(OUT_DIR, exist_ok=True)
        backup_path = os.path.join(OUT_DIR, 'matek_fixed_backup.json')
        backup = [{
            'problem_id': p.id,
            'title': p.title,
            'statement': p.statement,
            'answer': p.answer,
            'solution': p.solution,
            'problem_type': p.problem_type,
            'content_format': p.content_format,
            'parts': [{
                'id': part.id, 'label': part.label, 'statement': part.statement,
                'answer': part.answer, 'solution': part.solution,
                'points': str(part.points) if part.points is not None else None,
                'order': part.order,
            } for part in p.parts.all()],
        } for p in (problems[i] for i in ids)]
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({
                'note': 'Снимок ДО применения matek_fixed.json — для отката.',
                'pack': os.path.basename(pack_path),
                'count': len(backup),
                'problems': backup,
            }, f, ensure_ascii=False, indent=1)
        self.stdout.write(f'Бэкап: {backup_path} ({len(backup)} задач)')

        # --- Шаг 3: разложить правки на применимые и расходящиеся ---
        applied = skipped = 0
        divergences = []
        plan = []  # (problem, [операции])

        for entry in entries:
            problem = problems[entry['problem_id']]
            parts_by_label = {part.label: part for part in problem.parts.all()}
            # порядок новых подпунктов берём из финального parts пакета,
            # а не выдумываем: пакет — источник правды о том, как должно быть.
            final_order = {p['label']: i for i, p in enumerate(entry.get('parts', []))}
            # Ярлыки, которые пакет удаляет. Нужны ДО разбора: человек
            # иногда разбивает слипшийся подпункт на несколько — тогда
            # старый «в» удаляется, а новые «в»/«г»/«д» создаются под теми
            # же ярлыками. Проверять «такой ярлык уже занят» надо против
            # состояния ПОСЛЕ удалений, иначе законная правка выглядит
            # расхождением (живые примеры — #27710 и #30012).
            removed_labels = {
                c['part_label'] for c in entry['changed']
                if c['part_label'] and (
                    c['field'].endswith(REMOVED_PART) or c['field'].endswith(COLLAPSED_PART)
                )
            }
            ops = []
            for change in entry['changed']:
                kind, attr = _classify(change['field'])
                label = change.get('part_label') or ''
                before, after = change['before'], change['after']

                def diverge(what):
                    divergences.append({
                        'problem_id': problem.id, 'field': change['field'],
                        'причина': what,
                    })

                if kind == 'unknown':
                    diverge(f'неизвестный вид правки «{change["field"]}»')
                    continue

                if kind == 'problem':
                    how, _ = _match(getattr(problem, attr), before)
                    if how is None:
                        diverge(f'текст в базе разошёлся с тем, что видел человек '
                                f'(поле {attr})')
                        continue
                    ops.append(('problem', attr, how, before, after))
                elif kind == 'part':
                    part = parts_by_label.get(label)
                    if part is None:
                        diverge(f'подпункта «{label}» нет в базе')
                        continue
                    if label in removed_labels:
                        diverge(f'подпункт «{label}» этот же пакет удаляет — '
                                f'непонятно, к какому из них правка')
                        continue
                    how, _ = _match(getattr(part, attr), before)
                    if how is None:
                        diverge(f'текст подпункта «{label}» в базе разошёлся '
                                f'(поле {attr})')
                        continue
                    ops.append(('part', (label, attr), how, before, after))
                elif kind == 'new_part':
                    if label in parts_by_label and label not in removed_labels:
                        diverge(f'подпункт «{label}» уже есть в базе, создавать нельзя')
                        continue
                    ops.append(('new_part', label, 'create', '', after))
                elif kind in ('remove_part', 'collapse_part'):
                    part = parts_by_label.get(label)
                    if part is None:
                        diverge(f'подпункта «{label}» нет в базе — удалять нечего')
                        continue
                    # удаление необратимо, поэтому текст сверяем строго
                    how, _ = _match(part.statement, before)
                    if how is None:
                        diverge(f'текст подпункта «{label}» разошёлся — не удаляю')
                        continue
                    ops.append((kind, label, how, before, after))

            applied += len(ops)
            plan.append((problem, ops, final_order))

        skipped = len(divergences)
        self.stdout.write(
            f'Правок всего: {applied + skipped}. Применимо: {applied}. '
            f'Расхождений (пропущено): {skipped}.'
        )

        # --- Шаг 4: запись ---
        content_format_set = 0
        content_format_held = 0
        if do_apply:
            problems_before = Problem.objects.count()
            with transaction.atomic():
                for problem, ops, final_order in plan:
                    self._execute(problem, ops, final_order)
                    problem.save()
                # content_format ставим ПОСЛЕ правок, на уже исправленном тексте
                for problem, _ops, _order in plan:
                    problem.refresh_from_db()
                    parts = list(problem.parts.all().order_by('order', 'label'))
                    result = convert_problem(
                        statement=problem.statement,
                        answer=problem.answer,
                        solution=problem.solution,
                        existing_parts=[(p.label, p.statement) for p in parts],
                    )
                    clean = may_render_as_markdown(result) and not result['warnings']
                    if clean:
                        if problem.content_format != Problem.ContentFormat.MARKDOWN:
                            problem.content_format = Problem.ContentFormat.MARKDOWN
                            problem.save(update_fields=['content_format'])
                        content_format_set += 1
                    else:
                        content_format_held += 1
            problems_after = Problem.objects.count()
            if problems_before != problems_after:
                raise CommandError(
                    f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было '
                    f'{problems_before}, стало {problems_after} — задач не должно '
                    f'ни прибавиться, ни убавиться'
                )
        else:
            # сухой прогон: посчитать, сколько задач стало бы markdown, нельзя
            # честно — текст ещё не исправлен. Не считаем и не выдумываем.
            self.stdout.write('Сухой прогон: в базу ничего не записано.')

        # --- Шаг 5: отчёт о расхождениях ---
        div_path = os.path.join(OUT_DIR, 'matek_fixed_divergences.md')
        with open(div_path, 'w', encoding='utf-8') as f:
            f.write(_render_divergences(divergences, applied, len(entries), do_apply))
        self.stdout.write(f'Расхождения: {div_path}')

        if do_apply:
            self.stdout.write(self.style.SUCCESS(
                f'ЗАПИСАНО. Применено правок: {applied}, пропущено: {skipped}. '
                f'content_format=markdown поставлен: {content_format_set}, '
                f'оставлено plain (не чисто после правки): {content_format_held}.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                'Сухой прогон завершён. Для записи повторить с --apply.'
            ))

    #: порядок применения внутри одной задачи: сначала удаления, потом
    #: правки уцелевших полей, и только потом создание новых подпунктов —
    #: иначе разбиение слипшегося подпункта («в» → «в»/«г»/«д») упрётся в
    #: занятый ярлык.
    _ORDER = {'remove_part': 0, 'collapse_part': 0, 'problem': 1, 'part': 1,
              'new_part': 2}

    def _execute(self, problem, ops, final_order):
        """Применить операции одной задачи к объектам в памяти/базе."""
        for kind, target, how, before, after in sorted(
                ops, key=lambda op: self._ORDER[op[0]]):
            if kind == 'problem':
                current = getattr(problem, target) or ''
                setattr(problem, target,
                        after if how in ('exact', 'squashed', 'empty')
                        else current.replace(before, after, 1))
            elif kind == 'part':
                label, attr = target
                part = problem.parts.get(label=label)
                current = getattr(part, attr) or ''
                setattr(part, attr,
                        after if how in ('exact', 'squashed', 'empty')
                        else current.replace(before, after, 1))
                part.save(update_fields=[attr])
            elif kind == 'new_part':
                ProblemPart.objects.create(
                    problem=problem, label=target, statement=after,
                    answer='', order=final_order.get(target, 0),
                )
            elif kind in ('remove_part', 'collapse_part'):
                # «схлопнут в условие» — текст подпункта уже перенесён в
                # statement отдельной правкой «Условие» того же пакета,
                # здесь остаётся только убрать сам подпункт.
                problem.parts.filter(label=target).delete()


def _render_divergences(divergences, applied, total_problems, did_apply):
    by_problem = {}
    for d in divergences:
        by_problem.setdefault(d['problem_id'], []).append(d)
    lines = [
        '# Расхождения при переносе фикс-пака МатЭк',
        '',
        f'Задач в пакете: {total_problems}. Правок применено: {applied}. '
        f'Правок пропущено из-за расхождения: {len(divergences)}.',
        f'Режим: {"ЗАПИСЬ (--apply)" if did_apply else "сухой прогон"}.',
        '',
        'Пропущенная правка — это случай, когда текст в базе не совпал с тем,',
        'что видел человек-ревьюер. Гадать, что он имел в виду, нельзя, поэтому',
        'такая правка не применяется, а остальные правки той же задачи —',
        'применяются.',
        '',
    ]
    if not divergences:
        lines.append('**Расхождений нет — весь пакет лёг дословно.**')
        return '\n'.join(lines) + '\n'
    lines += [f'## Задач с расхождениями: {len(by_problem)}', '']
    for pid in sorted(by_problem):
        lines.append(f'### #{pid}')
        lines.append('')
        for d in by_problem[pid]:
            lines.append(f'- `{d["field"]}` — {d["причина"]}')
        lines.append('')
    return '\n'.join(lines) + '\n'
