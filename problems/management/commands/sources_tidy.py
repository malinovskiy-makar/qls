"""Источники: новые имена и слияние «ЛЭШ 2026 — Гамма» в ILE.

Решение владельца 17.09.2026. Переименование — правка справочника `Source`
по id (на бой доезжает синхронизацией банка: источник там ключуется по id).
Слияние — привязки задач ЛЭШ переезжают на ILE с теми же годом, номером и
заметкой; пустая ссылка становится главной страницей ILE. Старая запись
источника НЕ удаляется: в заметке пометка «слит в ILE 17.09».

    manage.py sources_tidy            # сухой прогон (по умолчанию)
    manage.py sources_tidy --apply
    manage.py sources_tidy --revert reports/bank_edits/sources_tidy/snapshot_<время>.json
"""
from problems import bank_sync
from problems.models import Problem, SourceReference, Source

from ._bank_edit import BankEditCommand

#: Прежнее имя → новое. Короткое тире «–» ровно как у владельца: длинное в
#: видимых строках каталога запрещено.
RENAMES = {
    'ILE / iloveeconomics.ru': 'ILE (iloveeconomics.ru)',
    'SolveHub — банк задач по экономике': 'SolveHub – банк задач по экономике',
    'МатЭк — Overleaf архивы (2021–2025)': 'МатЭк 57 школы',
    'Школково — банк задач по экономике': 'Школково – банк задач по экономике',
}
ILE_NAMES = ('ILE / iloveeconomics.ru', 'ILE (iloveeconomics.ru)')
MERGE_FROM = 'ЛЭШ 2026 — Гамма'
ILE_HOME = 'https://iloveeconomics.ru/'
MERGE_NOTE = 'слит в ILE 17.09'


class Command(BankEditCommand):
    help = 'Переименовать источники и слить «ЛЭШ 2026 — Гамма» в ILE (сухой прогон по умолчанию).'

    def build(self, options):
        result = bank_sync.empty_plan(refs=('source',), children=('source_references',))
        sources = {s.name: s for s in Source.objects.all()}
        renames = []
        for old, new in RENAMES.items():
            if old in sources:
                s = sources[old]
                result['refs']['source']['update'].append(
                    {'pk': s.pk, 'key': s.pk, 'old': {'name': old}, 'new': {'name': new}})
                renames.append('- `%s` → `%s` (id %d)' % (old, new, s.pk))
            elif new not in sources:
                result['skipped'].append(('source', old, 'нет ни под старым, ни под новым именем'))

        ile = next((sources[n] for n in ILE_NAMES if n in sources), None)
        lesh = sources.get(MERGE_FROM)
        merged = 0
        if ile is None or lesh is None:
            result['skipped'].append(('source', MERGE_FROM, 'нет источника ЛЭШ или ILE'))
        else:
            if MERGE_NOTE not in lesh.note:
                note = (lesh.note + '\n' if lesh.note else '') + MERGE_NOTE
                result['refs']['source']['update'].append(
                    {'pk': lesh.pk, 'key': lesh.pk, 'old': {'note': lesh.note}, 'new': {'note': note}})
            fields = bank_sync.CHILD_BY_NAME['source_references'].fields
            with_ile = set(SourceReference.objects.filter(source=ile).values_list('problem_id', flat=True))
            ops = result['children']['source_references']
            for ref in SourceReference.objects.filter(source=lesh).order_by('problem_id'):
                row = {f: bank_sync.dump(SourceReference._meta.get_field(f), getattr(ref, f))
                       for f in fields}
                if ref.problem_id in with_ile:
                    result['skipped'].append(('source_references', '#%d' % ref.problem_id,
                                              'у задачи уже есть привязка к ILE'))
                    continue
                ops['delete'].append({'pk': ref.pk, 'problem': ref.problem_id, 'key': lesh.pk, 'row': row})
                ops['create'].append({'problem': ref.problem_id, 'key': ile.pk,
                                      'row': dict(row, url=row['url'] or ILE_HOME)})
                merged += 1

        from catalog.filters import base_queryset
        visible = set(base_queryset('catalog').values_list('id', flat=True))
        moved = {item['problem'] for item in result['children']['source_references']['create']}
        header = ['- Переименований: %d' % len(renames),
                  '- Привязок ЛЭШ → ILE: %d (задач видимых в каталоге: %d; всего задач в базе: %d)'
                  % (merged, len(moved & visible), Problem.objects.count())]
        return result, header, ['## Переименования', ''] + (renames or ['нет'])
