#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Кодирование текстов отпечатка на арендованной видеокарте. БЕЗ Django.

Единственный файл, который едет на арендованную машину вместе с текстами.
Зависимости — только `sentence-transformers`, `torch`, `numpy`. Django,
базы и репозитория там нет и быть не должно: база остаётся дома, туда едут
тексты, обратно — векторы, и откат — это просто «не ввозить».

Читает JSONL от `manage.py embeddings_export_texts` (первая строка — шапка,
дальше `{"id":…, "hash":…, "text":…}`) и пишет два файла:

* `<out>.f32`       — сырой float32, N × 1024, порядок СТРОГО как во входном
                      файле; ничего кроме чисел, никакого заголовка;
* `<out>.meta.json` — модель и билд, версии torch / sentence-transformers /
                      transformers / tokenizers, `max_seq_length`, устройство,
                      dtype, размер батча, число строк, sha256 входного файла,
                      массивы `id` и `hash` в том же порядке, скорость.

⚠️ **Скрипт ПАДАЕТ, если `--device cuda`, а CUDA недоступна, и если dtype не
float32.** Тихий откат на CPU здесь — худшее, что может случиться: прогон
пройдёт, займёт сутки, и никто не заметит, пока не кончится аренда. По той
же причине `max_seq_length` задаётся ЯВНО, а не берётся из конфига модели по
умолчанию: любое расхождение здесь сдвигает векторы без единого красного
теста.

⚠️ **Корпус и запрос кодируются одним билдом.** Пины версий — в
`reports/formula_v2/RUNBOOK_GPU.md`; сверку привезённого против домашнего CPU
делает `manage.py embeddings_check_build` (порог: минимальный косинус
≥ 0,9999, медиана ≥ 0,99999).

Запуск на арендованной машине:
    python gpu_encode.py --in texts_v2.jsonl --out vec_v2 --device cuda \
        --batch-size 64 --sample 200          # сначала сверка билда!
    python gpu_encode.py --in texts_v2.jsonl --out vec_v2 --device cuda
"""
import argparse
import hashlib
import json
import sys
import time

import numpy as np

DIM = 1024
DTYPE = 'float32'


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for кусок in iter(lambda: fh.read(1 << 20), b''):
            h.update(кусок)
    return h.hexdigest()


def read_jsonl(path, limit=None):
    """Шапка и строки входного файла. Порядок строк — это контракт."""
    шапка, строки = None, []
    with open(path, encoding='utf-8') as fh:
        for номер, строка in enumerate(fh):
            строка = строка.strip()
            if not строка:
                continue
            запись = json.loads(строка)
            if номер == 0 and 'text' not in запись:
                шапка = запись
                continue
            строки.append(запись)
            if limit and len(строки) >= limit:
                break
    if шапка is None:
        raise SystemExit('В файле нет шапки — это не файл вывоза текстов.')
    return шапка, строки


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--in', dest='inp', required=True)
    p.add_argument('--out', required=True,
                   help='Префикс: получатся <out>.f32 и <out>.meta.json.')
    p.add_argument('--batch-size', type=int, default=64)
    p.add_argument('--device', default='cuda')
    p.add_argument('--dtype', default=DTYPE)
    p.add_argument('--sample', type=int, default=0,
                   help='Закодировать первые N строк и выйти — сверка билда. '
                        'Первый шаг на арендованной машине, ДО прогона '
                        'вариантов.')
    p.add_argument('--max-seq-length', type=int, default=None,
                   help='Перебить max_seq_length из шапки файла. По умолчанию '
                        'берётся оттуда — так дом и аренда заведомо совпадают.')
    args = p.parse_args(argv)

    # ⚠️ Проверки ДО загрузки модели: падать надо за секунды, а не через
    # четверть часа прогрева.
    if args.dtype != DTYPE:
        raise SystemExit('dtype обязан быть %s — этим билдом живёт прод, и '
                         'любой другой заставит пересчитывать заново.' % DTYPE)

    import torch
    if args.device.startswith('cuda') and not torch.cuda.is_available():
        raise SystemExit(
            'Запрошена cuda, но torch.cuda.is_available() = False. Тихий '
            'откат на CPU здесь запрещён: прогон прошёл бы, занял сутки и '
            'съел аренду. Проверьте драйвер и CUDA-сборку torch.')

    шапка, строки = read_jsonl(args.inp, limit=args.sample or None)
    max_seq = args.max_seq_length or шапка.get('max_seq_length')
    if not max_seq:
        raise SystemExit('В шапке нет max_seq_length и он не задан флагом. '
                         'Молча взять значение по умолчанию нельзя — оно '
                         'сдвинет векторы без единого красного теста.')

    from sentence_transformers import SentenceTransformer
    имя_модели = шапка.get('model_name', 'BAAI/bge-m3')
    print('модель: %s, устройство: %s, max_seq_length: %d, строк: %d'
          % (имя_модели, args.device, max_seq, len(строки)), flush=True)

    model = SentenceTransformer(имя_модели, device=args.device)
    model.max_seq_length = max_seq

    начало = time.time()
    векторы = model.encode(
        [з['text'] for з in строки], batch_size=args.batch_size,
        show_progress_bar=True, convert_to_numpy=True)
    прошло = time.time() - начало

    векторы = np.asarray(векторы, dtype=np.float32)
    if векторы.shape != (len(строки), DIM):
        raise SystemExit('Форма выхода %s, ожидалась (%d, %d).'
                         % (векторы.shape, len(строки), DIM))
    if not np.isfinite(векторы).all():
        raise SystemExit('В выходе есть NaN или бесконечность — файл негоден.')

    with open(args.out + '.f32', 'wb') as fh:
        fh.write(векторы.tobytes(order='C'))

    import tokenizers
    import transformers
    import sentence_transformers
    мета = {
        'kind': 'embedding_vectors',
        'spec': шапка.get('spec'),
        'version': шапка.get('version'),
        'source_kind': шапка.get('kind'),
        'set': шапка.get('set'),
        'model_name': имя_модели,
        'model_build': шапка.get('model_build'),
        'max_seq_length': max_seq,
        'device': args.device,
        'dtype': DTYPE,
        'dim': DIM,
        'batch_size': args.batch_size,
        'rows': len(строки),
        'sample': bool(args.sample),
        'input_sha256': sha256_file(args.inp),
        'ids': [з['id'] for з in строки],
        'hashes': [з['hash'] for з in строки],
        'versions': {
            'torch': torch.__version__,
            'sentence_transformers': sentence_transformers.__version__,
            'transformers': transformers.__version__,
            'tokenizers': tokenizers.__version__,
            'python': sys.version.split()[0],
        },
        'cuda': {
            'available': bool(torch.cuda.is_available()),
            'device_name': (torch.cuda.get_device_name(0)
                            if torch.cuda.is_available() else ''),
        },
        'seconds': round(прошло, 1),
        'texts_per_second': round(len(строки) / прошло, 1) if прошло else None,
    }
    with open(args.out + '.meta.json', 'w', encoding='utf-8') as fh:
        json.dump(мета, fh, ensure_ascii=False, indent=1)

    print('готово: %s.f32 (%d × %d), %.1f c, %.1f текстов/с'
          % (args.out, len(строки), DIM, прошло,
             len(строки) / прошло if прошло else 0), flush=True)
    if args.sample:
        print('Это ВЫБОРКА (%d строк). Везите оба файла домой и прогоните '
              '`manage.py embeddings_check_build` ДО прогона вариантов.'
              % args.sample)


if __name__ == '__main__':
    main()
