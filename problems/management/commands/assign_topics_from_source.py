u"""
assign_topics_from_source — проставить `Problem.topics` по разметке САМОГО
источника, без модели и без эвристик.

⚠️ ПИШЕТ ТОЛЬКО `topics` (M2M). Тексты задачи (`statement`, `answer`,
`solution`) не трогает вовсе — это запрет P0 корневого CLAUDE.md.

⚠️ ДОБАВЛЯЕТ, А НЕ ЗАМЕНЯЕТ. Если у задачи уже есть темы, поставленные
человеком или прежним переносом, они остаются: источник знает про свою
разметку, но не про чужую.

Сегодня умеет один источник — **SolveHub**. У него в сыром JSON есть
`tagList`, а в справочнике `tags.json` у каждого тега стоит `is_topic`.
Связь с банком — через `SourceReference.problem_number`, куда импортёр
положил хеш задачи SolveHub.

У остальных источников тем в сырье нет: у Сборника АА в `note` лежит
ИСХОДНАЯ ОЛИМПИАДА («Заключительный этап ВОШ 2001»), у ВсОШ — цена вопроса
в баллах. Ни то, ни другое темой не является, и выдумывать из этого тему
нельзя.

Запуск:
    manage.py assign_topics_from_source --source solvehub            # превью
    manage.py assign_topics_from_source --source solvehub --confirm  # запись
    manage.py assign_topics_from_source --source solvehub --revert   # откат

Откат идёт по журналу, который пишется при записи
(`reports/topics/assign_<источник>_<n>.json`): снимаются РОВНО те связи,
которые поставил этот прогон, и ничего больше.
"""
import io
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.models import Problem, Source, Topic
from problems.management.commands.apply_topic_mapping import CANONICAL

REPORT_DIR = os.path.join('reports', 'topics')
DEFAULT_RAW = os.path.join('C:/', 'Users', 'shipu', 'weconomics-data',
                           'solvehub')

# ---------------------------------------------------------------------------
# Таблица соответствий: тема SolveHub -> каноническая тема банка
# ---------------------------------------------------------------------------
#
# Составлена вручную по справочнику tags.json (36 тем) и списку CANONICAL
# (23 темы). Ключ — id тега SolveHub, значение — каноническое имя.
#
# ⚠️ ЧЕТЫРЕ ТЕГА НАМЕРЕННО НЕ СОПОСТАВЛЕНЫ. «Микроэкономика» (2 884 задачи),
# «Макроэкономика» (493), «Рыночные структуры» (980) и «Бизнес» (46) — это
# РАЗДЕЛЫ дерева, а не темы: у них есть дети, и сами они означают «где-то
# здесь». Поставить их темой значит записать в банк «тема: микроэкономика»
# — это не тема, это половина курса.
SOLVEHUB_TO_CANONICAL = {
    4: u'Математика и оптимизация',
    5: u'Альтернативные издержки и КПВ',
    6: u'Международная торговля',        # КТВ — кривая ТОРГОВЫХ возможностей
    7: u'Теория потребителя и полезность',
    8: u'Эластичность',
    9: u'Теория фирмы: производство и издержки',
    10: u'Спрос и предложение',
    11: u'Рынок труда',                  # «рынки факторов производства»
    12: u'Вмешательство государства',
    14: u'Олигополия и теория игр',
    15: u'Олигополия и теория игр',
    16: u'Олигополия и теория игр',      # Курно
    17: u'Олигополия и теория игр',      # Штакельберг
    18: u'Олигополия и теория игр',      # Бертран
    19: u'Олигополия и теория игр',      # Хотелинг
    74: u'Олигополия и теория игр',      # Форхаймер
    20: u'Вмешательство государства',    # общественные товары и экстерналии
    21: u'Неравенство доходов',
    22: u'Международная торговля',
    3: u'Финансы и финансовые инструменты',
    23: u'Финансы и финансовые инструменты',   # фондовый рынок
    24: u'Инфляция и безработица',
    25: u'Инфляция и безработица',
    26: u'Совокупный спрос и совокупное предложение',
    27: u'Фискальная политика',
    28: u'Монетарная политика',
    29: u'Международная торговля',       # открытая экономика
    30: u'Совокупный спрос и совокупное предложение',   # IS-LM-BP
    31: u'ВВП и национальные счета',
    44: u'ВВП и национальные счета',     # модель кругооборота
    33: u'Монополия и ценовая дискриминация',
    36: u'Теория фирмы: производство и издержки',
}

# Разделы дерева: тегами они есть, темами не становятся.
SOLVEHUB_SECTIONS = {1: u'Макроэкономика', 2: u'Микроэкономика',
                     13: u'Рыночные структуры', 67: u'Бизнес'}

