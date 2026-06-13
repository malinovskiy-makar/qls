"""
Management command: import_ile

Импортирует задачи из problems_enriched.json в базу данных платформы QLS.

Запуск (из папки проекта):
    python manage.py import_ile
    python manage.py import_ile --file /path/to/problems_enriched.json
    python manage.py import_ile --dry-run   # только считает, не пишет в базу
"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from problems.models import Job, Problem, Source, SourceReference, Tag


# Путь к файлу по умолчанию (относительно корня проекта).
DEFAULT_FILE = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'ile_dataset 2 copy'
    / 'problems_enriched.json'
)

BATCH_SIZE = 100

# Первое число (целое или дробное) в строке difficulty.
_DIFFICULTY_RE = re.compile(r'(\d+(?:\.\d+)?)')


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def clean_statement(text: str, title: str) -> str:
    """
    Убирает навигацию сайта ILE из начала и конца текста задачи.

    Сырой текст выглядит так:
      «{title} | Экономика для школьников ЛЭШ ILE Об ILE … РЭШ
       {title} Задача Темы … метаданные …
       Версия для печати Только условие Условие с решением Только решение
       {СОБСТВЕННО ТЕКСТ ЗАДАЧИ}
       Войдите или зарегистрируйтесь … О проекте Сайт создан …»
    """
    if not text:
        return ''

    # 1. Отрезаем футер сайта (всё от этих слов до конца).
    for footer in ('Войдите или зарегистрируйтесь',
                   'войдите или зарегистрируйтесь',
                   'О проекте Сайт создан'):
        idx = text.find(footer)
        if idx > 0:
            text = text[:idx]

    # 2. Убираем шапку — ищем маркер конца метаданных.
    marker = 'Версия для печати'
    idx = text.find(marker)
    if idx != -1:
        after = text[idx + len(marker):]
        # Убираем три служебные ссылки печатной версии.
        for skip in ('Только условие',
                     'Условие с решением и ответом',
                     'Только решение и ответ'):
            after = after.replace(skip, '', 1)
        return after.strip()

    # Запасной вариант 1: второе вхождение заголовка.
    if title:
        p1 = text.find(title)
        if p1 != -1:
            p2 = text.find(title, p1 + 1)
            if p2 != -1:
                return text[p2 + len(title):].strip()

    # Запасной вариант 2: просто обрезаем первые 200 символов навигации.
    return text[200:].strip() if len(text) > 200 else text.strip()


def parse_difficulty(raw: str):
    """
    Парсит строку вроде «1.5 Средняя: 1.5 ( 4 оценок) 02.03.2017».
    Возвращает (difficulty_int_or_None, difficulty_native_str_max_20).

    Перевод в нашу шкалу 1–5: умножаем на 2 и округляем (1.5 → 3).
    Ограничиваем диапазоном [1, 5]. Значение 0 (нет голосов) → None.
    """
    native = raw[:20].strip() if raw else ''
    if not raw:
        return None, native

    m = _DIFFICULTY_RE.search(raw)
    if not m:
        return None, native

    try:
        val = float(m.group(1))
    except ValueError:
        return None, native

    if val == 0:
        return None, native

    scaled = round(val * 2)
    scaled = max(1, min(5, scaled))
    return scaled, native


def _make_base_slug(text: str) -> str:
    """Транслит + латинская строчная для генерации slug тегов."""
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
        'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
        'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-',
    }
    lowered = text.lower()
    transliterated = ''.join(table.get(ch, ch) for ch in lowered)
    slug = ''.join(c for c in transliterated if c.isalnum() or c == '-')
    return slug[:110] or 'tag'


def ensure_tag(name: str, cache: dict, created_names: set) -> Tag:
    """
    Находит или создаёт Tag с указанным именем.

    cache         — словарь {name: Tag}, снижает число обращений к БД.
    created_names — множество имён тегов, созданных в текущем savepoint;
                    при откате savepoint вызывающий код удалит эти ключи
                    из кэша, чтобы следующая запись создала их заново.
    """
    if name in cache:
        return cache[name]

    # Пробуем найти существующий тег.
    try:
        tag = Tag.objects.get(name=name)
        cache[name] = tag
        return tag
    except Tag.DoesNotExist:
        pass

    # Создаём новый тег с уникальным slug.
    # Каждую попытку оборачиваем в свой savepoint, чтобы IntegrityError
    # (коллизия slug) не испортила родительскую транзакцию записи.
    base_slug = _make_base_slug(name)
    slug = base_slug
    for attempt in range(1, 300):
        try:
            with transaction.atomic():
                tag = Tag.objects.create(name=name[:99], slug=slug[:119])
            cache[name] = tag
            created_names.add(name)
            return tag
        except IntegrityError:
            # Коллизия slug — добавляем числовой суффикс и пробуем снова.
            slug = f'{base_slug}-{attempt}'[:119]

    raise RuntimeError(f'Не удалось создать тег «{name}»: все варианты slug заняты')


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Импортирует задачи из ILE датасета (problems_enriched.json)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=str, default=str(DEFAULT_FILE),
            help='Путь к problems_enriched.json',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать и показывать статистику, ничего не записывать в базу',
        )

    def handle(self, *args, **options):
        filepath = Path(options['file'])
        dry_run = options['dry_run']

        if not filepath.exists():
            self.stderr.write(self.style.ERROR(f'Файл не найден: {filepath}'))
            return

        # ── Загрузка данных ──────────────────────────────────────────────────
        self.stdout.write(f'Загружаю: {filepath}')
        with open(filepath, encoding='utf-8') as f:
            records = json.load(f)
        total = len(records)
        self.stdout.write(f'Записей в файле: {total}')

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')

        # ── Источник ILE ─────────────────────────────────────────────────────
        ile_source, created_source = Source.objects.get_or_create(
            name='ILE / iloveeconomics.ru',
            defaults={
                'kind': 'онлайн-банк задач',
                'note': (
                    'Задачи с сайта iloveeconomics.ru — онлайн-банк '
                    'олимпиадных задач по экономике ЛЭШ (ВШЭ).'
                ),
            },
        )
        action = 'создан' if created_source else 'найден'
        self.stdout.write(f'Источник ILE {action}: #{ile_source.pk}')

        # ── Job (фоновая задача) ──────────────────────────────────────────────
        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'file': str(filepath), 'total': total, 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан, статус: {job.status}')

        # ── Кэши для производительности ──────────────────────────────────────
        # Все существующие теги — чтобы не делать SELECT на каждую запись.
        tag_cache: dict = {t.name: t for t in Tag.objects.all()}
        # Уже импортированные URL из этого источника — для дедупликации.
        existing_urls: set = set(
            SourceReference.objects.filter(source=ile_source)
            .values_list('url', flat=True)
        )
        self.stdout.write(
            f'Уже в базе: {len(existing_urls)} задач из этого источника'
        )

        # ── Основной цикл: батчами по {BATCH_SIZE} записей ───────────────────
        created = skipped = errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():   # один коммит на весь батч
                for record in batch:
                    url = (record.get('url') or '').strip()

                    # Дедупликация по URL.
                    if url and url in existing_urls:
                        skipped += 1
                        continue

                    # created_tag_names отслеживает теги, созданные в этом
                    # savepoint, — чтобы при ошибке очистить кэш.
                    created_tag_names: set = set()
                    try:
                        with transaction.atomic():   # savepoint на одну запись
                            title = (record.get('title') or '').strip()[:299]
                            raw_text = record.get('text') or ''
                            statement = clean_statement(raw_text, title)
                            if not statement:
                                statement = title or '—'

                            difficulty, difficulty_native = parse_difficulty(
                                record.get('difficulty') or ''
                            )

                            raw_grade = (record.get('grade') or '').strip()
                            # grade > 15 символов — скорее всего мусор, игнорируем.
                            grade = raw_grade[:49] if len(raw_grade) <= 15 else ''

                            raw_tags = record.get('tags') or ''
                            tag_names = [
                                t.strip() for t in raw_tags.split(';')
                                if t.strip()
                            ]

                            if not dry_run:
                                tags = [
                                    ensure_tag(n, tag_cache, created_tag_names)
                                    for n in tag_names
                                ]

                                problem = Problem.objects.create(
                                    title=title,
                                    statement=statement,
                                    difficulty=difficulty,
                                    difficulty_native=difficulty_native,
                                    status=Problem.Status.PUBLISHED,
                                    problem_type='',
                                )
                                if tags:
                                    problem.tags.add(*tags)

                                SourceReference.objects.create(
                                    problem=problem,
                                    source=ile_source,
                                    url=url[:199] if url else '',
                                    grade=grade,
                                )
                                if url:
                                    existing_urls.add(url)

                        created += 1

                    except Exception as exc:
                        # Savepoint откатился — теги из created_tag_names тоже.
                        # Убираем их из кэша, чтобы следующая запись создала заново.
                        for tname in created_tag_names:
                            tag_cache.pop(tname, None)
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка в записи '
                            f'«{record.get("title", "?")}»: {exc}'
                        )

            # ── Прогресс после каждого батча ─────────────────────────────────
            done = min(batch_start + BATCH_SIZE, total)
            progress = int(done / total * 100)

            if not dry_run:
                job.progress = progress
                job.result = {
                    'created': created,
                    'skipped': skipped,
                    'errors': errors,
                }
                job.save(update_fields=['progress', 'result'])

            self.stdout.write(
                f'  [{done:4d}/{total}]  '
                f'создано: {created},  '
                f'пропущено: {skipped},  '
                f'ошибок: {errors}'
            )

        # ── Завершаем Job ─────────────────────────────────────────────────────
        if not dry_run:
            job.status = Job.Status.DONE
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {
                'created': created,
                'skipped': skipped,
                'errors': errors,
            }
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Создано задач:         {created}\n'
            f'  Пропущено (дубли):     {skipped}\n'
            f'  Ошибок:                {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
