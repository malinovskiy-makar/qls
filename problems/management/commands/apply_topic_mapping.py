# -*- coding: utf-8 -*-
"""
Этап А3 — единая таксономия тем.

Сводит ~840 фрагментированных тем (названия листков/занятий из разных курсов)
к 21 канонической теме.

Запуск:
  ./venv/bin/python manage.py apply_topic_mapping --dry-run     # только статистика, ничего не меняем
  ./venv/bin/python manage.py apply_topic_mapping               # боевой прогон: добавляет канонические темы
  ./venv/bin/python manage.py apply_topic_mapping --remove-old  # ещё и снимает старые темы с задач
  ./venv/bin/python manage.py apply_topic_mapping --show-mapping # печатает весь словарь OLD_TO_NEW

Как устроено:
  - CANONICAL — список из 21 канонической темы (создаются, если их ещё нет).
  - classify(name) — относит старое название темы к одной из 21 (или к None).
    Логика «кто раньше в названии — тот и тема»: для каждой канонической темы
    ищем самое раннее вхождение её ключевых слов в название; побеждает тема с
    самым ранним вхождением. Это даёт «по головному слову»: «СК и монополия» →
    Совершенная конкуренция, «Монополия и СК» → Монополия.
  - OLD_TO_NEW — словарь {точное_название_старой_темы: каноническое_или_None},
    строится из базы функцией build_old_to_new(): ключи гарантированно совпадают
    с реальными названиями тем (никаких опечаток).
"""

import re
from django.core.management.base import BaseCommand
from django.db import transaction
from problems.models import Problem, Topic


# ---------------------------------------------------------------------------
# 21 каноническая тема
# ---------------------------------------------------------------------------

KPV    = 'Альтернативные издержки и КПВ'
SD     = 'Спрос и предложение'
EL     = 'Эластичность'
CONS   = 'Теория потребителя и полезность'
FIRM   = 'Теория фирмы: производство и издержки'
SK     = 'Совершенная конкуренция'
MON    = 'Монополия и ценовая дискриминация'
OLIG   = 'Олигополия и теория игр'
GOV    = 'Вмешательство государства'
TRADE  = 'Международная торговля'
LABOR  = 'Рынок труда'
INEQ   = 'Неравенство доходов'
GDP    = 'ВВП и национальные счета'
INFL   = 'Инфляция и безработица'
FISC   = 'Фискальная политика'
MONET  = 'Монетарная политика'
GROWTH = 'Экономический рост и циклы'
FIN    = 'Финансы и финансовые инструменты'
ECNM   = 'Эконометрика и анализ данных'
BEH    = 'Поведенческая экономика'
MATH   = 'Математика и оптимизация'

# Порядок = порядок отображения в каталоге (микро → макро → прочее)
CANONICAL = [
    KPV, SD, EL, CONS, FIRM, SK, MON, OLIG, GOV, TRADE, LABOR, INEQ,
    GDP, INFL, FISC, MONET, GROWTH,
    FIN, ECNM, BEH, MATH,
]

# Приоритет при «ничьей» (два ключа на одной позиции): раньше в списке — важнее.
PRIORITY = [
    OLIG, MON, SK, EL, CONS, KPV, TRADE, LABOR, INEQ,
    GDP, INFL, FISC, MONET, GROWTH, ECNM, BEH, FIN,
    FIRM, SD, GOV, MATH,
]

# ---------------------------------------------------------------------------
# Ключевые слова (в нижнем регистре). Строка = подстрока; кортеж ('re', pat) =
# регулярное выражение (для коротких/неоднозначных меток вроде «СК»).
# ---------------------------------------------------------------------------

