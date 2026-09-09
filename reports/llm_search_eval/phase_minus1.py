"""Фаза −1: сверка с реальностью. Только чтение базы."""
import os, sys, json, hashlib, django
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.db.models import Count
from problems.models import Problem, EconConcept, Tag, Topic
from catalog.filters import base_queryset

out = {}
out['db_name'] = str(settings.DATABASES['default']['NAME'])
out['db_engine'] = settings.DATABASES['default']['ENGINE']
out['semantic_enabled'] = settings.SEMANTIC_SEARCH_ENABLED
out['semantic_min_score'] = settings.SEMANTIC_SEARCH_MIN_SCORE

from problems.embedding_config import (ACTIVE_SPEC_NAME, EMBEDDING_FORMULA_VERSION,
                                       EMBEDDING_MODEL_NAME, CANONICAL_TAG_NAMES)
out['active_spec'] = ACTIVE_SPEC_NAME
out['formula_version'] = EMBEDDING_FORMULA_VERSION
out['model'] = EMBEDDING_MODEL_NAME
out['canonical_tag_names_in_code'] = len(CANONICAL_TAG_NAMES)

out['problem_total'] = Problem.objects.count()
out['econconcept_total'] = EconConcept.objects.count()
out['tag_total'] = Tag.objects.count()
out['topic_total'] = Topic.objects.count()
out['title_candidate_nonempty'] = Problem.objects.exclude(title_candidate='').exclude(
    title_candidate__isnull=True).count()

out['visible_catalog'] = base_queryset('catalog').count()
out['visible_tutor'] = base_queryset('tutor').count()

# векторы
out['with_embedding'] = Problem.objects.exclude(embedding__isnull=True).count()
vers = list(Problem.objects.exclude(embedding__isnull=True).values(
    'embedding_version').annotate(n=Count('id')).order_by())
out['embedding_versions'] = vers
builds = list(Problem.objects.exclude(embedding__isnull=True).values(
    'embedding_model_build').annotate(n=Count('id')).order_by())
out['embedding_builds'] = builds
out['visible_with_embedding'] = base_queryset('catalog').exclude(embedding__isnull=True).count()

# каноничность тем/тегов
out['topics_canonical'] = Topic.objects.count()
try:
    out['tags_canonical_in_db'] = Tag.objects.filter(name__in=list(CANONICAL_TAG_NAMES)).count()
except Exception as e:
    out['tags_canonical_in_db'] = f'ERR {e}'

# понятия: связь m2m
f = [x.name for x in Problem._meta.get_fields()]
out['problem_has_econ_concepts'] = 'econ_concepts' in f
if 'econ_concepts' in f:
    out['problems_with_concepts'] = Problem.objects.filter(econ_concepts__isnull=False).distinct().count()

# дедуп
out['dedup_fields'] = [x for x in f if 'dup' in x.lower()]

# отпечаток защищённых полей (для сверки в конце)
import itertools
def fingerprint():
    h = hashlib.md5()
    qs = Problem.objects.order_by('id').values_list('id', 'statement', 'answer', 'solution')
    n = 0
    for pid, st, an, so in qs.iterator(chunk_size=2000):
        h.update(f'{pid}\x1f{st or ""}\x1f{an or ""}\x1f{so or ""}\x1e'.encode('utf-8'))
        n += 1
    return h.hexdigest(), n
fp, n = fingerprint()
out['fingerprint_protected_md5'] = fp
out['fingerprint_rows'] = n

from problems.models import ProblemPart
out['problempart_total'] = ProblemPart.objects.count()
def fingerprint_parts():
    h = hashlib.md5()
    qs = ProblemPart.objects.order_by('id').values_list('id', 'statement', 'answer', 'solution')
    n = 0
    for row in qs.iterator(chunk_size=2000):
        h.update((''.join('' if v is None else str(v) for v in row) + '').encode('utf-8'))
        n += 1
    return h.hexdigest(), n
fpp, np_ = fingerprint_parts()
out['fingerprint_parts_md5'] = fpp
out['fingerprint_parts_rows'] = np_

print(json.dumps(out, ensure_ascii=False, indent=1))
