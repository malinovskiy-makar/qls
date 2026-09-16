"""Метки подпунктов 1, 2, 3 → а, б, в у открытых задач (решение владельца 17.09.2026).

Только у задач, которые НЕ тест (у теста цифры — варианты ответа) и у
которых ВСЕ метки подпунктов цифровые. Задача пропускается, если ответ или
решение (задачи и подпунктов) ссылается на цифры — «1)», строка «1. …»,
«пункт 2», — или условие говорит «пункт N»: иначе текст разошёлся бы с
метками. Скобка и точка в метке сохраняются: «1)» → «а)».
Метка подпункта в отпечаток вектора не входит — векторы не устаревают.

    manage.py parts_relabel_letters            # сухой прогон (по умолчанию)
    manage.py parts_relabel_letters --apply
    manage.py parts_relabel_letters --revert reports/bank_edits/parts_relabel_letters/snapshot_<время>.json
"""
import re
from collections import defaultdict

from problems import bank_sync, problem_types
from problems.models import Problem, ProblemPart

from ._bank_edit import BankEditCommand

LETTERS = 'абвгдежзиклмнопрст'
LABEL_RE = re.compile(r'^(\(?)(\d{1,2})([).]?)$')
REF_RES = {
    'paren': re.compile(r'(?<![\w.,])[1-9]\)'),
    'dot': re.compile(r'(?m)^\s*[1-9]\.\s'),
    'word': re.compile(r'(?i)\bпункт\w*\s*[1-9]\b'),
}


def letter_label(label):
    """«1» → «а», «2)» → «б)», «(3)» → «(в)»; не цифровая метка → None."""
    m = LABEL_RE.match((label or '').strip())
    if not m or not 1 <= int(m.group(2)) <= len(LETTERS):
        return None
    return m.group(1) + LETTERS[int(m.group(2)) - 1] + m.group(3)


class Command(BankEditCommand):
    help = 'Цифровые метки подпунктов открытых задач → буквы (сухой прогон по умолчанию).'

    def build(self, options):
        from catalog.filters import base_queryset
        visible = set(base_queryset('catalog').values_list('id', flat=True))
        parts = defaultdict(list)
        for row in ProblemPart.objects.values('pk', 'problem_id', 'label', 'order', 'statement',
                                              'answer', 'solution').iterator(chunk_size=5000):
            parts[row['problem_id']].append(row)
        candidates = [pid for pid, rows in parts.items()
                      if all(letter_label(r['label']) for r in rows)]
        info = {}
        for chunk in bank_sync.chunks(candidates):
            for row in Problem.objects.filter(id__in=chunk).values_list(
                    'id', 'problem_type', 'statement', 'answer', 'solution'):
                info[row[0]] = row[1:]

        result = bank_sync.empty_plan(children=('parts',))
        ops = result['children']['parts']
        skipped_refs, tests = [], 0
        for pid in sorted(candidates):
            ptype, statement, answer, solution = info[pid]
            if problem_types.is_test(ptype):
                tests += 1
                continue
            rows = parts[pid]
            texts = [answer, solution] + [r['answer'] for r in rows] + [r['solution'] for r in rows]
            hits = sorted({name for name, rx in REF_RES.items() if any(rx.search(t or '') for t in texts)})
            if any(REF_RES['word'].search(t or '') for t in [statement] + [r['statement'] for r in rows]):
                hits = sorted(set(hits) | {'word(условие)'})
            if hits:
                skipped_refs.append('- #%d%s: %s' % (pid, ' (виден)' if pid in visible else '', ', '.join(hits)))
                result['skipped'].append(('parts', '#%d' % pid, 'ссылки на цифры: %s' % ', '.join(hits)))
                continue
            for r in sorted(rows, key=lambda r: r['order']):
                ops['update'].append({'pk': r['pk'], 'problem': pid, 'key': r['order'],
                                      'old': {'label': r['label']}, 'new': {'label': letter_label(r['label'])}})
        changed = {item['problem'] for item in ops['update']}
        header = ['- Задач с одними цифровыми метками: %d, из них тестов (не трогаем): %d'
                  % (len(candidates), tests),
                  '- Переписываем: %d задач (видимых %d), подпунктов %d'
                  % (len(changed), len(changed & visible), len(ops['update'])),
                  '- Пропущено из-за ссылок на цифры: %d (видимых %d)'
                  % (len(skipped_refs), sum(1 for s in skipped_refs if '(виден)' in s))]
        return result, header, ['## Пропущены из-за ссылок', ''] + (skipped_refs or ['нет'])