KEYWORDS = {
    KPV: [
        'кпв', 'ктв', 'кривая производ', 'кривые производ',
        'производственных возмож', 'торговых возмож',
        'кривая торгов', 'кривые торгов',
        'альтернативн', 'сравнительн', 'выгоды обмена', 'экономика обмена',
    ],
    SD: [
        'спрос и предлож', 'спроса и предлож', 'спросе и предлож',
        'рыночное равновес', 'рыночного равновес', 'рынок (спрос',
        'закон спроса', 'что такое спрос', 'что такое предлож',
        'модель спроса', 'рынки', 'микс-рынок',
    ],
    EL: ['эластичн'],
    CONS: [
        'полезност', 'потребител', 'межвременн', 'неопредел',
        'отношение к риску',
    ],
    FIRM: [
        'производст', 'издержк', 'теория фирмы', 'фирма', 'фирмы', 'фирм',
        'отдача от масштаба', 'выручка', 'прибыл', 'завод',
    ],
    SK: ['совершенн', ('re', r'(?<![а-яёa-z])ск(?![а-яёa-z])')],
    MON: [
        'монопол', 'монопсон', 'дискриминац', 'скрининг', 'двухчастн',
        'лояльн', 'власть на рынке', 'рыночная власть',
    ],
    OLIG: [
        'олигопол', 'теория игр', 'теории игр', 'теорию игр', 'тигр',
        'курно', 'штакельберг', 'грим', 'смешанные стратег',
        'последовательные игр', 'повторяющиеся игр', 'взаимодейств',
        'матчинг', 'мэтчинг', 'хоттелинг', 'хотеллинг', 'модели io',
    ],
    GOV: [
        'вмешательств', 'налог', 'экстернал', 'внешние эффект',
        'общественн', 'благосостоян', 'излишк', 'провалы рынка', 'субсид',
    ],
    TRADE: [
        'международн', 'торговл', 'межторг', 'межнар', 'валют',
        'обменный курс', 'обменн', 'открытая эконом', 'открытой эконом',
        'торговых сюжет',
    ],
    LABOR: ['рынок труда', 'рынка труда', 'рынке труда', 'труда', 'профсоюз'],
    INEQ: ['неравенств', 'джини', 'джинни', 'лоренц', 'распределени доход'],
    GDP: [
        'ввп', 'внп', 'национальн', 'кругооборот', 'круговорот',
        'индексы цен', 'индекс цен', 'дефлятор', 'система национальн',
    ],
    INFL: ['инфляц', 'безработиц', 'оукен'],
    FISC: ['фискальн', 'бюджет', 'мультипликац'],
    MONET: [
        'монетарн', 'денежн', 'деньги', 'банковск', 'банк',
        'кредитно-денежн', 'денежно-кредитн', 'is-lm',
    ],
    GROWTH: [
        'экономический рост', 'экономического рост', 'ad-as',
        'совокупный спрос', 'модель солоу', 'солоу', 'цикл', 'кризис',
        'долгосрочная макро', 'lr макро', 'sr макро',
    ],
    FIN: [
        'финан', 'фининстр', 'финграм', 'дериватив', 'npv', 'ценных бумаг',
        'ценные бумаг', 'облигац', 'инвестиц', 'кредит', 'депозит',
        'брокер', 'иис', 'страхов', 'пенсионн', 'технический анализ',
        'фундаментальный анализ', 'доходность', 'мошенничеств',
    ],
    ECNM: ['эконометрик', 'анализ данных', 'анализу данных', 'анализа данных',
           'регресс'],
    BEH: ['поведенческ'],
    MATH: [
        'математик', 'оптимизац', 'производн', 'дифференц', 'дифф',
        'формализац', 'вероятн', 'дискретн', 'линейн', 'квадратичн',
        'парабол', 'график', 'метод нулевого случая',
    ],
}

# Точечные исключения (каламбуры/особые случаи), которые правило не ловит.
OVERRIDES = {
    'СКолько можно уже?': SK,
    'КэПэВэ -- это моя жизнь': KPV,
    'Качи по АД, решалка': ECNM,
}


def _kw_index(name_l, kw):
    """Позиция первого вхождения ключа в название (или -1, если нет)."""
    if isinstance(kw, tuple):          # ('re', pattern)
        m = re.search(kw[1], name_l)
        return m.start() if m else -1
    return name_l.find(kw)


def classify(name):
    """Относит название старой темы к одной из 21 канонической (или None)."""
    if name in OVERRIDES:
        return OVERRIDES[name]

    name_l = name.lower()
    best_canon = None
    best_pos = None
    best_prio = None
    for canon, kws in KEYWORDS.items():
        pos = -1
        for kw in kws:
            i = _kw_index(name_l, kw)
            if i != -1 and (pos == -1 or i < pos):
                pos = i
        if pos == -1:
            continue
        prio = PRIORITY.index(canon)
        if best_pos is None or pos < best_pos or (pos == best_pos and prio < best_prio):
            best_canon, best_pos, best_prio = canon, pos, prio
    return best_canon


def build_old_to_new():
    """Строит словарь {точное_название_старой_темы: каноническое_или_None}.

    Ключи берутся прямо из базы — совпадают с реальными названиями тем.
    Канонические темы сами на себя (тождественно), чтобы повторный прогон
    был идемпотентным.
    """
    mapping = {}
    canon_set = set(CANONICAL)
    for name in Topic.objects.values_list('name', flat=True):
        if name in canon_set:
            mapping[name] = name        # каноническая тема → она же
        else:
            mapping[name] = classify(name)
    return mapping


# ---------------------------------------------------------------------------
# Создание/получение канонических тем
# ---------------------------------------------------------------------------

_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _make_slug(name):
    chars = [_TRANSLIT.get(c, c) for c in name.lower()]
    slug = re.sub(r'[^a-z0-9]+', '-', ''.join(chars)).strip('-')
    return slug[:110] or 'topic'


