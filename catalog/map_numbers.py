"""Живые числа карты тем и ключ справочника у узлов (каталог «Стол», 18.09.2026).

Зачем: число темы в `topic_map.json` — сумма чисел тегов статичного
справочника (`catalog/taxonomy_map.py`), а не число задач базы; аудит P0
нашёл расхождение у 29 тем из 29 («Производство и издержки фирмы» 7 434 на
карте против 2 015 в фильтре). Карта и фильтры — одно состояние (решение
владельца 17.09), значит и числа на них одни.

К каждому узлу добавляются:
* `db` — ключ канонической `Topic` (тема) или `Tag` (тег), найденной по
  названию нестрого (`topic_blocks.normalize`); не нашлась — `None`, такой
  узел на карте не выбирается;
* `c` — число задач каталога с этой темой или тегом, теми же подсчётами, что
  у фильтров каталога без фильтров (`filters.base_queryset('catalog')`).

Кэш 10 минут: ключ — ETag файла карты и размер корпуса каталога.
"""
import hashlib
import json

from django.core.cache import cache
from django.db.models import Count

from . import filters
from .topic_blocks import normalize

CACHE_SECONDS = 10 * 60
CACHE_PREFIX = 'topic_map_live'


def _counts(base, field):
    return dict(base.values(field).annotate(n=Count('id', distinct=True))
                .values_list(field, 'n'))


def _build(text):
    from problems.models import Tag, Topic

    data = json.loads(text)
    base = filters.base_queryset('catalog')
    topics = {normalize(t.name): t.id for t in Topic.objects.filter(is_canonical=True)}
    tags = {normalize(t.name): t.id for t in Tag.objects.filter(kind='canonical')}
    topic_counts = _counts(base, 'topics')
    tag_counts = _counts(base, 'tags')
    for node in data.get('nodes', []):
        is_theme = node.get('k') == 'theme'
        key = (topics if is_theme else tags).get(normalize(node.get('l')))
        node['db'] = key
        node['c'] = (topic_counts if is_theme else tag_counts).get(key, 0) if key else None
    return json.dumps(data, ensure_ascii=False)


def live_payload(text, etag):
    """(текст JSON с `db` и живыми `c`, его ETag) — из кэша, если он свежий."""
    size = filters.base_queryset('catalog').count()
    key = '%s:%s:%d' % (CACHE_PREFIX, etag.strip('"'), size)
    cached = cache.get(key)
    if cached is None:
        live = _build(text)
        cached = (live, '"%s"' % hashlib.sha256(live.encode('utf-8')).hexdigest()[:32])
        cache.set(key, cached, CACHE_SECONDS)
    return cached
