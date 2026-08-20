"""export_sources_json — выгрузка трёх источников целиком в JSON.

⚠️ ТОЛЬКО ЧИТАЕТ. В базу не пишет ничего.

Пакет передачи Макару: по файлу на источник (ILE, Сборник тестов АА, МатЭк).
Внутри — ВСЕ задачи источника, без фильтра по видимости и без фильтра по
наличию вердикта: получателю нужен весь массив, чтобы посчитать эмбеддинги
разом, а чинить и выкладывать постепенно.

Тексты отдаются ДОСЛОВНО из базы, без обрезки и без санитайзера: получатель
считает по ним отпечаток, и любая «улучшенная» на выходе строка означала бы,
что он считает не то, что лежит у нас.

⚠️ ПОЛЕ `embedding` В JSON НЕ КЛАДЁТСЯ. Это бинарный вектор на 4 КБ задачу
(40 МБ на выгрузку), и он всё равно будет пересчитан заново — ради чего
выгрузка и делается. Вместо него у задачи стоит `has_embedding`: получателю
важно знать, был ли вектор, а не какой именно.

⚠️ НАЗВАНИЯ КАТЕГОРИЙ БЕРУТСЯ ИЗ `problems/review_categories.py` — это
единственная точка правды. Список категорий здесь не хардкодится: разойдясь
с ней, файл называл бы дефекты не теми словами, что оболочка ревью.

⚠️ `visible_in_catalog` СЧИТАЕТСЯ ТЕМ ЖЕ ПРИЗНАКОМ, ЧТО У БОЕВОЙ ВЬЮХИ
(`catalog/views.py::problem_list`): published + не зафлагована качественным
шлюзом + не спрятана шлюзом человеческой проверки. Свой предикат рядом
разъехался бы с сайтом на первом же изменении правил.

Порядок всего в файле детерминированный (задачи по id, подпункты по order,
темы и теги по алфавиту, вердикты по пакету и категории): два прогона обязаны
дать побайтно одинаковый JSON, иначе сверкой MD5 нельзя пользоваться.

    venv\\Scripts\\python manage.py export_sources_json
    venv\\Scripts\\python manage.py export_sources_json --out reports/handover_20260820
"""

import json
import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from problems.management.commands.apply_topic_mapping import CANONICAL
from problems.models import Problem, Source
from problems.review_categories import CATEGORY_LABELS, REVIEW_CATEGORIES

# Вид категории («ok» / «defect» / «disputed» / «trash») — оттуда же, откуда
# ключ и название. Отдельного списка не заводим.
CATEGORY_KIND = {c['key']: c['kind'] for c in REVIEW_CATEGORIES}

CANONICAL_SET = set(CANONICAL)

# Имя файла ← точное название источника в базе. Ищем ПО НАЗВАНИЮ, а не по
# числовому id: id — это то, что легко перепутать при переносе базы.
SOURCES = [
    ('ile',   'ILE / iloveeconomics.ru'),
    ('aa',    'Сборник тестов АА'),
    ('matek', 'МатЭк — Overleaf архивы (2021–2025)'),
]

EXPORT_FORMAT = 'qls-source-export-v1'


def _iso(dt):
    """Момент в ISO-8601 или None. Наивных дат в базе нет, но если попадётся,
    честнее отдать её как есть, чем приписать ей чужой часовой пояс."""
    if dt is None:
        return None
    return dt.isoformat()


def _num(value):
    """Decimal (баллы подпункта) в число. JSON про Decimal не знает."""
    if value is None:
        return None
    return float(value)


