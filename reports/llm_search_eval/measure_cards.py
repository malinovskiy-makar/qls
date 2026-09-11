"""Замер реальной длины карточек в токенах на 200 случайных видимых задачах."""
import os, sys, json, random, statistics, django
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
import tiktoken
from problems.models import Problem
from catalog.filters import base_queryset

enc = tiktoken.get_encoding('o200k_base')
random.seed(20260909)
ids = list(base_queryset('catalog').values_list('id', flat=True))
sample = random.sample(ids, 200)

qs = (Problem.objects.filter(id__in=sample)
      .prefetch_related('topics', 'tags', 'econ_concepts'))

def topics_of(p):
    return [t.name for t in p.topics.all() if t.is_canonical] or [t.name for t in p.topics.all()][:1]

def judge_card(p):
    return json.dumps({
        'id': p.id,
        'тема': ', '.join(topics_of(p)),
        'теги': ', '.join(t.name for t in p.tags.all() if t.kind == 'canonical'),
        'понятия': ', '.join(c.canonical for c in p.econ_concepts.all()),
        'тип': p.problem_type or '',
        'сложность': p.difficulty or '',
        'заголовок': p.title_candidate or p.title or '',
        'дано': (p.given or '')[:300],
        'найти': (p.find or '')[:300],
        'условие': (p.statement or '')[:600],
    }, ensure_ascii=False)

def rerank_card(p):
    return json.dumps({
        'id': p.id,
        'тема': ', '.join(topics_of(p)),
        'теги': ', '.join(t.name for t in p.tags.all() if t.kind == 'canonical'),
        'понятия': ', '.join(c.canonical for c in p.econ_concepts.all()),
        'найти': (p.find or '')[:200],
        'тип': p.problem_type or '',
        'сложность': p.difficulty or '',
        'заголовок': p.title_candidate or p.title or '',
    }, ensure_ascii=False)

res = {}
for label, fn in (('judge', judge_card), ('rerank', rerank_card)):
    lens = [len(enc.encode(fn(p))) for p in qs]
    res[label] = {
        'n': len(lens), 'mean': round(statistics.mean(lens), 1),
        'median': statistics.median(lens), 'p90': sorted(lens)[int(len(lens) * .9)],
        'max': max(lens), 'min': min(lens),
    }

# длина словаря тем+тегов (кэшируемый префикс разбора запроса)
from problems.models import Topic, Tag
topics = list(Topic.objects.filter(is_canonical=True).values_list('name', flat=True))
tags = list(Tag.objects.filter(kind='canonical').values_list('name', flat=True))
res['map_prefix_tokens'] = len(enc.encode('\n'.join(topics) + '\n' + '\n'.join(tags)))
res['n_topics'] = len(topics); res['n_tags'] = len(tags)
print(json.dumps(res, ensure_ascii=False, indent=1))
