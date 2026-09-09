# -*- coding: utf-8 -*-
"""`embeddings_import_vectors` — ввоз посчитанных векторов в банк.

Последний шаг аренды и единственный в этой цепочке, который ПИШЕТ в банк.
Всё, что до него, — файлы на диске, и откат оттуда бесплатный: просто не
ввозить. Поэтому здесь проверок больше, чем в остальных командах вместе.

Что проверяется ДО первой записи:

1. `spec` файла совпадает с `ACTIVE_SPEC_NAME`, а `version` — с
   `EMBEDDING_FORMULA_VERSION`. Ввезти векторы одной формулы, а тексты
   считать по другой — это разъезд корпуса с запросами, и он молчаливый.
2. Размерность 1024, все значения конечны, норма вектора в разумных
   пределах.
3. **Хеш текста пересчитывается ПРЯМО СЕЙЧАС** и сверяется с хешем из
   файла: разошёлся — значит поля правились после вывоза, и вектор такой
   задаче уже не соответствует. Такой id пропускается и попадает в отчёт.
4. Сверка билда (`embeddings_check_build`) пройдена — отметка в
   `STATE.json`. Без неё запись не начинается.

После записи — свип-детектор защищённых полей: `protected_fingerprint()` до
и после обязан совпасть. По умолчанию команда НИЧЕГО НЕ МЕНЯЕТ и печатает
план; запись — только с `--apply`.

Запуск:
    manage.py embeddings_import_vectors --vectors reports/formula_v2/vec_v2
    manage.py embeddings_import_vectors --vectors reports/formula_v2/vec_v2 --apply
"""
import json
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.embedding_config import (
    ACTIVE_SPEC_NAME, EMBEDDING_DIM, EMBEDDING_FORMULA_VERSION,
    EMBEDDING_MODEL_BUILD,
)
from problems.embedding_formula import PREFETCH, SPECS, build_text
from problems.embedding_provenance import (
    TEXT_PROTECTED_FIELDS, protected_fingerprint,
)
from problems.management.commands.embeddings_check_build import (
    STATE_PATH, load_vectors,
)
from problems.management.commands.embeddings_export_texts import text_hash
from problems.models import Problem

#: Норма вектора у нормализованной модели — единица. Допуск широкий: ловим
#: не «чуть-чуть не единица», а мусор вроде нулевого или разошедшегося
#: вектора.
NORM_MIN, NORM_MAX = 0.5, 2.0

#: Сколько задач пишем одной транзакцией.
BATCH = 500

#: `filter(pk__in=[...])` с десятками тысяч значений роняет SQLite
#: («too many SQL variables») — читаем задачи порциями. PostgreSQL это же
#: ограничение не задевает, но порция дешёвая и там.
ID_CHUNK = 900


