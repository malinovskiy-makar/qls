# -*- coding: utf-8 -*-
"""ФАЗА A.1 — инвентарь векторных файлов вариантов формулы.

Только чтение файлов reports/formula_v2/*.meta.json. Базу не трогает.
"""
import json
import os
import sys

ROOT = os.path.join('reports', 'formula_v2')
EXPECT_ROWS = 41307
DIM = 1024


def main():
    rows = []
    for fn in sorted(os.listdir(ROOT)):
        if not fn.endswith('.meta.json'):
            continue
        path = os.path.join(ROOT, fn)
        try:
            meta = json.load(open(path, encoding='utf-8'))
        except Exception as exc:            # noqa: BLE001
            rows.append({'file': fn, 'error': str(exc)})
            continue
        if meta.get('kind') != 'embedding_vectors':
            continue
        f32 = path[:-len('.meta.json')] + '.f32'
        size = os.path.getsize(f32) if os.path.exists(f32) else None
        ids = meta.get('ids') or []
        rows.append({
            'file': fn[:-len('.meta.json')],
            'spec': meta.get('spec'),
            'version': meta.get('version'),
            'rows_meta': meta.get('rows'),
            'ids_len': len(ids),
            'ids_unique': len(set(ids)),
            'sample': meta.get('sample'),
            'f32_bytes': size,
            'f32_rows': (size // (DIM * 4)) if size else None,
            'model_build': meta.get('model_build'),
            'max_seq': meta.get('max_seq_length'),
            'full_corpus': (meta.get('rows') == EXPECT_ROWS
                            and len(ids) == EXPECT_ROWS
                            and size == EXPECT_ROWS * DIM * 4),
        })
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == '__main__':
    main()
