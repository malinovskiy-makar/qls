"""Паспорт состояния базы для передачи обратно Макару.

ТОЛЬКО ЧТЕНИЕ. Ни одного save/update/create — скрипт считает и печатает.
Итог: reports/handover_back_20260820/STATE.md (для человека)
      reports/handover_back_20260820/state.json (для сверки машиной)

Макар восстановит разметку у себя из трёх файлов вердиктов и должен получить
ровно те же числа. Этот файл — эталон, с которым он себя сверит.
"""
import hashlib
import json
import os
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db.models import Count, Max  # noqa: E402

from problems.models import Problem, ProblemPart, ReviewVerdict, Source  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'reports' / 'handover_back_20260820'
OUT.mkdir(parents=True, exist_ok=True)

# Источники ищем ПО НАЗВАНИЮ, а не по числовому id: id — то, что легко
# перепутать при переносе базы (то же правило, что в export_sources_json).
# Названия взяты дословно оттуда же, id печатаем справочно — для сверки.
SOURCES = [
    ('ILE', 2, 'ILE / iloveeconomics.ru'),
    ('AA', 6, 'Сборник тестов АА'),
    ('MATEK', 13, 'МатЭк — Overleaf архивы (2021–2025)'),
]

# Видимость в каталоге — тем же выражением, что у боевой вьюхи
# catalog/views.py::problem_list (строки 90-92).
VISIBLE = dict(status=Problem.Status.PUBLISHED,
               needs_quality_review=False,
               hidden_pending_review=False)


def md5_of(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(cmd):
    try:
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, timeout=300)
        return res.stdout.decode('utf-8', 'replace')
    except Exception as exc:                      # noqa: BLE001
        return 'не удалось выполнить: {}'.format(exc)


data = OrderedDict()
data['generated_at'] = datetime.now().isoformat(timespec='seconds')
data['machine'] = 'Windows, C:\\qls (машина Анича)'

# --- 1. Файл базы и объёмы -------------------------------------------------
db_path = ROOT / 'db.sqlite3'
data['db'] = OrderedDict([
    ('file', 'db.sqlite3'),
    ('md5', md5_of(db_path)),
    ('size_bytes', db_path.stat().st_size),
    ('problem_total', Problem.objects.count()),
    ('problempart_total', ProblemPart.objects.count()),
])

# --- 2..5. Признаки --------------------------------------------------------
hr = OrderedDict()
for value in ('approved', 'defect'):
    hr[value] = Problem.objects.filter(human_review=value).count()
hr['empty'] = Problem.objects.filter(human_review='').count()
other = Problem.objects.count() - sum(hr.values())
if other:
    hr['прочие_значения'] = other
data['human_review'] = hr

data['flags'] = OrderedDict([
    ('hidden_pending_review_true', Problem.objects.filter(hidden_pending_review=True).count()),
    ('needs_quality_review_true', Problem.objects.filter(needs_quality_review=True).count()),
    ('solution_needs_review_true', Problem.objects.filter(solution_needs_review=True).count()),
    ('duplicate_of_not_null', Problem.objects.filter(duplicate_of__isnull=False).count()),
    ('embedding_not_empty', Problem.objects.exclude(embedding__isnull=True).count()),
])

# --- 6. Распределение статусов --------------------------------------------
data['status'] = OrderedDict(
    (row['status'], row['n'])
    for row in Problem.objects.values('status').annotate(n=Count('id')).order_by('-n')
)

# --- 8. ReviewVerdict ------------------------------------------------------
data['review_verdict_total'] = ReviewVerdict.objects.count()
verdicts = []
rows = (ReviewVerdict.objects
        .values('bundle', 'category')
        .annotate(n=Count('id'))
        .order_by('bundle', '-n', 'category'))
for row in rows:
    verdicts.append(OrderedDict([
        ('bundle', row['bundle']),
        ('category', row['category']),
        ('count', row['n']),
    ]))
data['review_verdict_by_bundle_category'] = verdicts

by_bundle = (ReviewVerdict.objects.values('bundle')
             .annotate(n=Count('id'), problems=Count('problem', distinct=True))
             .order_by('bundle'))
data['review_verdict_by_bundle'] = [
    OrderedDict([('bundle', r['bundle']), ('rows', r['n']), ('problems', r['problems'])])
    for r in by_bundle
]

# --- 9. Три источника ------------------------------------------------------
src_stats = []
for key, expected_id, name in SOURCES:
    src = Source.objects.filter(name=name).first()
    if src is None:
        src_stats.append(OrderedDict([
            ('key', key), ('error', 'источник не найден по названию: ' + name)]))
        continue
    qs = Problem.objects.filter(source_references__source=src).distinct()
    total = qs.count()
    src_stats.append(OrderedDict([
        ('key', key),
        ('source_name', src.name),
        ('source_id_actual', src.id),
        ('source_id_expected', expected_id),
        ('id_matches_expected', src.id == expected_id),
        ('total', total),
        ('approved', qs.filter(human_review='approved').count()),
        ('defect', qs.filter(human_review='defect').count()),
        ('no_verdict', qs.filter(human_review='').count()),
        ('visible_in_catalog', qs.filter(**VISIBLE).count()),
        ('hidden_pending_review', qs.filter(hidden_pending_review=True).count()),
    ]))
data['sources'] = src_stats

# --- 11..12. Миграции ------------------------------------------------------
py = str(ROOT / 'venv' / 'Scripts' / 'python.exe')
show = run([py, 'manage.py', 'showmigrations', 'problems'])
show_lines = [ln.rstrip() for ln in show.splitlines() if ln.strip()]
data['showmigrations_problems_tail15'] = show_lines[-15:]

mig_dir = ROOT / 'problems' / 'migrations'
files = sorted(p for p in mig_dir.glob('00[34]*.py'))
mig_list = []
for p in files:
    st = p.stat()
    mig_list.append(OrderedDict([
        ('file', p.name),
        ('mtime', datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds')),
        ('size_bytes', st.st_size),
    ]))
data['migrations_003x_004x'] = mig_list

ours = sorted(p.name for p in mig_dir.glob('004*.py'))
data['migrations_0040_plus'] = ours

with open(OUT / 'state.json', 'w', encoding='utf-8') as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)

print('state.json записан:', OUT / 'state.json')
print('Problem:', data['db']['problem_total'],
      'ProblemPart:', data['db']['problempart_total'])
print('approved/defect/empty:', hr.get('approved'), hr.get('defect'), hr.get('empty'))
print('ReviewVerdict:', data['review_verdict_total'])
print('миграции 0040+:', ', '.join(ours) if ours else '(нет)')
