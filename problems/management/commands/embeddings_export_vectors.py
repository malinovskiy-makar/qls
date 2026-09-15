# -*- coding: utf-8 -*-
"""`embeddings_export_vectors` — вывоз ГОТОВЫХ векторов банка файлом для боя.

⚠️ ЗАЧЕМ (15.09.2026). На бою векторов нет: `dump_for_deploy` вырезает поле
`embedding`, а посчитать их там нечем — в контейнере `web` нет
`sentence_transformers` и torch намеренно (ADR 0002). Локальная база хранит
векторы, посчитанные по активной формуле и прошедшие сверку билда
(`embeddings_check_build`, отметка в `reports/formula_v2/STATE.json`). Путь
один: вывезти их файлом и ввезти на бою существующим `embeddings_import_vectors`.

Формат — РОВНО тот, что читает ввоз: пара `<out>.f32` (сырые float32, N×1024,
порядок C) и `<out>.meta.json` (`rows`, `ids`, `hashes`, `spec`, `version`).
Третий файл — `<out>.state.json`: копия отметки о пройденной сверке билда для
активной спецификации. Ввоз без такой отметки не пишет, а провести сверку на
бою нечем: модели нет в `web`, а у контейнера `search` нет ни базы, ни кода
проекта. Сверка отвечает на вопрос «совпадает ли видеокарта с CPU-контейнером
поиска», и дома на него уже ответили по этим самым векторам.

⚠️ ХЕШ — СОХРАНЁННЫЙ `embedding_source_hash`, а не пересчитанный по сегодняшним
полям: это хеш текста, по которому вектор действительно посчитан. Ввоз на бою
пересчитывает хеш по боевым полям и пропускает задачи, у которых текст
разошёлся, — так устаревший дома вектор не прилипнет к чужому тексту.

Команда ТОЛЬКО ЧИТАЕТ базу.

Запуск:
    manage.py embeddings_export_vectors --out reports/vectors/catalog
    manage.py embeddings_export_vectors --out reports/vectors/bank --all
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from catalog import filters
from problems.embedding_config import (
    ACTIVE_SPEC, EMBEDDING_DIM, EMBEDDING_MAX_SEQ_LENGTH, EMBEDDING_MODEL_BUILD,
    EMBEDDING_MODEL_NAME,
)
from problems.management.commands.embeddings_check_build import STATE_PATH
from problems.models import Problem

#: Сколько строк с векторами тянем из базы за раз.
CHUNK = 2000


class Command(BaseCommand):
    help = ('Вывезти готовые векторы банка файлом в формате '
            'embeddings_import_vectors. Только читает.')

    def add_arguments(self, parser):
        parser.add_argument('--out', required=True,
                            help='Префикс: получатся <out>.f32, <out>.meta.json '
                                 'и <out>.state.json.')
        parser.add_argument('--all', action='store_true',
                            help='Весь банк, а не только видимый каталог.')
        parser.add_argument('--state', default=str(STATE_PATH),
                            help='Где лежит отметка о сверке билда '
                                 '(по умолчанию %(default)s).')

    def handle(self, *args, **options):
        spec = ACTIVE_SPEC
        check = self._passed_build_check(Path(options['state']), spec)

        scope = 'all' if options['all'] else 'catalog'
        base = (Problem.objects.all() if options['all']
                else filters.base_queryset('catalog'))
        in_scope = base.count()
        qs = (Problem.objects.filter(pk__in=base.values('pk'))
              .exclude(embedding=None)
              .exclude(embedding_source_hash='')
              .filter(embedding_version=spec.version,
                      embedding_model_build=EMBEDDING_MODEL_BUILD)
              .order_by('id')
              .values_list('id', 'embedding', 'embedding_source_hash'))

        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        f32_path = Path(str(out) + '.f32')
        ids, hashes, broken = [], [], []
        with f32_path.open('wb') as fh:
            for pid, blob, digest in qs.iterator(chunk_size=CHUNK):
                raw = bytes(blob)
                # Битый вектор не везём: ввоз отверг бы весь файл целиком.
                if (len(raw) != EMBEDDING_DIM * 4
                        or not np.isfinite(np.frombuffer(raw, dtype=np.float32)).all()):
                    broken.append(pid)
                    continue
                fh.write(raw)
                ids.append(pid)
                hashes.append(digest)
        if not ids:
            f32_path.unlink()
            raise CommandError(
                'Вывозить нечего: в срезе «%s» нет векторов по формуле «%s» '
                '(версия %d, сборка %s).'
                % (scope, spec.name, spec.version, EMBEDDING_MODEL_BUILD))

        exported_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        meta = {
            'kind': 'embedding_vectors',
            'source_kind': 'bank_export',
            'scope': scope,
            'spec': spec.name,
            'version': spec.version,
            'model_name': EMBEDDING_MODEL_NAME,
            'model_build': EMBEDDING_MODEL_BUILD,
            'max_seq_length': EMBEDDING_MAX_SEQ_LENGTH,
            'dtype': 'float32',
            'dim': EMBEDDING_DIM,
            'rows': len(ids),
            'sample': False,
            'exported_at': exported_at,
            'build_check': check,
            'ids': ids,
            'hashes': hashes,
        }
        Path(str(out) + '.meta.json').write_text(
            json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        Path(str(out) + '.state.json').write_text(json.dumps({
            'build_check_passed': True,
            'build_check': check,
            'copied_from': str(options['state']),
            'copied_at': exported_at,
        }, ensure_ascii=False, indent=1), encoding='utf-8')

        self.stdout.write('Вывоз векторов: спецификация «%s» (версия %d), срез «%s»'
                          % (spec.name, spec.version, scope))
        self.stdout.write('   задач в срезе: %d' % in_scope)
        self.stdout.write('   вывезено векторов: %d' % len(ids))
        self.stdout.write('   без вектора или по другой формуле: %d'
                          % (in_scope - len(ids) - len(broken)))
        self.stdout.write('   битых (длина или NaN), не вывезены: %d %s'
                          % (len(broken), broken[:20]))
        self.stdout.write('   файлы: %s (%.1f МБ), .meta.json, .state.json'
                          % (f32_path, f32_path.stat().st_size / 1024 / 1024))

    def _passed_build_check(self, path, spec):
        """Отметка о сверке билда для активной спецификации — или отказ."""
        if not path.exists():
            raise CommandError(
                'Нет %s — сверка билда дома не проводилась. Непроверенные '
                'векторы на бой не везём: `embeddings_check_build` сначала.'
                % path)
        state = json.loads(path.read_text(encoding='utf-8'))
        check = state.get('build_check') or {}
        if not state.get('build_check_passed') or check.get('spec') != spec.name:
            raise CommandError(
                'Сверка билда в %s не пройдена для активной спецификации «%s» '
                '(там: пройдена=%r, спецификация=%r).'
                % (path, spec.name, state.get('build_check_passed'),
                   check.get('spec')))
        return check
