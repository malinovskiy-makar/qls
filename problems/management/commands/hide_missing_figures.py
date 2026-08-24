"""Скрыть задачи, которые без пропавшей картинки решить нельзя.

Решение владельца 2026-08-24: показывать задачу с текстом «см. рисунок» без
самого рисунка хуже, чем не показывать её вовсе. Скрытие обратимо
(``status='hidden'``, НЕ удаление), данные не теряются.

⚠️ КАКОЙ ИМЕННО МЕХАНИЗМ СКРЫТИЯ. В проекте их три, и мы берём первый:

    status='hidden'          — «убрано руками» (решение редактора)  ← ЭТОТ
    needs_quality_review     — «скрыто, потому что ПЛОХОЕ»
    hidden_pending_review    — «скрыто, потому что человек НЕ СМОТРЕЛ»

Наш случай — именно редакторское решение: текст задачи в порядке, не хватает
вложения. Ни один из двух других признаков команда не трогает.

⚠️ ЧТО НЕ ТРОГАЕМ. `statement`, `answer`, `solution` и `ProblemPart.statement`
не изменяются ни на байт — меняется только `status` и добавляется тег.

МЕТКА. Каждой затронутой задаче вешается тег «нет картинки»
(slug ``missing-figure``). По нему будущая фаза «сопоставить картинки»
найдёт их одним запросом::

    Problem.objects.filter(tags__slug='missing-figure')

Тег ставится ВСЕМ найденным нерешаемым задачам, включая те, что уже скрыты
по другой причине, — иначе часть работы по подбору файлов потерялась бы.
Статус меняется ТОЛЬКО у `published`: у `duplicate`, `draft` и `archived`
свой смысл, и затирать его скрытием нельзя.

ОБРАТИМОСТЬ. `--apply` пишет журнал старых статусов в
``reports/missing_figures/<метка>.json``; `--revert --apply` читает журнал и
возвращает статусы ровно тем задачам, которые команда меняла.

    manage.py hide_missing_figures              # проба, ничего не пишет
    manage.py hide_missing_figures --apply
    manage.py hide_missing_figures --revert --apply
"""

import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.models import Problem, Tag
from problems.missing_figures import (
    MISSING_FIGURE_TAG_NAME, MISSING_FIGURE_TAG_SLUG,
    scan_problems, unsolvable_ids,
)

OUT_DIR = os.path.join('reports', 'missing_figures')
JOURNAL = os.path.join(OUT_DIR, 'hide_journal.json')


class Command(BaseCommand):
    help = ('Прячет задачи, которые без пропавшей картинки не решаются. '
            'Без --apply только считает.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать в базу')
        parser.add_argument('--revert', action='store_true',
                            help='вернуть статусы по журналу и снять тег')

    def handle(self, *args, **opts):
        say = self.stdout.write
        os.makedirs(OUT_DIR, exist_ok=True)

        if opts['revert']:
            return self._revert(say, opts['apply'])

        found = scan_problems()
        targets = unsolvable_ids(found)
        to_hide = sorted(
            pid for pid in targets
            if found[pid]['status'] == Problem.Status.PUBLISHED)

        hidden_before = Problem.objects.filter(
            status=Problem.Status.HIDDEN).count()
        say(f'Найдено задач с недоступной картинкой: {len(found)}')
        say(f'Из них нерешаемых без картинки: {len(targets)}')
        say(f'Из них сейчас published (сменят статус): {len(to_hide)}')
        say(f'Тег «{MISSING_FIGURE_TAG_NAME}» получат все {len(targets)}')
        say(f'Скрытых (status=hidden) сейчас: {hidden_before}')

        if not opts['apply']:
            say('')
            say('ПРОБА: в базу ничего не записано. Повторите с --apply.')
            return

        with transaction.atomic():
            tag, _ = Tag.objects.get_or_create(
                slug=MISSING_FIGURE_TAG_SLUG,
                defaults={'name': MISSING_FIGURE_TAG_NAME})
            journal = {
                'stamp': timezone.now().isoformat(),
                'tagged': sorted(targets),
                'status_changed': {
                    str(pid): found[pid]['status'] for pid in to_hide},
            }
            Problem.tags.through.objects.bulk_create(
                [Problem.tags.through(problem_id=pid, tag_id=tag.pk)
                 for pid in sorted(targets)],
                ignore_conflicts=True)
            Problem.objects.filter(id__in=to_hide).update(
                status=Problem.Status.HIDDEN)
            with open(JOURNAL, 'w', encoding='utf-8') as fh:
                json.dump(journal, fh, ensure_ascii=False, indent=1)

        hidden_after = Problem.objects.filter(
            status=Problem.Status.HIDDEN).count()
        say('')
        say(f'ПРИМЕНЕНО. Скрытых стало: {hidden_after} '
            f'(было {hidden_before}, разница {hidden_after - hidden_before})')
        if hidden_after - hidden_before != len(to_hide):
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: прирост скрытых '
                f'{hidden_after - hidden_before} != {len(to_hide)}')
        say(f'Журнал отката: {JOURNAL}')
        say(f'Найти помеченные: '
            f'Problem.objects.filter(tags__slug="{MISSING_FIGURE_TAG_SLUG}")')

    # ------------------------------------------------------------------
    def _revert(self, say, apply):
        if not os.path.exists(JOURNAL):
            raise CommandError(f'Журнала нет: {JOURNAL} — откатывать нечего.')
        with open(JOURNAL, encoding='utf-8') as fh:
            journal = json.load(fh)
        changed = journal['status_changed']
        say(f'ОТКАТ по журналу от {journal["stamp"]}: '
            f'вернуть статус {len(changed)} задачам, '
            f'снять тег с {len(journal["tagged"])}.')
        if not apply:
            say('ПРОБА: в базу ничего не записано. Повторите с --apply.')
            return
        with transaction.atomic():
            for pid, old_status in changed.items():
                Problem.objects.filter(id=int(pid)).update(status=old_status)
            tag = Tag.objects.filter(slug=MISSING_FIGURE_TAG_SLUG).first()
            if tag:
                Problem.tags.through.objects.filter(
                    tag_id=tag.pk,
                    problem_id__in=journal['tagged']).delete()
        say('ОТКАТ выполнен.')