SOURCES = {
    'solvehub': {
        'name_prefix': 'SolveHub',
        'mapping': SOLVEHUB_TO_CANONICAL,
        'sections': SOLVEHUB_SECTIONS,
    },
}


def load_solvehub_tags(raw_dir):
    u"""hash задачи -> [канонические темы] по tagList и tags.json."""
    tags_path = os.path.join(raw_dir, 'tags.json')
    if not os.path.exists(tags_path):
        raise CommandError(u'нет справочника тегов: %s' % tags_path)
    with io.open(tags_path, encoding='utf-8') as fh:
        raw = json.load(fh)
    is_topic = {t['id']: bool(t.get('is_topic')) for t in raw['tags']}
    names = {t['id']: t['name'] for t in raw['tags']}

    out, seen_tag = {}, {}
    problems_dir = os.path.join(raw_dir, 'problems')
    for fname in sorted(os.listdir(problems_dir)):
        if not fname.endswith('.json'):
            continue
        with io.open(os.path.join(problems_dir, fname), encoding='utf-8') as fh:
            d = json.load(fh)
        raw_list = d.get('tagList') or '[]'
        try:
            ids = json.loads(raw_list) if isinstance(raw_list, str) \
                else list(raw_list)
        except ValueError:
            ids = []
        ids = [i for i in ids if is_topic.get(i)]
        for i in ids:
            seen_tag[i] = names.get(i, str(i))
        out[d['hash']] = ids
    return out, seen_tag