def ensure_canonical_topics(dry_run):
    """Возвращает {каноническое_название: Topic}. Создаёт недостающие."""
    result = {}
    for i, name in enumerate(CANONICAL):
        topic = Topic.objects.filter(name=name).first()
        if topic is None and not dry_run:
            base = _make_slug(name)
            slug = base
            c = 1
            while Topic.objects.filter(slug=slug).exists():
                slug = f'{base}-{c}'
                c += 1
            topic = Topic.objects.create(name=name, slug=slug, order=i)
        result[name] = topic
    return result


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Этап А3: свести старые темы к 21 канонической и проставить их задачам.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать статистику, ничего не менять.')
        parser.add_argument('--remove-old', action='store_true',
                            help='После маппинга снять с задач старые (неканонические) темы.')
        parser.add_argument('--show-mapping', action='store_true',
                            help='Напечатать весь словарь OLD_TO_NEW и выйти.')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        remove_old = opts['remove_old']

        old_to_new = build_old_to_new()

        if opts['show_mapping']:
            for old in sorted(old_to_new):
                self.stdout.write(f'{old!r}: {old_to_new[old]!r}')
            self.stdout.write(self.style.SUCCESS(f'\nВсего тем: {len(old_to_new)}'))
            return

        canon_set = set(CANONICAL)
        # Старые темы (без канонических), сгруппируем результат
        mapped_names   = {o: n for o, n in old_to_new.items()
                          if o not in canon_set and n is not None}
        unmapped_names = [o for o, n in old_to_new.items()
                          if o not in canon_set and n is None]

        # Сколько задач стоит за каждой неотмапленной темой — для топ-5
        unmapped_counts = (
            Topic.objects.filter(name__in=unmapped_names)
            .values_list('name', flat=True)
        )
        unmapped_with_n = []
        for t in Topic.objects.filter(name__in=unmapped_names):
            unmapped_with_n.append((t.problems.count(), t.name))
        unmapped_with_n.sort(reverse=True)

        # --- проход по задачам: считаем покрытие ---
        canon_topics = ensure_canonical_topics(dry_run)

        problems = Problem.objects.prefetch_related('topics').all()
        total = problems.count()
        will_get_canon = 0       # задачи, которым достанется хотя бы одна каноническая тема
        will_stay_bare = 0       # задачи, оставшиеся без канонической темы
        added_links = 0          # сколько связей (задача↔каноническая тема) добавим

        # для боевого прогона копим, что добавлять
        to_add = []              # (problem, [canonical Topic, ...])
        to_remove = []           # (problem, [old Topic, ...])

        for p in problems:
            cur_topics = list(p.topics.all())
            cur_names = {t.name for t in cur_topics}
            canon_for_p = set()
            for t in cur_topics:
                mapped = old_to_new.get(t.name)
                if mapped is not None:
                    canon_for_p.add(mapped)
            if canon_for_p:
                will_get_canon += 1
                # какие канонические темы реально новые (ещё не стоят на задаче)
                new_canon_names = [c for c in canon_for_p if c not in cur_names]
                added_links += len(new_canon_names)
                if new_canon_names and not dry_run:
                    to_add.append((p, [canon_topics[c] for c in new_canon_names]))
            else:
                will_stay_bare += 1

            if remove_old:
                old_links = [t for t in cur_topics if t.name not in canon_set]
                if old_links and not dry_run:
                    to_remove.append((p, old_links))

        # --- статистика ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Маппинг тем (Этап А3) ==='))
        self.stdout.write(f'Канонических тем:            {len(CANONICAL)}')
        self.stdout.write(f'Всего старых тем в базе:     {len(old_to_new)}')
        self.stdout.write(f'  из них отмаплено:          {len(mapped_names)}')
        self.stdout.write(f'  не попало в маппинг:       {len(unmapped_names)}')
        self.stdout.write('')
        self.stdout.write(f'Всего задач:                 {total}')
        self.stdout.write(self.style.SUCCESS(
            f'  получат каноническую тему: {will_get_canon}'))
        self.stdout.write(self.style.WARNING(
            f'  останутся без канонической:{will_stay_bare}'))
        self.stdout.write(f'Новых связей задача↔тема:     {added_links}')
        self.stdout.write('')
        self.stdout.write('Топ-5 старых тем БЕЗ маппинга (по числу задач):')
        for n, name in unmapped_with_n[:5]:
            self.stdout.write(f'  {n:>5}  {name}')

        if dry_run:
            self.stdout.write(self.style.NOTICE(
                '\n[dry-run] Ничего не записано. Убери --dry-run для боевого прогона.'))
            return

        # --- запись ---
        with transaction.atomic():
            for p, topics in to_add:
                p.topics.add(*topics)
            if remove_old:
                for p, topics in to_remove:
                    p.topics.remove(*topics)

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово. Добавлено связей: {added_links}.'))
        if remove_old:
            removed = sum(len(t) for _, t in to_remove)
            self.stdout.write(self.style.SUCCESS(
                f'Снято старых связей: {removed}.'))
        else:
            self.stdout.write(
                'Старые темы оставлены (флаг --remove-old не задан).')
