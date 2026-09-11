# -*- coding: utf-8 -*-
"""`embeddings_export_texts` — вывоз текстов отпечатка на арендованную видеокарту.

База на арендованный сервер НЕ ЕДЕТ: туда едут только тексты отпечатка,
обратно — векторы. Так ничего не расходится, а откат — это просто «не
ввозить». Команда ТОЛЬКО ЧИТАЕТ: ни одного `save()`, ни одного `update()`.

Формат файла — JSONL. Первая строка — шапка (имя спецификации, версия,
бюджеты, порядок блоков, модель, билд, `max_seq_length`, число строк, дата,
разрез банка по `enrichment_source`), дальше по строке на задачу:
`{"id": …, "hash": md5 текста, "text": …}`.

⚠️ **Гейт на входе — механический, а не «не забудь».** Смысл всей затеи в
том, чтобы векторы считались по банку ПОСЛЕ допрогона, а не до. Порядок фаз
этого не гарантирует — гарантирует проверка. Команда считает
`enrichment_source = 'run1' AND content_status <> 'junk'` и отказывается
работать, пока это не ноль. У задач-`junk` метка `run1` остаётся законно:
они в манифест допрогона не входили.

Разрез по `enrichment_source` пишется в шапку целиком — тогда даже спустя
неделю по одному файлу видно, на каком состоянии банка он собран.

Запуск:
    manage.py embeddings_export_texts --spec v2 --out reports/formula_v2/texts_v2.jsonl
    manage.py embeddings_export_texts --spec v1 --out … --scope prod
    manage.py embeddings_export_texts --self-check 2000
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.embedding_config import (
    EMBEDDING_MAX_SEQ_LENGTH, EMBEDDING_MODEL_BUILD, EMBEDDING_MODEL_NAME,
)
from problems.embedding_formula import PREFETCH, SPECS, build_text
from problems.models import Problem

#: Сколько задач держим в памяти одновременно. Корпус целиком не помещается:
#: 41 302 задачи — это 338 МБ одних только байтов изображений плюс тексты и
#: 66 тысяч подпунктов.
CHUNK = 500


def text_hash(text):
    """MD5 текста, который реально уйдёт в модель. Тот же ключ, что у
    `build_embeddings.embedding_source_hash` — ввоз векторов пересчитывает
    его заново и сверяет: разошлось значит поля правились после вывоза."""
    return hashlib.md5(text.encode('utf-8'), usedforsecurity=False).hexdigest()


def export_queryset(scope):
    """Кого вывозим.

    ⚠️ НЕ `catalog.semantic.index_queryset`: тот требует `embedding__isnull
    = False`, а мы как раз идём считать векторы тем, у кого их нет. Срез
    `prod` повторяет остальные четыре признака видимости один в один.
    """
    if scope == 'all':
        return Problem.objects.all().order_by('id')
    if scope == 'prod':
        return Problem.objects.filter(
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            hidden_pending_review=False,
            content_status=Problem.ContentStatus.OK,
        ).order_by('id')
    raise CommandError('Неизвестный срез: %r. Допустимы «all» и «prod».' % scope)


def run1_leftovers():
    """id задач, всё ещё сидящих на данных слабого первого прогона.

    Список, а не число: когда их единицы, человеку нужно видеть, кто именно,
    — иначе гейт превращается в тупик. У задач-`junk` метка `run1` остаётся
    законно, они в манифест допрогона не входили.
    """
    return sorted(Problem.objects.filter(enrichment_source='run1')
                  .exclude(content_status='junk')
                  .values_list('id', flat=True))


class Command(BaseCommand):
    help = ('Вывезти тексты отпечатка по спецификации формулы — вход для '
            'кодирования на арендованной видеокарте. Только читает.')

    def add_arguments(self, parser):
        parser.add_argument('--spec', default=None,
                            help='Имя спецификации формулы (%s).'
                                 % ', '.join(sorted(SPECS)))
        parser.add_argument('--out', default=None, help='Куда писать JSONL.')
        parser.add_argument('--scope', default='all', choices=['all', 'prod'],
                            help='Срез банка (по умолчанию «all»: срез '
                                 'каталога сейчас всё равно поедет).')
        parser.add_argument(
            '--self-check', type=int, default=0, metavar='N',
            help='Не вывозить, а проверить на N РЕАЛЬНЫХ задачах банка, что '
                 '`build_text(p, SPECS["v1"])` совпадает с `problem_to_text(p)` '
                 'СИМВОЛ В СИМВОЛ. Юнит-тест гоняется на пустой тестовой базе '
                 'и настоящих задач не видит; §3.2 задания требует выборку '
                 'не меньше 2 000.')
        parser.add_argument(
            '--allow-run1-leftovers', action='store_true',
            help='⚠️ Снять гейт допрогона. Нужен ровно для одного случая — '
                 'вывоз ради проверки конвейера, когда векторы заведомо не '
                 'поедут в банк. Для боевого вывоза не применять: смысл '
                 'аренды в том, чтобы считать по банку ПОСЛЕ допрогона.')

    def handle(self, *args, **options):
        if options['self_check']:
            return self._self_check(options['self_check'])

        if not options['spec'] or not options['out']:
            raise CommandError('--spec и --out обязательны (или --self-check N).')
        try:
            spec = SPECS[options['spec']]
        except KeyError:
            raise CommandError('Нет такой спецификации: %r. Есть: %s'
                               % (options['spec'], ', '.join(sorted(SPECS))))

        разрез = dict(Counter(
            Problem.objects.values_list('enrichment_source', flat=True)))
        осталось = run1_leftovers()
        if осталось and not options['allow_run1_leftovers']:
            raise CommandError(
                'ГЕЙТ ДОПРОГОНА: %d задач всё ещё на данных слабого первого '
                'прогона (enrichment_source = run1, content_status <> junk). '
                'Векторы обязаны считаться по банку ПОСЛЕ допрогона, иначе '
                'аренда оплатит устаревшие поля. Сначала фазы 1-2: '
                'glm_enrich_run --ids-file … --include-nonok, затем '
                'merge_enrichment_v2 --apply --source-tag run3.\n'
                '   id: %s\n'
                '   разрез enrichment_source: %s\n'
                'Если это единичные задачи, на которых прогон застрял по '
                'известной причине, — посмотрите их поимённо и запускайте с '
                '--allow-run1-leftovers, назвав причину в отчёте.'
                % (len(осталось), осталось[:50], разрез))

        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        qs = export_queryset(options['scope'])
        всего = qs.count()

        шапка = {
            'kind': 'embedding_texts',
            'spec': spec.name,
            'version': spec.version,
            'blocks': list(spec.blocks),
            'budgets': dict(spec.budgets),
            'options': sorted(spec.options),
            'model_name': EMBEDDING_MODEL_NAME,
            'model_build': EMBEDDING_MODEL_BUILD,
            'max_seq_length': EMBEDDING_MAX_SEQ_LENGTH,
            'scope': options['scope'],
            'rows': всего,
            'enrichment_source': разрез,
            'run1_leftovers': len(осталось),
            'run1_leftover_ids': осталось[:200],
            'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }

        длины, пустых, записано = [], 0, 0
        with out.open('w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(шапка, ensure_ascii=False) + '\n')
            for задача in qs.prefetch_related(*PREFETCH).iterator(chunk_size=CHUNK):
                текст = build_text(задача, spec)
                if not текст.strip():
                    пустых += 1
                длины.append(len(текст))
                fh.write(json.dumps(
                    {'id': задача.id, 'hash': text_hash(текст), 'text': текст},
                    ensure_ascii=False) + '\n')
                записано += 1

        if записано != всего:
            raise CommandError(
                'Записано %d строк, а в срезе %d — банк менялся во время '
                'вывоза. Файл негоден, повторите.' % (записано, всего))

        длины.sort()
        медиана = длины[len(длины) // 2] if длины else 0
        p90 = длины[int(len(длины) * 0.9)] if длины else 0
        self.stdout.write(self.style.SUCCESS(
            'Вывезено %d текстов по спецификации «%s» (версия %d) → %s'
            % (записано, spec.name, spec.version, out)))
        self.stdout.write('   срез: %s, блоков: %d'
                          % (options['scope'], len(spec.blocks)))
        self.stdout.write('   длина текста: медиана %d, p90 %d, максимум %d'
                          % (медиана, p90, длины[-1] if длины else 0))
        self.stdout.write('   пустых текстов: %d' % пустых)
        self.stdout.write('   enrichment_source: %s' % разрез)
        return None

    # ── самопроверка v1 на реальных задачах ───────────────────────────

    def _self_check(self, n):
        """§3.2: `v1` обязана воспроизводиться символ в символ.

        Выборка берётся по всему диапазону id, а не «первые N»: первые
        задачи банка — целиком легаси без подпунктов и без тегов, и такая
        проверка не проверила бы ничего.
        """
        from problems.management.commands.build_embeddings import problem_to_text

        всего = Problem.objects.count()
        шаг = max(1, всего // n)
        ids = list(Problem.objects.values_list('id', flat=True).order_by('id'))[::шаг][:n]

        расхождения, проверено = [], 0
        покрытие = Counter()
        for задача in (Problem.objects.filter(pk__in=ids)
                       .prefetch_related(*PREFETCH).iterator(chunk_size=CHUNK)):
            эталон = problem_to_text(задача)
            наш = build_text(задача, SPECS['v1'])
            проверено += 1
            покрытие['с подпунктами'] += bool(задача.parts.all())
            покрытие['без темы'] += not задача.topics.all()
            покрытие['без blurb'] += not (задача.ai_blurb or '').strip()
            покрытие['с пустым title'] += not (задача.title or '').strip()
            покрытие['с пустым условием'] += not (задача.statement or '').strip()
            if эталон != наш:
                расхождения.append(задача.id)

        self.stdout.write('Самопроверка v1 на реальных задачах банка:')
        self.stdout.write('   проверено: %d' % проверено)
        for имя, число in sorted(покрытие.items()):
            self.stdout.write('   %s: %d' % (имя, число))
        if расхождения:
            raise CommandError(
                'РАСХОЖДЕНИЕ v1 против problem_to_text у %d задач: %s. '
                'Сравнение v1 против v2 сейчас нечестное — это сравнение v2 '
                'с новой опечаткой.' % (len(расхождения), расхождения[:20]))
        self.stdout.write(self.style.SUCCESS(
            '   расхождений: 0 — v1 воспроизводится символ в символ.'))
        return None
