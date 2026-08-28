# -*- coding: utf-8 -*-
"""`search_eval` — измеритель поиска (С14, Уровень 0 `EMBEDDINGS.md`).

ТОЛЬКО ЧИТАЕТ БАЗУ. Ни одного `save()`, ни одного `update()` — стережёт тест
`test_команда_не_меняет_защищённые_поля`. Команда гоняется по живому банку, и
правка данных замером испортила бы ровно то, что измеряется.

## Что считает

recall@5/10/20/50, MRR@10, nDCG@10, долю «нет в индексе вовсе» и главное
число всей поисковой программы — **разрыв recall@50 − recall@5**. Разрыв это
точный потолок того, что способен дать реранкер: мал — реранкер не окупит
задержку; велик — нужное поиск находит, но плохо расставляет.

## Два среза, и оба обязательны

`prod` — что видно на сайте сегодня; эту цифру увидят бета-пользователи.
`all`  — весь банк с вектором; по нему потом будет видно, помогли ли чистка
         корпуса и формула v2.
Кого пускать в срез, решает `catalog.semantic.index_queryset` — та же
функция, которой строится индекс сайта. Своего фильтра здесь нет намеренно:
разъехавшись с прод-индексом, измеритель мерил бы не то, что показывает сайт.

## Чем считается близость

Тем же, чем на проде: косинус нормализованных векторов, то есть скалярное
произведение (`catalog/semantic.py`). Формула не переписана, взята оттуда.

⚠️ ЗАПРОС КОДИРУЕТСЯ ЛОКАЛЬНО, А НЕ ПО HTTP. На проде `semantic.embed_query`
ходит в контейнер `search`; локально его нет, и поднимать его ради замера
незачем — модель берётся тем же `search_service.app.get_model()`, что и в
сервисе, поэтому вектор получается тот же самый. Нормализация повторяет
`embed_query`: сервис отдаёт СЫРОЙ выход модели, нормализуют обе стороны
одинаково и по одному разу.

## Режимы наборов

`mode='problem'` (набор A) — запросом служит УЖЕ ПОСЧИТАННЫЙ вектор задачи,
модель не грузится вовсе. Так работает блок «Похожие задачи»
(`cache_similar`). Сама задача-запрос из выдачи исключается: иначе первое
место всегда занимала бы она сама.

`mode='text'` (наборы B и C) — строка запроса кодируется моделью.

Запуск:
    manage.py search_eval --set C
    manage.py search_eval --set A --scope prod
    manage.py search_eval --set path/to/set.json --out отчёт.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from catalog.semantic import index_queryset
from problems.embedding_config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_BUILD,
    EMBEDDING_MODEL_NAME,
)
from problems.eval_sets import DATA_DIR, load_eval_set
from problems.search_eval_metrics import aggregate, evaluate_case

KS_ПО_УМОЛЧАНИЮ = [5, 10, 20, 50]

# Сколько запросов кодируем и умножаем за раз. Матрица (запросы × корпус)
# на 2 619 запросов и 31 694 задачи — это 332 МБ float32 разом; батч держит
# память в десятках мегабайт и на скорость почти не влияет.
БАТЧ = 64


def _нормализовать(m: np.ndarray) -> np.ndarray:
    """Строки в единичную длину: тогда косинус = скалярное произведение."""
    нормы = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(нормы == 0, 1e-9, нормы)


def построить_индекс(scope):
    """Матрица нормализованных векторов и список id для среза.

    Повторяет `catalog.semantic._build_index`, но без фильтра по типу
    контента и без флагов «это тест»: измерителю нужны сырые id и порядок,
    а не готовые к показу карточки.
    """
    ids, vecs = [], []
    qs = index_queryset(scope).values_list('id', 'embedding')
    for pid, raw in qs.iterator(chunk_size=1000):
        raw = bytes(raw)
        if len(raw) != EMBEDDING_DIM * 4:
            continue          # повреждённый вектор — как и на проде, пропуск
        ids.append(pid)
        vecs.append(np.frombuffer(raw, dtype=np.float32))
    if not vecs:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []
    return _нормализовать(np.stack(vecs)), ids


def _кодировщик_модели():
    """Локальный кодировщик, тот же билд модели, что у сервиса поиска."""
    from search_service.app import get_model

    model = get_model()

    def кодировать(тексты):
        return np.asarray(model.encode(list(тексты), show_progress_bar=False),
                          dtype=np.float32)

    return кодировать


class Command(BaseCommand):
    help = ('Замерить качество смыслового поиска на эталонном наборе '
            '(recall@K, MRR@10, nDCG@10, разрыв recall@50 - recall@5).')

    def add_arguments(self, parser):
        parser.add_argument(
            '--set', required=True,
            help='Буква набора (A/B/C) или путь к JSON-файлу набора.')
        parser.add_argument(
            '--scope', default='both', choices=['prod', 'all', 'both'],
            help='Срез индекса: prod — как на сайте, all — весь банк с '
                 'вектором, both — оба (по умолчанию).')
        parser.add_argument(
            '--ks', nargs='+', type=int, default=KS_ПО_УМОЛЧАНИЮ,
            help='Значения K для recall@K.')
        parser.add_argument(
            '--limit-queries', type=int, default=None,
            help='Взять первые N запросов набора (быстрая проверка).')
        parser.add_argument('--out', default=None, help='Куда записать отчёт.')

    def handle(self, *args, **options):
        путь_набора = self._путь_набора(options['set'])
        мета, случаи = load_eval_set(путь_набора)
        if options['limit_queries']:
            случаи = случаи[:options['limit_queries']]
        if not случаи:
            raise CommandError(f'В наборе нет ни одного запроса: {путь_набора}')

        ks = sorted(set(options['ks']))
        режим = мета.get('mode', 'text')
        срезы = ['prod', 'all'] if options['scope'] == 'both' else [options['scope']]

        # Модель нужна только текстовым наборам. В прогоне тестов подменяется
        # `_кодировщик_модели` целиком — грузить 2,12 ГБ ради проверки склейки
        # значит добавить минуты к каждому прогону CI.
        кодировать = None
        if режим == 'text':
            self.stdout.write('Загружаем модель для кодирования запросов...')
            кодировать = _кодировщик_модели()

        отчёт = {
            'set': мета,
            'set_path': str(путь_набора),
            'queries': len(случаи),
            'ks': ks,
            'engine': 'dense (косинус, catalog/semantic.py)',
            'model_name': EMBEDDING_MODEL_NAME,
            'model_build': EMBEDDING_MODEL_BUILD,
            'run_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'slices': {},
        }

        for срез in срезы:
            отчёт['slices'][срез] = self._замер(случаи, режим, срез, ks,
                                                кодировать)

        if options['out']:
            путь = Path(options['out'])
            путь.parent.mkdir(parents=True, exist_ok=True)
            путь.write_text(json.dumps(отчёт, ensure_ascii=False, indent=1),
                            encoding='utf-8')
            self.stdout.write(f'Отчёт записан: {путь}')

        self._напечатать(отчёт, ks)
        return None

    # ── внутреннее ────────────────────────────────────────────────────

    def _путь_набора(self, значение):
        if len(значение) == 1 and значение.isalpha():
            return DATA_DIR / f'eval_set_{значение.lower()}.json'
        return Path(значение)

    def _замер(self, случаи, режим, срез, ks, кодировать):
        matrix, ids = построить_индекс(срез)
        self.stdout.write(f'Срез «{срез}»: {len(ids)} задач в индексе.')
        место = {pid: i for i, pid in enumerate(ids)}
        глубина = max(ks + [50])

        результаты = []
        for начало in range(0, len(случаи), БАТЧ):
            пачка = случаи[начало:начало + БАТЧ]
            q, исключить = self._векторы_запросов(пачка, режим, кодировать,
                                                  место)
            if matrix.shape[0] == 0:
                выдачи = [[] for _ in пачка]
            else:
                оценки = matrix @ q.T                      # (N, batch)
                выдачи = []
                for столбец, свой in enumerate(исключить):
                    s = оценки[:, столбец]
                    if свой is not None:
                        # Сама задача-запрос из выдачи исключается.
                        s = s.copy()
                        s[свой] = -np.inf
                    k = min(глубина, s.shape[0])
                    верх = np.argpartition(s, -k)[-k:]
                    верх = верх[np.argsort(s[верх])[::-1]]
                    выдачи.append([ids[i] for i in верх if np.isfinite(s[i])])

            for случай, выдача in zip(пачка, выдачи):
                итог = evaluate_case(случай, выдача, место, ks)
                итог['ranked_ids'] = выдача[:глубина]
                результаты.append(итог)

        свод = aggregate(результаты, ks)
        свод['index_size'] = len(ids)
        свод['scope'] = срез
        свод['cases'] = результаты
        return свод

    def _векторы_запросов(self, пачка, режим, кодировать, место):
        """Векторы запросов пачки и позиции, которые надо вычеркнуть."""
        if режим == 'problem':
            from problems.models import Problem

            ids = [c.meta.get('query_problem_id') for c in пачка]
            блобы = dict(Problem.objects.filter(pk__in=[i for i in ids if i])
                         .values_list('id', 'embedding'))
            строки, исключить = [], []
            for pid in ids:
                raw = блобы.get(pid)
                if raw is None or len(bytes(raw)) != EMBEDDING_DIM * 4:
                    # Нет вектора у самой задачи-запроса — искать нечем.
                    строки.append(np.zeros(EMBEDDING_DIM, dtype=np.float32))
                else:
                    строки.append(np.frombuffer(bytes(raw), dtype=np.float32))
                исключить.append(место.get(pid))
            return _нормализовать(np.stack(строки)), исключить

        векторы = np.asarray(кодировать([c.query for c in пачка]),
                             dtype=np.float32)
        return _нормализовать(векторы), [None] * len(пачка)

    def _напечатать(self, отчёт, ks):
        имя = отчёт['set'].get('name', '?')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Набор {имя}: {отчёт["queries"]} запросов'))
        for срез, свод in отчёт['slices'].items():
            подпись = ('срез прода (что видно на сайте)' if срез == 'prod'
                       else 'весь банк с вектором')
            self.stdout.write('')
            self.stdout.write(f'── {подпись}: {свод["index_size"]} задач ──')
            for k in ks:
                self.stdout.write(f'   recall@{k:<3} {свод["recall"][k]:.3f}')
            self.stdout.write(f'   MRR@10     {свод["mrr_10"]:.3f}')
            self.stdout.write(f'   nDCG@10    {свод["ndcg_10"]:.3f}')
            self.stdout.write(
                f'   нет в индексе вовсе: {свод["unreachable_count"]} '
                f'({свод["unreachable_share"]:.1%})')
            self.stdout.write(self.style.WARNING(
                f'   ГЛАВНОЕ ЧИСЛО — разрыв recall@50 − recall@5: '
                f'{свод["gap_50_5"]:+.3f}'))
