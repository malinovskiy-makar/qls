# -*- coding: utf-8 -*-
"""`embeddings_export_queries` — вывоз строк запросов эталонного набора.

⚠️ **Корпус и запрос кодируются ОДНИМ билдом модели.** Смешение даёт
необъяснимый сдвиг косинуса, который не покраснеет ни в одной проверке.
Поэтому строки запросов едут на ту же арендованную машину и тем же
`tools/gpu_encode.py`, что и тексты корпуса, а не кодируются потом дома
чем попало.

Набору **A это не нужно**: там запросом служит уже посчитанный вектор самой
задачи (`mode='problem'`), модель не грузится вовсе. Команда такой набор
вывозить отказывается — молча отдать пустой файл значило бы получить дома
замер набора A по нулям и долго искать причину.

Формат тот же, что у `embeddings_export_texts`: шапка + по строке на
запрос, `{"id": порядковый номер случая, "hash": md5, "text": строка}`.
Порядковый номер, а не id задачи: у одного запроса бывает несколько
правильных ответов, а id задачи вообще не ключ здесь.

Команда ТОЛЬКО ЧИТАЕТ и базу не трогает вовсе — наборы лежат в файлах.

Запуск:
    manage.py embeddings_export_queries --set C   --out reports/formula_v2/queries_c58.jsonl
    manage.py embeddings_export_queries --set c_v3 --out reports/formula_v2/queries_c65.jsonl
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.embedding_config import (
    EMBEDDING_MAX_SEQ_LENGTH, EMBEDDING_MODEL_BUILD, EMBEDDING_MODEL_NAME,
)
from problems.eval_sets import DATA_DIR, load_eval_set
from problems.management.commands.embeddings_export_texts import text_hash


def набор_путь(значение):
    """Буква набора, суффикс вроде `c_v3` или прямой путь к файлу."""
    путь = Path(значение)
    if путь.suffix == '.json':
        return путь
    return DATA_DIR / ('eval_set_%s.json' % значение.lower())


class Command(BaseCommand):
    help = ('Вывезти строки запросов эталонного набора — чтобы запросы '
            'кодировались тем же билдом модели, что и корпус.')

    def add_arguments(self, parser):
        parser.add_argument('--set', required=True,
                            help='Буква набора (C), суффикс файла (c_v3) или '
                                 'путь к JSON.')
        parser.add_argument('--out', required=True, help='Куда писать JSONL.')

    def handle(self, *args, **options):
        путь = набор_путь(options['set'])
        if not путь.exists():
            raise CommandError('Нет файла набора: %s' % путь)
        мета, случаи = load_eval_set(путь)

        режим = мета.get('mode', 'text')
        if режим != 'text':
            raise CommandError(
                'Набор «%s» в режиме %r — запросом служит уже посчитанный '
                'вектор задачи, кодировать нечего. Вывозить строки нужно '
                'только текстовым наборам (B, C).'
                % (мета.get('name', '?'), режим))
        if not случаи:
            raise CommandError('В наборе нет ни одного запроса: %s' % путь)

        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        шапка = {
            'kind': 'embedding_queries',
            'set': мета.get('name', '?'),
            'set_path': str(путь),
            'mode': режим,
            'model_name': EMBEDDING_MODEL_NAME,
            'model_build': EMBEDDING_MODEL_BUILD,
            'max_seq_length': EMBEDDING_MAX_SEQ_LENGTH,
            'rows': len(случаи),
            'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        with out.open('w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(шапка, ensure_ascii=False) + '\n')
            for номер, случай in enumerate(случаи):
                fh.write(json.dumps(
                    {'id': номер, 'hash': text_hash(случай.query),
                     'text': случай.query}, ensure_ascii=False) + '\n')

        self.stdout.write(self.style.SUCCESS(
            'Вывезено %d запросов набора «%s» → %s'
            % (len(случаи), мета.get('name', '?'), out)))
        return None
