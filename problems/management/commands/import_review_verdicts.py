"""Импорт вердиктов ручного ревью из JSON-файла оболочки reviewer.html.

Файл создаёт кнопка «Скачать вердикты (JSON)» в офлайн-пакете
(export_review_bundle). Понимаются ОБА формата:

  v1 (`qls-review-verdicts-v1`) — у вердикта одна `category` (строка).
     Так лежат 2 401 вердикт Анича по ILE; конвертировать их не нужно.
  v2 (`qls-review-verdicts-v2`) — у вердикта список `categories`: оболочка
     разрешает отметить несколько дефектов сразу. В базе это несколько строк
     ReviewVerdict с ОДНИМ И ТЕМ ЖЕ комментарием — комментарий относится ко
     всей задаче, а не к отдельной категории.

Импорт ИДЕМПОТЕНТЕН по ключу (bundle, problem, category): повторный импорт
того же файла ничего не дублирует. Набор категорий задачи внутри пакета
ЗАМЕЩАЕТСЯ содержимым файла — если ревьюер снял категорию и выгрузил заново,
лишняя строка удаляется, иначе база показывала бы отменённый дефект.

    ./venv/bin/python manage.py import_review_verdicts verdicts_aa.json
    ./venv/bin/python manage.py import_review_verdicts file.json --reviewer "Ксения"

После импорта печатается сводка по категориям.
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.models import Problem, ReviewVerdict
from problems.review_categories import (CATEGORY_KEYS, CATEGORY_LABELS,
                                        VERDICTS_FORMAT_V1, VERDICTS_FORMATS)


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


def verdict_categories(entry, fmt):
    """Список категорий вердикта независимо от версии формата файла."""
    if fmt == VERDICTS_FORMAT_V1:
        cat = entry.get('category')
        return [cat] if cat is not None else []
    cats = entry.get('categories')
    if isinstance(cats, list):
        # Порядок не важен, но дубли в файле превратились бы в лишний UPDATE.
        seen, out = set(), []
        for c in cats:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out
    # v2-файл со старым полем — принимаем, чтобы не отказать из-за мелочи.
    return [entry['category']] if entry.get('category') else []


class Command(BaseCommand):
    help = 'Импортировать вердикты ревью из JSON-файла оболочки reviewer.html.'

    def add_arguments(self, parser):
        parser.add_argument('file', help='JSON-файл вердиктов из reviewer.html.')
        parser.add_argument('--reviewer', default=None,
                            help='Переопределить имя ревьюера из файла.')
        parser.add_argument('--bundle', default=None,
                            help='Переопределить пакет (по умолчанию — '
                                 'bundle_id из файла).')

    def handle(self, *args, **opts):
        path = Path(opts['file'])
        if not path.exists():
            raise CommandError(f'Файл не найден: {path}')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CommandError(f'Файл не читается как JSON: {exc}')

        fmt = data.get('format')
        if fmt not in VERDICTS_FORMATS:
            raise CommandError(
                f'Неожиданный формат {fmt!r} — '
                f'жду один из {list(VERDICTS_FORMATS)} (файл из reviewer.html).')
        verdicts = data.get('verdicts')
        if not isinstance(verdicts, list):
            raise CommandError('В файле нет списка verdicts.')

        reviewer = (opts['reviewer'] if opts['reviewer'] is not None
                    else data.get('reviewer') or '')
        bundle = (opts['bundle'] if opts['bundle'] is not None
                  else data.get('bundle_id') or '')

        # Категории проверяем ДО записи: незнакомый ключ — весь файл в отказ
        # (это рассинхрон версий пакета и кода, а не «плохая строчка»).
        bad_cats = sorted({c for v in verdicts
                           for c in verdict_categories(v, fmt)
                           if c not in CATEGORY_KEYS})
        if bad_cats:
            raise CommandError(f'Неизвестные категории: {bad_cats}. '
                               f'Допустимые: {CATEGORY_KEYS}')

        ids = [v.get('problem_id') for v in verdicts]
        known_ids = set(Problem.objects.filter(id__in=[i for i in ids if i])
                        .values_list('id', flat=True))

        # Ключ идемпотентности не содержит ревьюера, поэтому чужой вердикт по
        # той же (пакет, задача, категория) молча затёрся бы. Такое не решаем
        # за человека: показываем и отказываемся целиком.
        wanted = defaultdict(set)
        for v in verdicts:
            pid = v.get('problem_id')
            if pid in known_ids:
                wanted[pid].update(verdict_categories(v, fmt))
        existing = list(ReviewVerdict.objects.filter(
            bundle=bundle, problem_id__in=list(wanted.keys())))
        foreign = [rv for rv in existing
                   if rv.reviewer and reviewer and rv.reviewer != reviewer
                   and rv.category in wanted.get(rv.problem_id, ())]
        if foreign:
            sample = ', '.join('#{} ({})'.format(rv.problem_id, rv.reviewer)
                               for rv in foreign[:10])
            raise CommandError(
                f'В пакете {bundle!r} уже есть {len(foreign)} вердиктов другого '
                f'ревьюера по тем же задачам и категориям: {sample}. '
                f'Импорт от имени {reviewer!r} затёр бы их. Разведите ревьюеров '
                f'по разным пакетам (--bundle) или импортируйте под тем же именем.')

        by_key = {(rv.problem_id, rv.category): rv for rv in existing}
        created = updated = unchanged = removed = 0
        quoted_problems, quote_rows = set(), 0
        skipped_ids = []
        summary = Counter()

        with transaction.atomic():
            for v in verdicts:
                pid = v.get('problem_id')
                if pid not in known_ids:
                    skipped_ids.append(pid)
                    continue
                comment = v.get('comment') or ''
                # Цитаты есть только в v3; у v1/v2 их нет — это пустой список,
                # а не отсутствие поля, иначе повторный импорт старого файла
                # выглядел бы как «ревьюер снял все цитаты».
                quotes = v.get('quotes')
                if not isinstance(quotes, list):
                    quotes = []
                if quotes:
                    quoted_problems.add(pid)
                    quote_rows += len(quotes)
                at = parse_at(v.get('at')) or timezone.now()
                for category in verdict_categories(v, fmt):
                    summary[category] += 1
                    prev = by_key.get((pid, category))
                    if prev is not None and (prev.comment, prev.reviewer,
                                             prev.quotes) == (comment, reviewer,
                                                              quotes):
                        unchanged += 1
                        continue
                    _, was_created = ReviewVerdict.objects.update_or_create(
                        bundle=bundle, problem_id=pid, category=category,
                        defaults={'comment': comment, 'reviewer': reviewer,
                                  'quotes': quotes, 'created_at': at})
                    if was_created:
                        created += 1
                    else:
                        updated += 1

            # Снятые ревьюером категории убираем — иначе база показывала бы
            # дефект, от которого он отказался. Чужие вердикты не трогаем.
            for rv in existing:
                if rv.category not in wanted.get(rv.problem_id, ()):
                    if reviewer and rv.reviewer and rv.reviewer != reviewer:
                        continue
                    rv.delete()
                    removed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Импорт {path.name} (формат {fmt}, пакет {bundle or "—"}, '
            f'ревьюер: {reviewer or "аноним"}): '
            f'новых {created}, обновлено {updated}, без изменений {unchanged}, '
            f'снято {removed}, пропущено (нет такой задачи) {len(skipped_ids)}.'))
        if skipped_ids:
            self.stdout.write(self.style.WARNING(
                f'Пропущенные id: {skipped_ids[:20]}'
                f'{"…" if len(skipped_ids) > 20 else ""}'))
        if quote_rows:
            self.stdout.write('Цитат: {} в {} задачах.'.format(
                quote_rows, len(quoted_problems)))
        self.stdout.write('Сводка по категориям:')
        for key in CATEGORY_KEYS:
            if summary[key]:
                self.stdout.write(f'  {CATEGORY_LABELS[key]}: {summary[key]}')