def problem_to_dict(problem, has_embedding):
    """Задача целиком: тексты, разметка ревью, признаки видимости."""

    parts = [
        {
            'order': part.order,
            'label': part.label,
            'statement': part.statement,
            'answer': part.answer,
            # Решение подпункта в списке полей задания не значилось, но оно
            # содержательное и в базе есть — отдаём.
            'solution': part.solution,
            'points': _num(part.points),
        }
        for part in problem.parts.all()
    ]

    topics = sorted(t.name for t in problem.topics.all())
    tags = sorted(t.name for t in problem.tags.all())

    refs = []
    for ref in problem.source_references.all():
        refs.append({
            'source_id': ref.source_id,
            'source_name': ref.source.name,
            'stage': ref.stage,
            'year': ref.year,
            'grade': ref.grade,
            'problem_number': ref.problem_number,
            'page': ref.page,
            'url': ref.url,
            'note': ref.note,
        })
    refs.sort(key=lambda r: (r['source_id'], r['problem_number'], r['url']))

    verdicts = []
    bundles = set()
    for v in problem.review_verdicts.all():
        bundles.add(v.bundle)
        verdicts.append({
            'bundle': v.bundle,
            'category_key': v.category,
            'category_label': CATEGORY_LABELS.get(v.category, v.category),
            'kind': CATEGORY_KIND.get(v.category, ''),
            'reviewer': v.reviewer,
            'comment': v.comment,
            'quotes': v.quotes or [],
            'created_at': _iso(v.created_at),
        })
    verdicts.sort(key=lambda v: (v['bundle'], v['category_key']))

    visible = (
        problem.status == Problem.Status.PUBLISHED
        and not problem.needs_quality_review
        and not problem.hidden_pending_review
    )

    return {
        'id': problem.id,
        'title': problem.title,
        'statement': problem.statement,
        'answer': problem.answer,
        'solution': problem.solution,
        'problem_type': problem.problem_type,
        'difficulty': problem.difficulty,
        'difficulty_native': problem.difficulty_native,
        'content_hash': problem.content_hash,
        'parts': parts,
        'parts_count': len(parts),
        'topics': topics,
        'topics_canonical': [t for t in topics if t in CANONICAL_SET],
        'tags': tags,
        'source_refs': refs,
        'attachments': sorted(f.file.name for f in problem.files.all()),

        'review': {
            'human_review': problem.human_review or None,
            'reviewed': bool(problem.human_review),
            'bundles': sorted(bundles),
            'verdicts': verdicts,
        },

        'visibility': {
            'status': problem.status,
            'needs_quality_review': problem.needs_quality_review,
            'solution_needs_review': problem.solution_needs_review,
            'hidden_pending_review': problem.hidden_pending_review,
            'visible_in_catalog': visible,
        },

        # Содержательные поля сверх списка задания: получателю они говорят,
        # что с задачей уже делали.
        'ai_blurb': problem.ai_blurb,
        'solution_ai_extracted': problem.solution_ai_extracted,
        'multiple_problems': problem.multiple_problems,
        'duplicate_of': problem.duplicate_of_id,
        'has_embedding': has_embedding,
        'created_at': _iso(problem.created_at),
        'updated_at': _iso(problem.updated_at),
    }


class Command(BaseCommand):
    help = ('Выгрузить все задачи трёх источников (ILE, АА, МатЭк) в JSON '
            'с полной разметкой ревью. Только чтение.')

    def add_arguments(self, parser):
        parser.add_argument('--out', default='reports/handover_20260820',
                            help='Куда класть файлы (по умолчанию '
                                 'reports/handover_20260820)')

    def handle(self, *args, **options):
        out_dir = options['out']
        os.makedirs(out_dir, exist_ok=True)

        generated_at = datetime.now(timezone.utc).isoformat()

        # Какие задачи несут вектор — одним дешёвым запросом на всю базу.
        # Тянуть сам BinaryField ради булева признака нельзя: это 4 КБ на
        # задачу и десятки мегабайт памяти впустую.
        with_embedding = set(
            Problem.objects.exclude(embedding__isnull=True)
            .values_list('id', flat=True)
        )

        totals = {'problems': 0, 'approved': 0, 'defect': 0, 'not_reviewed': 0}

        for slug, name in SOURCES:
            try:
                source = Source.objects.get(name=name)
            except Source.DoesNotExist:
                raise SystemExit(f'Источник не найден по названию: {name!r}')

            qs = (
                Problem.objects
                .filter(source_references__source=source)
                .distinct()
                .order_by('id')
                .defer('embedding')
                .prefetch_related('parts', 'topics', 'tags', 'files',
                                  'source_references__source', 'review_verdicts')
            )

            problems = []
            counts = {'total': 0, 'approved': 0, 'defect': 0, 'not_reviewed': 0}
            for problem in qs.iterator(chunk_size=200):
                problems.append(
                    problem_to_dict(problem, problem.id in with_embedding))
                counts['total'] += 1
                if problem.human_review == 'approved':
                    counts['approved'] += 1
                elif problem.human_review == 'defect':
                    counts['defect'] += 1
                else:
                    counts['not_reviewed'] += 1

            payload = {
                'format': EXPORT_FORMAT,
                'generated_at': generated_at,
                'source': {'id': source.id, 'name': source.name},
                'counts': counts,
                'problems': problems,
            }

            path = os.path.join(out_dir, f'{slug}.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)

            size = os.path.getsize(path)
            self.stdout.write(
                f'{slug}.json: задач {counts["total"]}, '
                f'approved {counts["approved"]}, defect {counts["defect"]}, '
                f'без вердикта {counts["not_reviewed"]}, '
                f'{size / 1024 / 1024:.1f} МБ'
            )

            totals['problems'] += counts['total']
            totals['approved'] += counts['approved']
            totals['defect'] += counts['defect']
            totals['not_reviewed'] += counts['not_reviewed']

        self.stdout.write('')
        self.stdout.write(
            f'ИТОГО: задач {totals["problems"]}, '
            f'approved {totals["approved"]}, defect {totals["defect"]}, '
            f'без вердикта {totals["not_reviewed"]}'
        )
        self.stdout.write(f'Файлы: {out_dir}')