class Command(BaseCommand):
    help = (u'Проставляет Problem.topics по разметке самого источника '
            u'(без превью-флага — сухой прогон).')

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True,
                            choices=sorted(SOURCES),
                            help=u'ключ источника (пока только solvehub)')
        parser.add_argument('--raw-dir', default=DEFAULT_RAW,
                            help=u'каталог сырья источника')
        parser.add_argument('--confirm', action='store_true',
                            help=u'записать в базу (иначе только превью)')
        parser.add_argument('--revert', default='',
                            help=u'путь к журналу прогона: снять его связи')
        parser.add_argument('--out', default='',
                            help=u'куда положить HTML-превью')
        parser.add_argument('--examples', type=int, default=20,
                            help=u'сколько примеров на тему в превью')

    # -- откат ------------------------------------------------------------
    def do_revert(self, path):
        with io.open(path, encoding='utf-8') as fh:
            log = json.load(fh)
        topics = {t.name: t for t in Topic.objects.filter(
            name__in={n for pairs in log['added'].values() for n in pairs})}
        undone = 0
        with transaction.atomic():
            for pid, names in log['added'].items():
                problem = Problem.objects.filter(pk=int(pid)).first()
                if not problem:
                    continue
                for name in names:
                    topic = topics.get(name)
                    if topic:
                        problem.topics.remove(topic)
                        undone += 1
        self.stdout.write(self.style.SUCCESS(
            u'Откат: снято связей %d по журналу %s' % (undone, path)))

    # -- основной ход -----------------------------------------------------
    def handle(self, *args, **options):
        if options['revert']:
            return self.do_revert(options['revert'])

        key = options['source']
        spec = SOURCES[key]
        by_hash, tag_names = load_solvehub_tags(options['raw_dir'])

        source = Source.objects.filter(
            name__startswith=spec['name_prefix']).first()
        if source is None:
            raise CommandError(u'источник не найден: %s'
                               % spec['name_prefix'])

        rows = (Problem.objects
                .filter(source_references__source=source)
                .distinct()
                .prefetch_related('topics', 'source_references')
                .order_by('id'))

        plan = {}            # problem_id -> [новые темы]
        stats = {'всего задач источника': 0, 'нет хеша': 0,
                 'хеша нет в сырье': 0, 'тем в сырье нет': 0,
                 'только разделы': 0, 'тема уже стоит': 0,
                 'получат тему': 0}
        per_topic = {}
        unmapped = {}
        for problem in rows.iterator(chunk_size=300):
            stats['всего задач источника'] += 1
            refs = [r for r in problem.source_references.all()
                    if r.source_id == source.id]
            h = (refs[0].problem_number or '').strip() if refs else ''
            if not h:
                stats['нет хеша'] += 1
                continue
            if h not in by_hash:
                stats['хеша нет в сырье'] += 1
                continue
            ids = by_hash[h]
            if not ids:
                stats['тем в сырье нет'] += 1
                continue
            names = []
            only_sections = True
            for i in ids:
                if i in spec['sections']:
                    continue
                only_sections = False
                canon = spec['mapping'].get(i)
                if canon is None:
                    unmapped[i] = tag_names.get(i, str(i))
                    continue
                if canon not in names:
                    names.append(canon)
            if only_sections:
                stats['только разделы'] += 1
                continue
            have = {t.name for t in problem.topics.all()}
            fresh = [n for n in names if n not in have]
            if not fresh:
                stats['тема уже стоит'] += 1
                continue
            plan[problem.id] = fresh
            stats['получат тему'] += 1
            for n in fresh:
                per_topic.setdefault(n, []).append(problem)

        for name, value in stats.items():
            self.stdout.write(u'  %-24s %6d' % (name, value))
        if unmapped:
            self.stdout.write(self.style.WARNING(
                u'  теги без соответствия: %s'
                % ', '.join(u'#%d %s' % (i, n)
                            for i, n in sorted(unmapped.items()))))
        bad = sorted({n for names in plan.values() for n in names}
                     - set(CANONICAL))
        if bad:
            raise CommandError(u'неканонические темы в таблице: %s' % bad)

        out = options['out'] or os.path.join(
            'reports', 'game', 'pool_topics_from_source.html')
        self.write_preview(out, key, spec, tag_names, stats, per_topic,
                           options['examples'])
        self.stdout.write(u'Превью: %s' % out)

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                u'Сухой прогон: в базу НЕ записано. Добавьте --confirm.'))
            return

        os.makedirs(REPORT_DIR, exist_ok=True)
        topics = {t.name: t for t in Topic.objects.filter(
            name__in={n for names in plan.values() for n in names})}
        missing = sorted({n for names in plan.values() for n in names}
                         - set(topics))
        if missing:
            raise CommandError(u'нет таких тем в базе: %s' % missing)

        added = 0
        with transaction.atomic():
            for pid, names in plan.items():
                problem = Problem.objects.get(pk=pid)
                for name in names:
                    problem.topics.add(topics[name])
                    added += 1
        log_path = os.path.join(REPORT_DIR, 'assign_%s_%d.json' % (key, added))
        with io.open(log_path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(
                {'source': key, 'added': {str(k): v for k, v in plan.items()}},
                ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS(
            u'Записано связей: %d у %d задач. Журнал отката: %s'
            % (added, len(plan), log_path)))

    # -- превью -----------------------------------------------------------
    def write_preview(self, path, key, spec, tag_names, stats, per_topic,
                      examples):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

        def esc(text):
            return (text or '').replace('&', '&amp;').replace(
                '<', '&lt;').replace('>', '&gt;')

        parts = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
                 '<title>Темы пула из источника</title>',
                 '<style>body{font:15px/1.55 system-ui,sans-serif;margin:0 '
                 'auto;max-width:1000px;padding:24px;color:#1c1c1c}'
                 'h1{font-size:24px}h2{font-size:19px;margin-top:32px}'
                 'table{border-collapse:collapse;width:100%;margin:12px 0}'
                 'td,th{border:1px solid #ddd;padding:6px 9px;'
                 'vertical-align:top;font-size:14px}'
                 'th{background:#f4f4f4;text-align:left}'
                 '.num{text-align:right;white-space:nowrap}'
                 '.ex{color:#444;font-size:13px}'
                 '.warn{background:#fff6e5}</style><main>']
        parts.append(u'<h1>Темы игрового пула из разметки источника: %s</h1>'
                     % esc(key))
        parts.append(u'<p>Ничего не записано: это превью. Пишется только '
                     u'<code>Problem.topics</code>; тексты задач не '
                     u'трогаются.</p>')

        parts.append(u'<h2>Счёт</h2><table><tr><th>что</th>'
                     u'<th class="num">сколько</th></tr>')
        for name, value in stats.items():
            parts.append(u'<tr><td>%s</td><td class="num">%d</td></tr>'
                         % (esc(name), value))
        parts.append('</table>')

        parts.append(u'<h2>Таблица соответствий</h2>')
        parts.append(u'<table><tr><th>тег источника</th>'
                     u'<th>каноническая тема банка</th></tr>')
        for tid, canon in sorted(spec['mapping'].items(),
                                 key=lambda kv: kv[1]):
            parts.append(u'<tr><td>#%d %s</td><td>%s</td></tr>'
                         % (tid, esc(tag_names.get(tid, '')), esc(canon)))
        for tid, name in sorted(spec['sections'].items()):
            parts.append(u'<tr class="warn"><td>#%d %s</td>'
                         u'<td><i>раздел дерева, темой не становится</i></td>'
                         u'</tr>' % (tid, esc(name)))
        parts.append('</table>')

        parts.append(u'<h2>Примеры: до %d задач на тему</h2>' % examples)
        for name in sorted(per_topic):
            items = per_topic[name]
            parts.append(u'<h3>%s <span class="num">(%d задач)</span></h3>'
                         % (esc(name), len(items)))
            parts.append('<table>')
            for problem in items[:examples]:
                parts.append(
                    u'<tr><td class="num">#%d</td><td class="ex">%s</td></tr>'
                    % (problem.id, esc((problem.statement or '')[:260])))
            parts.append('</table>')
        parts.append('</main></html>')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(parts))
