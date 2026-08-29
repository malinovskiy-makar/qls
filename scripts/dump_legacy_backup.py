# -*- coding: utf-8 -*-
"""Снимок текста легаси-корпуса ПЕРЕД боевым рендером — журнал отката.

Пишет `id -> statement/answer/solution/content_format` плюс все
`ProblemPart` по четырём легаси-источникам. Формат — как у
`matek_fixed_backup.json` (`apply_matek_fixed.py`), чтобы откат читался
тем же способом, что и прежние снимки.

Берётся ВЕСЬ кандидатский корпус источников, а не только PASS-множество:
снимок не должен зависеть от того, что решил шлюз, иначе при спорном
вердикте откатывать будет нечего.

Только читает. Запускать ДО `render_legacy_sources --apply`:

    venv313/Scripts/python.exe scripts/dump_legacy_backup.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.conf import settings

from problems.management.commands.render_legacy_sources import SOURCES
from problems.models import Problem

OUT_DIR = os.path.join(settings.BASE_DIR, 'backups')


def main():
    source_ids = [sid for sid, _name in SOURCES.values()]
    qs = (
        Problem.objects.filter(source_references__source_id__in=source_ids)
        .distinct()
        .prefetch_related('parts')
        .order_by('id')
    )
    backup = [{
        'problem_id': p.id,
        'title': p.title,
        'statement': p.statement,
        'answer': p.answer,
        'solution': p.solution,
        'problem_type': p.problem_type,
        'content_format': p.content_format,
        'status': p.status,
        'parts': [{
            'id': part.id, 'label': part.label, 'statement': part.statement,
            'answer': part.answer, 'solution': part.solution,
            'points': str(part.points) if part.points is not None else None,
            'order': part.order,
        } for part in p.parts.all()],
    } for p in qs.iterator(chunk_size=500)]

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, 'legacy_text_backup_20260829.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            'note': 'Снимок текста 4 легаси-источников ДО боевого рендера '
                    '(render_legacy_sources --apply) — для отката.',
            'sources': {slug: name for slug, (_sid, name) in SOURCES.items()},
            'count': len(backup),
            'problems': backup,
        }, f, ensure_ascii=False, indent=1)

    parts_total = sum(len(b['parts']) for b in backup)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f'Задач в снимке:      {len(backup)}')
    print(f'ProblemPart в снимке: {parts_total}')
    print(f'Файл:                 {path}')
    print(f'Размер:               {size_mb:.1f} МБ')


if __name__ == '__main__':
    main()
