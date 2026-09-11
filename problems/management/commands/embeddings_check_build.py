# -*- coding: utf-8 -*-
"""`embeddings_check_build` — сверка привезённых с видеокарты векторов против CPU.

⚠️ **Это главный гейт всей аренды, и он стоит ПЕРЕД ввозом, а не после.**
На проде запрос кодирует CPU-контейнер (`search_service`), а корпус посчитан
на арендованной видеокарте. Если GPU считает хоть немного иначе, весь корпус
разъедется с запросами — МОЛЧА. Ни один тест этого не покажет: векторы на
месте, размерность верная, поиск просто станет хуже без видимой причины.
Ровно об этом предупреждает `docs/EMBEDDINGS.md`, и ровно поэтому первый шаг
на арендованной машине — `gpu_encode.py --sample 200`, а не прогон
семнадцати вариантов.

Порог: **минимальный косинус ≥ 0,9999 и медиана ≥ 0,99999.** Ниже — ввоз
запрещён.

Заодно сверяются версии библиотек из `meta.json` с
`search_service/requirements.txt`. Мажорное расхождение — отказ; расхождение
только в суффиксе сборки torch (`+cu…` против CPU-колеса) допустимо, но
пишется в отчёт: именно так и должно быть, GPU-сборка на арендованной
машине неизбежна.

Команда ТОЛЬКО ЧИТАЕТ базу. Результат кладётся в `STATE.json` — ввоз
векторов смотрит туда.

Запуск:
    manage.py embeddings_check_build --vectors reports/formula_v2/vec_v2 --sample 200
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from problems.embedding_config import EMBEDDING_DIM, EMBEDDING_MAX_SEQ_LENGTH
from problems.embedding_formula import PREFETCH, SPECS, build_text
from problems.models import Problem

#: Гейт. Ниже — ввоз запрещён.
MIN_COSINE = 0.9999
MEDIAN_COSINE = 0.99999

#: Куда кладётся отметка «сверка пройдена» — её смотрит ввоз векторов.
STATE_PATH = Path('reports/formula_v2/STATE.json')

#: Библиотеки, чьё расхождение сдвигает векторы. Токенизация и пулинг живут
#: в них, а не в весах модели.
PINNED = ('sentence-transformers', 'transformers', 'tokenizers', 'torch')
REQUIREMENTS = Path('search_service/requirements.txt')

_PIN_RE = re.compile(r'^([A-Za-z0-9_.\-]+)==([^\s#]+)')


def read_pins(path=REQUIREMENTS):
    """Закреплённые версии ML-стека из requirements сервиса поиска."""
    пины = {}
    if not path.exists():
        return пины
    for строка in path.read_text(encoding='utf-8').splitlines():
        m = _PIN_RE.match(строка.strip())
        if m and m.group(1).lower() in PINNED:
            пины[m.group(1).lower().replace('-', '_')] = m.group(2)
    return пины


def major(version):
    """Мажорная часть версии: «2.13.0+cu121» → «2»."""
    return str(version).split('+')[0].split('.')[0]


def compare_versions(meta_versions, pins):
    """Расхождения версий, разложенные на «отказ» и «в отчёт».

    Расхождение только в суффиксе сборки (`+cu121`) — законное: на
    арендованной машине CUDA-колесо, дома CPU-колесо, веса и токенизация
    те же. Мажорное расхождение — отказ.
    """
    отказы, замечания = [], []
    for имя, ожидалось in sorted(pins.items()):
        было = meta_versions.get(имя)
        if было is None:
            замечания.append('%s: версии нет в meta.json' % имя)
            continue
        if str(было) == str(ожидалось):
            continue
        if major(было) != major(ожидалось):
            отказы.append('%s: привезено %s, закреплено %s (мажорное '
                          'расхождение)' % (имя, было, ожидалось))
        elif str(было).split('+')[0] == str(ожидалось).split('+')[0]:
            замечания.append('%s: %s против %s — только суффикс сборки, '
                             'это ожидаемо для CUDA-колеса' % (имя, было, ожидалось))
        else:
            замечания.append('%s: привезено %s, закреплено %s (минорное '
                             'расхождение)' % (имя, было, ожидалось))
    return отказы, замечания


def load_vectors(prefix):
    """Матрица и метаданные привезённого файла."""
    prefix = Path(prefix)
    f32 = Path(str(prefix) + '.f32') if not str(prefix).endswith('.f32') else prefix
    meta_path = Path(str(f32)[:-4] + '.meta.json')
    if not f32.exists():
        raise CommandError('Нет файла векторов: %s' % f32)
    if not meta_path.exists():
        raise CommandError('Нет файла метаданных: %s' % meta_path)
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    сырые = np.frombuffer(f32.read_bytes(), dtype=np.float32)
    ожидалось = meta['rows'] * EMBEDDING_DIM
    if сырые.size != ожидалось:
        raise CommandError(
            'Размер %s не сходится: %d чисел, а по meta.json ожидалось '
            '%d (%d строк × %d). Файл повреждён или meta от другого прогона.'
            % (f32, сырые.size, ожидалось, meta['rows'], EMBEDDING_DIM))
    return сырые.reshape(meta['rows'], EMBEDDING_DIM), meta


def нормализовать(m):
    нормы = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(нормы == 0, 1e-9, нормы)


class Command(BaseCommand):
    help = ('Сверить привезённые с видеокарты векторы против кодирования на '
            'домашнем CPU. Гейт перед ввозом.')

    def add_arguments(self, parser):
        parser.add_argument('--vectors', required=True,
                            help='Префикс пары файлов (<...>.f32 и '
                                 '<...>.meta.json).')
        parser.add_argument('--sample', type=int, default=200,
                            help='Сколько строк пересчитать на CPU (200).')
        parser.add_argument('--state', default=str(STATE_PATH),
                            help='Куда записать отметку о пройденной сверке.')
        parser.add_argument('--no-state', action='store_true',
                            help='Не трогать STATE.json (пробный прогон).')

    def handle(self, *args, **options):
        матрица, meta = load_vectors(options['vectors'])

        if meta.get('dtype') != 'float32':
            raise CommandError('dtype привезённого файла %r, а не float32.'
                               % meta.get('dtype'))
        if meta.get('max_seq_length') != EMBEDDING_MAX_SEQ_LENGTH:
            raise CommandError(
                'max_seq_length разошёлся: привезено %r, дома %d. Это ровно '
                'тот сдвиг векторов, который не покраснеет ни в одной другой '
                'проверке.' % (meta.get('max_seq_length'),
                               EMBEDDING_MAX_SEQ_LENGTH))

        отказы, замечания = compare_versions(meta.get('versions') or {},
                                             read_pins())
        for замечание in замечания:
            self.stdout.write(self.style.WARNING('   версии: ' + замечание))
        if отказы:
            raise CommandError('Версии ML-стека разошлись мажорно — '
                               'токенизация и пулинг живут в библиотеке, '
                               'векторы будут другими:\n   ' +
                               '\n   '.join(отказы))

        имя_спеки = meta.get('spec')
        if имя_спеки not in SPECS:
            raise CommandError('В meta.json спецификация %r, а такой нет.'
                               % имя_спеки)
        spec = SPECS[имя_спеки]
        if meta.get('version') != spec.version:
            raise CommandError('meta.json называет версию %r, а спецификация '
                               '«%s» имеет версию %d.'
                               % (meta.get('version'), spec.name, spec.version))

        if meta.get('source_kind') == 'embedding_queries':
            raise CommandError(
                'Это векторы ЗАПРОСОВ, а не корпуса: пересчитать их на CPU '
                'по спецификации формулы нельзя — там нет задач. Сверку '
                'билда делайте на файле корпуса; запросы кодировались тем же '
                'прогоном и тем же билдом.')

        # ── пересчёт выборки на домашнем CPU ──────────────────────────
        ids = meta['ids'][:options['sample']]
        хеши = dict(zip(meta['ids'], meta['hashes']))
        задачи = {p.id: p for p in Problem.objects.filter(pk__in=ids)
                  .prefetch_related(*PREFETCH)}
        пропало = [i for i in ids if i not in задачи]
        if пропало:
            raise CommandError('В банке нет задач из привезённого файла: %s'
                               % пропало[:20])

        from search_service.app import get_model
        model = get_model()
        тексты = [build_text(задачи[i], spec) for i in ids]

        # Хеш пересчитывается ЗДЕСЬ И СЕЙЧАС: разошёлся — поля правились
        # после вывоза, и сравнивать векторы уже бессмысленно.
        from problems.management.commands.embeddings_export_texts import text_hash
        разошлись = [i for i, t in zip(ids, тексты) if text_hash(t) != хеши.get(i)]
        if разошлись:
            raise CommandError(
                'У %d задач текст отпечатка изменился после вывоза (%s…). '
                'Сверка билда на них ничего не докажет: разница будет от '
                'правки полей, а не от устройства.'
                % (len(разошлись), разошлись[:10]))

        свои = np.asarray(model.encode(тексты, show_progress_bar=False),
                          dtype=np.float32)
        привезённые = матрица[:len(ids)]
        косинусы = np.sum(нормализовать(свои) * нормализовать(привезённые), axis=1)

        минимум = float(np.min(косинусы))
        медиана = float(np.median(косинусы))
        среднее = float(np.mean(косинусы))
        худшие = [int(ids[i]) for i in np.argsort(косинусы)[:5]]

        self.stdout.write('Сверка билда: спецификация «%s» (версия %d), '
                          'строк %d' % (spec.name, spec.version, len(ids)))
        self.stdout.write('   устройство привоза: %s, %s'
                          % (meta.get('device'),
                             (meta.get('cuda') or {}).get('device_name', '')))
        self.stdout.write('   косинус: минимум %.7f, медиана %.7f, среднее %.7f'
                          % (минимум, медиана, среднее))
        self.stdout.write('   худшие пять задач: %s' % худшие)

        прошло = минимум >= MIN_COSINE and медиана >= MEDIAN_COSINE
        if not options['no_state']:
            self._write_state(options['state'], spec, meta, минимум, медиана,
                              len(ids), прошло)

        if not прошло:
            raise CommandError(
                'ГЕЙТ НЕ ПРОЙДЕН: минимум %.7f (порог %.4f), медиана %.7f '
                '(порог %.5f). Ввоз запрещён — это и есть смешение билдов: '
                'на проде запрос кодирует CPU-контейнер, и весь корпус '
                'разъедется с запросами молча.'
                % (минимум, MIN_COSINE, медиана, MEDIAN_COSINE))

        self.stdout.write(self.style.SUCCESS(
            '   ГЕЙТ ПРОЙДЕН — билды совпадают, ввоз разрешён.'))
        return None

    def _write_state(self, path, spec, meta, минимум, медиана, строк, прошло):
        path = Path(path)
        состояние = {}
        if path.exists():
            состояние = json.loads(path.read_text(encoding='utf-8'))
        состояние['build_check_passed'] = bool(прошло)
        состояние['build_check'] = {
            'spec': spec.name,
            'version': spec.version,
            'rows_checked': строк,
            'min_cosine': round(минимум, 7),
            'median_cosine': round(медиана, 7),
            'device': meta.get('device'),
            'versions': meta.get('versions'),
            'input_sha256': meta.get('input_sha256'),
            'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(состояние, ensure_ascii=False, indent=1),
                        encoding='utf-8')
        self.stdout.write('   отметка записана: %s' % path)
