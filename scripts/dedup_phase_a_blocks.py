# -*- coding: utf-8 -*-
"""ФАЗА A.2-A.3 — состав кодируемого текста по вариантам формулы.

Считает, какая доля СИМВОЛОВ отпечатка приходится на условие задачи
(`statement` + подпункты) против всего остального, на выборке задач.

Только чтение: база открывается на чтение через ORM, ничего не пишется.
Сверка с `reports/formula_v2/gpu_out/texts_*.jsonl` доказывает, что
пересобранный здесь текст — тот же, что был реально закодирован на GPU.
"""
import argparse
import json
import os
import random
import sys

import django

# Корень проекта в пути: скрипт запускается как файл, и Python кладёт в
# sys.path каталог scripts/, а не корень.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from problems.embedding_formula import BLOCKS, SPECS  # noqa: E402
from problems.models import Problem  # noqa: E402

GPU_OUT = os.path.join('reports', 'formula_v2', 'gpu_out')
META_DIR = os.path.join('reports', 'formula_v2')

#: Условие задачи как таковое — то, ради чего дедуп и затевается.
STATEMENT_BLOCKS = ('statement', 'parts')
#: Производные от текста задачи: их писала модель или автор по этому же тексту.
DERIVED_BLOCKS = ('blurb', 'queries', 'find', 'given', 'solution', 'hints',
                  'plot')
#: Метаданные: рубрикация и служебные признаки.
META_BLOCKS_GROUP = ('topics', 'tags', 'concepts', 'features', 'kind',
                     'olympiad', 'difficulty_note', 'difficulty', 'title',
                     'skills')


def group_of(name):
    if name in STATEMENT_BLOCKS:
        return 'statement'
    if name in DERIVED_BLOCKS:
        return 'derived'
    return 'meta'


def sample_ids(n, seed):
    meta = json.load(open(os.path.join(
        META_DIR, 'vec_v2_focus_repeat.meta.json'), encoding='utf-8'))
    ids = list(meta['ids'])
    rnd = random.Random(seed)
    return sorted(rnd.sample(ids, n))


def load_problems(ids):
    qs = (Problem.objects
          .filter(id__in=ids)
          .prefetch_related('topics', 'tags', 'econ_concepts', 'parts',
                            'skills')
          .order_by('id'))
    return list(qs)


def full_statement_chars(p):
    """Длина условия задачи ЦЕЛИКОМ, без бюджетов: сколько текста вообще есть."""
    return (len(p.statement or '')
            + sum(len(ч.statement or '') for ч in p.parts.all()))


def measure(problems, spec):
    """Сумма длин блоков по группам + длина склейки, как в build_text."""
    totals = {'statement': 0, 'derived': 0, 'meta': 0}
    joined_total = 0
    rebuilt = {}
    truncated = 0
    for p in problems:
        куски = []
        for имя in spec.blocks:
            кусок = BLOCKS[имя](p, spec)
            if кусок or (имя == 'statement' and spec.has('v1')):
                куски.append(кусок)
                totals[group_of(имя)] += len(кусок)
        текст = ' '.join(куски)
        rebuilt[p.id] = текст
        joined_total += len(текст)
        # Бюджет срезал часть условия? Считаем по сырым длинам, а не по
        # склейке: метки блоков («Условие: ») длину сдвигают.
        сырое = len(p.statement or '')
        if spec.budget('statement') is not None and сырое > spec.budget('statement'):
            truncated += 1
        elif any(len(ч.statement or '') > (spec.budget('parts') or 10 ** 9)
                 for ч in p.parts.all()):
            truncated += 1
    return totals, joined_total, rebuilt, truncated


def read_gpu_texts(spec_name, wanted):
    """Тексты из выгрузки GPU для нужных id. Один проход по файлу."""
    path = os.path.join(GPU_OUT, 'texts_%s.jsonl' % spec_name)
    if not os.path.exists(path):
        return None
    нужны = set(wanted)
    out = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            # Дешёвый предфильтр: строка заведомо не про наш id.
            if not line.startswith('{"id": '):
                continue
            конец = line.find(',', 7)
            try:
                ident = int(line[7:конец])
            except ValueError:
                continue
            if ident in нужны:
                out[ident] = json.loads(line)['text']
                if len(out) == len(нужны):
                    break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=500)
    ap.add_argument('--seed', type=int, default=20260911)
    ap.add_argument('--verify-gpu', action='store_true')
    ap.add_argument('--specs', default=None,
                    help='список имён через запятую; по умолчанию все')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    ids = sample_ids(args.n, args.seed)
    problems = load_problems(ids)
    missing = len(ids) - len(problems)

    доступно = sum(full_statement_chars(p) for p in problems)

    отчёт = {'n_requested': args.n,
             'statement_chars_available': доступно, 'n_loaded': len(problems),
             'missing_in_db': missing, 'seed': args.seed, 'specs': []}

    отбор = set(args.specs.split(',')) if args.specs else set(SPECS)
    for имя in sorted(отбор):
        spec = SPECS[имя]
        totals, joined, rebuilt, truncated = measure(problems, spec)
        сумма = sum(totals.values()) or 1
        строка = {
            'spec': имя,
            'version': spec.version,
            'blocks': list(spec.blocks),
            'chars_statement': totals['statement'],
            'chars_derived': totals['derived'],
            'chars_meta': totals['meta'],
            'chars_total_blocks': sum(totals.values()),
            'chars_joined': joined,
            'share_statement': round(totals['statement'] / сумма, 4),
            'share_derived': round(totals['derived'] / сумма, 4),
            'share_meta': round(totals['meta'] / сумма, 4),
            'avg_len': round(joined / max(len(problems), 1), 1),
            'problems_truncated': truncated,
            'share_truncated': round(truncated / max(len(problems), 1), 4),
            'statement_chars_available': доступно,
            'statement_coverage': round(
                totals['statement'] / max(доступно, 1), 4),
        }
        if args.verify_gpu:
            gpu = read_gpu_texts(имя, ids)
            if gpu is None:
                строка['gpu_check'] = 'нет файла texts_%s.jsonl' % имя
            else:
                совпало = sum(1 for i, t in rebuilt.items()
                              if gpu.get(i) == t)
                строка['gpu_rows_found'] = len(gpu)
                строка['gpu_byte_exact'] = совпало
                строка['gpu_byte_exact_share'] = round(
                    совпало / max(len(gpu), 1), 4)
        отчёт['specs'].append(строка)
        print('%-24s условие %5.1f%%  производное %5.1f%%  мета %5.1f%%  '
              'средняя длина %6.0f  срез у %3d  охват условия %5.1f%%%s'
              % (имя, 100 * строка['share_statement'],
                 100 * строка['share_derived'], 100 * строка['share_meta'],
                 строка['avg_len'], truncated,
                 100 * строка['statement_coverage'],
                 ('  сверка GPU %d/%d' % (строка.get('gpu_byte_exact', 0),
                                          строка.get('gpu_rows_found', 0)))
                 if args.verify_gpu else ''),
              file=sys.stderr)

    if args.out:
        json.dump(отчёт, open(args.out, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('записано: %s' % args.out, file=sys.stderr)


if __name__ == '__main__':
    main()
