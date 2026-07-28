"""Импорт вердиктов ручного ревью из JSON-файла оболочки reviewer.html.

Файл создаёт кнопка «Скачать вердикты (JSON)» в офлайн-пакете
(export_review_bundle). Импорт ИДЕМПОТЕНТЕН: на пару (задача, ревьюер) в базе
живёт одна запись ReviewVerdict, повторный импорт того же файла ничего не
дублирует, а более свежий вердикт по той же задаче обновляет существующий.

    ./venv/bin/python manage.py import_review_verdicts verdicts_ile.json
    ./venv/bin/python manage.py import_review_verdicts file.json --reviewer "Ксения"

После импорта печатается сводка по категориям.
"""

import json
from collections import Counter
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.models import Problem, ReviewVerdict
from problems.review_categories import CATEGORY_KEYS, CATEGORY_LABELS, VERDICTS_FORMAT


def parse_at(value) -> Optional[datetime]:
    """ISO-момент вердикта из JS (`new Date().toISOString()` даёт хвост Z,
    который fromisoformat в Python 3.9 не понимает). Мусор -> None."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt


class Command(BaseCommand):
    help = 'Импортировать вердикты ревью из JSON-файла оболочки reviewer.html.'

    def add_arguments(self, parser):
        parser.add_argument('file', help='JSON-файл вердиктов из reviewer.html.')
        parser.add_argument('--reviewer', default=None,
                            help='Переопределить имя ревьюера из файла.')

    def handle(self, *args, **opts):
        path = Path(opts['file'])
        if not path.exists():
            raise CommandError(f'Файл не найден: {path}')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CommandError(f'Файл не читается как JSON: {exc}')

        if data.get('format') != VERDICTS_FORMAT:
            raise CommandError(
                f'Неожиданный формат {data.get("format")!r} — '
                f'жду {VERDICTS_FORMAT!r} (файл из reviewer.html).')
        verdicts = data.get('verdicts')
        if not isinstance(verdicts, list):
            raise CommandError('В файле нет списка verdicts.')

        reviewer = (opts['reviewer'] if opts['reviewer'] is not None
                    else data.get('reviewer') or '')

        # Категории проверяем ДО записи: незнакомый ключ — весь файл в отказ
        # (это рассинхрон версий пакета и кода, а не «плохая строчка»).
        bad_cats = sorted({v.get('category') for v in verdicts
                           if v.get('category') not in CATEGORY_KEYS})
        if bad_cats:
            raise CommandError(f'Неизвестные категории: {bad_cats}. '
                               f'Допустимые: {CATEGORY_KEYS}')

        ids = [v.get('problem_id') for v in verdicts]
        known_ids = set(Problem.objects.filter(id__in=[i for i in ids if i])
                        .values_list('id', flat=True))

        created = updated = unchanged = 0
        skipped_ids = []
        summary = Counter()
        with transaction.atomic():
            # Снимок «до» — чтобы честно посчитать обновлённые и не трогать
            # записи, которые импорт не меняет (идемпотентность).
            existing = {rv.problem_id: rv for rv in ReviewVerdict.objects
                        .filter(reviewer=reviewer, problem_id__in=known_ids)}
            for v in verdicts:
                pid = v.get('problem_id')
                if pid not in known_ids:
                    skipped_ids.append(pid)
                    continue
                category = v['category']
                comment = v.get('comment') or ''
                summary[category] += 1
                prev = existing.get(pid)
                if prev is not None and (prev.category, prev.comment) == (category, comment):
                    unchanged += 1
                    continue
                _, was_created = ReviewVerdict.objects.update_or_create(
                    problem_id=pid, reviewer=reviewer,
                    defaults={'category': category, 'comment': comment,
                              'created_at': parse_at(v.get('at')) or timezone.now()})
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Импорт {path.name} (ревьюер: {reviewer or "аноним"}): '
            f'новых {created}, обновлено {updated}, без изменений {unchanged}, '
            f'пропущено (нет такой задачи) {len(skipped_ids)}.'))
        if skipped_ids:
            self.stdout.write(self.style.WARNING(
                f'Пропущенные id: {skipped_ids[:20]}'
                f'{"…" if len(skipped_ids) > 20 else ""}'))
        self.stdout.write('Сводка по категориям:')
        for key in CATEGORY_KEYS:
            if summary[key]:
                self.stdout.write(f'  {CATEGORY_LABELS[key]}: {summary[key]}')
