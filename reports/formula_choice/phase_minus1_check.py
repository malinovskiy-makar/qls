"""Фаза -1 линейки выбора формулы: сверка с реальностью.

Только читает — банк и файлы не трогает. Гоняется через:
    venv313/Scripts/python.exe reports/formula_choice/phase_minus1_check.py
"""
import json
import os
import sys

import django
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from problems.management.commands.embeddings_check_build import load_vectors  # noqa: E402
from problems.embedding_formula import SPECS, build_text  # noqa: E402
from problems.models import Problem  # noqa: E402
from catalog.semantic import index_queryset  # noqa: E402

FORMULAS = [
    'vec_v1', 'vec_v2', 'vec_v2_3000', 'vec_v2_nolimit', 'vec_v2_lean',
    'vec_v2_focus', 'vec_v2_focus_repeat', 'vec_v2_meta_first',
    'vec_v2_masked_numbers', 'vec_v2_no_solution', 'vec_v2_no_hints',
    'vec_v2_no_queries', 'vec_v2_no_offlist', 'vec_v2_no_code_features',
    'vec_v2_no_tail_meta', 'vec_v2_no_blurb',
]
PREFIX = 'reports/formula_v2/'


def main():
    print('=== 1. Размеры файлов и версии библиотек ===')
    versions_set = set()
    ids_ref = None
    for name in FORMULAS:
        matrix, meta = load_vectors(PREFIX + name)
        v = json.dumps(meta['versions'], sort_keys=True, ensure_ascii=False)
        versions_set.add(v)
        n_bytes = os.path.getsize(PREFIX + name + '.f32')
        expected = 41307 * 1024 * 4
        ok_size = 'OK' if n_bytes == expected == matrix.nbytes else 'MISMATCH'
        print(f'{name:28s} rows={meta["rows"]:6d} bytes={n_bytes:10d} {ok_size} spec={meta.get("spec")!r}')
        ids = meta['ids']
        if ids_ref is None:
            ids_ref = set(ids)
        else:
            if set(ids) != ids_ref:
                print(f'  !!! id-набор {name} расходится с первым файлом')

    print()
    print('Уникальных наборов versions среди 16 файлов:', len(versions_set))
    if len(versions_set) != 1:
        print('!!! БИЛДЫ РАЗОШЛИСЬ — СТОП')
        for v in versions_set:
            print('  ', v)
        sys.exit(1)
    else:
        print('Билд один на все 16 файлов — OK.')

    print()
    print('=== 2. Размер индекса в срезе all ===')
    all_ids = set(index_queryset('all').values_list('id', flat=True))
    print('index_queryset("all").count() =', len(all_ids))
    print('ids в файле (любом) =', len(ids_ref))
    missing_in_file = all_ids - ids_ref
    extra_in_file = ids_ref - all_ids
    print('в базе "all", но нет в файле:', len(missing_in_file))
    print('в файле, но нет в базе "all":', len(extra_in_file))

    print()
    print('=== 3. Локальный CPU-энкод vs файл (спецификация каждого файла) ===')
    sample_ids = sorted(ids_ref)[:1] + sorted(ids_ref)[len(ids_ref) // 2:len(ids_ref) // 2 + 1]
    problems = {p.pk: p for p in Problem.objects.filter(pk__in=sample_ids)}

    from search_service.app import get_model
    model = get_model()

    for name in ['vec_v2_meta_first', 'vec_v1']:
        matrix, meta = load_vectors(PREFIX + name)
        spec_name = meta.get('spec')
        spec = SPECS[spec_name]
        pos = {pid: i for i, pid in enumerate(meta['ids'])}
        print(f'--- {name} (spec={spec_name}) ---')
        for pid in sample_ids:
            p = problems[pid]
            text = build_text(p, spec)
            local_vec = np.asarray(model.encode([text], show_progress_bar=False)[0], dtype=np.float32)
            file_vec = matrix[pos[pid]]
            cos = float(
                np.dot(local_vec, file_vec)
                / (np.linalg.norm(local_vec) * np.linalg.norm(file_vec) + 1e-12)
            )
            print(f'  id={pid} cos={cos:.6f}')


if __name__ == '__main__':
    main()