class Command(BaseCommand):
    help = 'Ввезти посчитанные векторы в банк (по умолчанию — план, без записи).'

    def add_arguments(self, parser):
        parser.add_argument('--vectors', required=True,
                            help='Префикс пары файлов (<...>.f32, '
                                 '<...>.meta.json).')
        parser.add_argument('--apply', action='store_true',
                            help='Действительно записать. Без него команда '
                                 'только печатает план.')
        parser.add_argument('--state', default=str(STATE_PATH))
        parser.add_argument(
            '--skip-build-check', action='store_true',
            help='⚠️ Пропустить требование пройденной сверки билда. Только '
                 'для тестов конвейера на подставных векторах — на боевых '
                 'данных это ровно та ошибка, ради которой сверка заведена.')

    def handle(self, *args, **options):
        матрица, meta = load_vectors(options['vectors'])

        # ── 1. Спецификация и версия ──────────────────────────────────
        if meta.get('spec') != ACTIVE_SPEC_NAME:
            raise CommandError(
                'Векторы посчитаны по спецификации «%s», а активна «%s». '
                'Сначала переключите ACTIVE_SPEC_NAME в '
                'problems/embedding_config.py — иначе корпус и запрос '
                'разъедутся молча.' % (meta.get('spec'), ACTIVE_SPEC_NAME))
        if meta.get('version') != EMBEDDING_FORMULA_VERSION:
            raise CommandError(
                'Версия формулы в файле %r, активная %d.'
                % (meta.get('version'), EMBEDDING_FORMULA_VERSION))
        if meta.get('sample'):
            raise CommandError(
                'Это файл ВЫБОРКИ (gpu_encode --sample), а не полный прогон. '
                'Ввозить его значит стереть векторы у всех остальных задач.')
        spec = SPECS[ACTIVE_SPEC_NAME]

        # ── 2. Числа ──────────────────────────────────────────────────
        if матрица.shape[1] != EMBEDDING_DIM:
            raise CommandError('Размерность %d, ожидалась %d.'
                               % (матрица.shape[1], EMBEDDING_DIM))
        if not np.isfinite(матрица).all():
            raise CommandError('В файле есть NaN или бесконечность.')
        нормы = np.linalg.norm(матрица, axis=1)
        плохие = np.where((нормы < NORM_MIN) | (нормы > NORM_MAX))[0]
        if плохие.size:
            raise CommandError(
                'У %d векторов норма вне [%.1f, %.1f] — например задачи %s. '
                'Это не «немного не единица», это мусор.'
                % (плохие.size, NORM_MIN, NORM_MAX,
                   [meta['ids'][i] for i in плохие[:10]]))

        # ── 3. Сверка билда ───────────────────────────────────────────
        if not options['skip_build_check']:
            self._require_build_check(options['state'], spec)

        # ── 4. Хеши пересчитываются здесь и сейчас ────────────────────
        ids = list(meta['ids'])
        хеши = dict(zip(ids, meta['hashes']))
        место = {pid: i for i, pid in enumerate(ids)}

        к_записи, разошлись = [], []
        нашлось = set()
        for начало in range(0, len(ids), ID_CHUNK):
            порция_ids = ids[начало:начало + ID_CHUNK]
            задачи = (Problem.objects.filter(pk__in=порция_ids)
                      .prefetch_related(*PREFETCH))
            for задача in задачи.iterator(chunk_size=BATCH):
                нашлось.add(задача.id)
                текст = build_text(задача, spec)
                если_хеш = text_hash(текст)
                if если_хеш != хеши.get(задача.id):
                    разошлись.append(задача.id)
                    continue
                к_записи.append((задача.id, если_хеш))
        пропало = [i for i in ids if i not in нашлось]

        self.stdout.write('Ввоз векторов: спецификация «%s» (версия %d)'
                          % (spec.name, spec.version))
        self.stdout.write('   строк в файле: %d' % len(ids))
        self.stdout.write('   к записи: %d' % len(к_записи))
        self.stdout.write('   пропущено, текст изменился после вывоза: %d %s'
                          % (len(разошлись), разошлись[:20]))
        self.stdout.write('   нет в банке вовсе (удалены после вывоза): %d %s'
                          % (len(пропало), пропало[:20]))

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                'Это план. Записи не было — добавьте --apply.'))
            return None
        if not к_записи:
            raise CommandError('Записывать нечего: ни один хеш не сошёлся.')

        # ⚠️ Свип по ТЕКСТАМ, не по всему PROTECTED_FIELDS: `embedding`
        # входит в полный список, а записывать его — и есть работа этой
        # команды. Сторож, который краснеет всегда, перестают читать.
        отпечаток_до = protected_fingerprint(Problem.objects.all(),
                                             TEXT_PROTECTED_FIELDS)
        сейчас = timezone.now()
        записано = 0
        # ⚠️ ОДНА транзакция на весь ввоз, не на батч. Обрыв процесса между
        # батчами при транзакции на каждые 500 задач оставил бы банк в смеси
        # старой и новой формулы — а это не поймает ни один инвариант, поиск
        # просто станет молча хуже. Разбивка на BATCH внутри — только чтобы
        # не собирать все объекты в память разом, коммит один на всё.
        with transaction.atomic():
            for начало in range(0, len(к_записи), BATCH):
                кусок = к_записи[начало:начало + BATCH]
                for pid, хеш in кусок:
                    вектор = матрица[место[pid]]
                    Problem.objects.filter(pk=pid).update(
                        embedding=вектор.tobytes(order='C'),
                        embedding_version=spec.version,
                        embedding_model_build=EMBEDDING_MODEL_BUILD,
                        embedding_source_hash=хеш,
                        embedding_built_at=сейчас,
                    )
                    записано += 1
                self.stdout.write('   записано %d/%d' % (записано, len(к_записи)))

            отпечаток_после = protected_fingerprint(Problem.objects.all(),
                                                    TEXT_PROTECTED_FIELDS)
            if отпечаток_до != отпечаток_после:
                raise CommandError(
                    'СВИП-ДЕТЕКТОР: тексты задач изменились во время ввоза '
                    '(%s → %s). Откат целиком — вся транзакция отменена.'
                    % (отпечаток_до, отпечаток_после))

        self.stdout.write(self.style.SUCCESS(
            'Записано %d векторов. Свип-детектор: расхождений 0.' % записано))
        self.stdout.write(self.style.WARNING(
            'Дальше по ранбуку: перелить cache_similar (иначе блок «Похожие '
            'задачи» останется от старой формулы) и перекалибровать порог '
            '0,55 — отпечатки стали другими.'))
        return None

    def _require_build_check(self, path, spec):
        path = Path(path)
        if not path.exists():
            raise CommandError(
                'Нет %s — сверка билда не проводилась. Сначала '
                '`manage.py embeddings_check_build --vectors …`: без неё '
                'нельзя утверждать, что видеокарта считает так же, как '
                'CPU-контейнер прода.' % path)
        состояние = json.loads(path.read_text(encoding='utf-8'))
        if not состояние.get('build_check_passed'):
            raise CommandError('Сверка билда не пройдена (build_check_passed '
                               'ложно в %s).' % path)
        сверка = состояние.get('build_check') or {}
        if сверка.get('spec') != spec.name:
            raise CommandError(
                'Сверка билда проводилась на спецификации «%s», а ввозится '
                '«%s». Пройдите сверку на том файле, который ввозите.'
                % (сверка.get('spec'), spec.name))
        self.stdout.write(
            '   сверка билда: пройдена на «%s», минимум %.7f, медиана %.7f'
            % (сверка.get('spec'), сверка.get('min_cosine', 0),
               сверка.get('median_cosine', 0)))
