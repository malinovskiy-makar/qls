"""Слить legacy-теги, совпадающие с каноническими (решение владельца 17.09.2026).

Совпадение — то же название без учёта регистра, пробелов и «ё»
(«стагфляция» = «Стагфляция»). Вложение («потоварный налог» внутри
«Потоварный налог на продавца и на покупателя») совпадением НЕ считается:
это другой тег. Связи задач с legacy-тегом переезжают на канонический;
legacy-тег остаётся в таблице с `kind='legacy'` и без связей. Остальные
legacy-теги не трогаются — фильтры каталога их просто не показывают.

В конце печатается инвариант таксономии: канонических тем должно быть 29,
канонических тегов — 343–344.

    manage.py tags_merge_legacy            # сухой прогон (по умолчанию)
    manage.py tags_merge_legacy --apply
    manage.py tags_merge_legacy --revert reports/bank_edits/tags_merge_legacy/snapshot_<время>.json
"""
import re

from problems import bank_sync
from problems.models import Problem, Tag, Topic

from ._bank_edit import BankEditCommand


def tag_key(name):
    return re.sub(r'\s+', ' ', name or '').strip().lower().replace('ё', 'е')


class Command(BankEditCommand):
    help = 'Слить legacy-теги, совпадающие с каноническими (сухой прогон по умолчанию).'

    def build(self, options):
        result = bank_sync.empty_plan(children=('tags',))
        canonical = {tag_key(t.name): t for t in Tag.objects.filter(kind='canonical')}
        through = Problem.tags.through
        pairs = []
        ops = result['children']['tags']
        # (задача, канонический тег): уже есть или уже в плане — два legacy-тега
        # одного канона не должны дать две одинаковые связи.
        taken = set(through.objects.filter(tag__kind='canonical').values_list('problem_id', 'tag_id'))
        for legacy in Tag.objects.filter(kind='legacy').order_by('name'):
            target = canonical.get(tag_key(legacy.name))
            if target is None:
                continue
            links = list(through.objects.filter(tag_id=legacy.pk).values_list('pk', 'problem_id'))
            for pk, pid in links:
                ops['delete'].append({'pk': pk, 'problem': pid, 'key': legacy.name, 'row': {}})
                if (pid, target.pk) not in taken:
                    taken.add((pid, target.pk))
                    ops['create'].append({'problem': pid, 'key': target.name, 'row': {}})
            pairs.append('- «%s» → «%s»: связей %d' % (legacy.name, target.name, len(links)))
        header = ['- legacy-тегов, совпадающих с каноническими: %d; связей переезжает: %d'
                  % (len(pairs), len(ops['delete'])),
                  '- Инвариант: канонических тем %d (ждём 29), канонических тегов %d (ждём 343–344)'
                  % (Topic.objects.filter(is_canonical=True).count(),
                     Tag.objects.filter(kind='canonical').count())]
        return result, header, ['## Пары', ''] + (pairs or ['нет'])
