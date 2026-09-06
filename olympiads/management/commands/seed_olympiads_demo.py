"""Демонстрационные данные раздела «Олимпиады».

⚠️ ВСЁ ЗДЕСЬ — ВЫДУМКА. Ни одна дата, ни один балл и ни одна льгота в
этом файле не проверялись по источникам. Данные нужны ровно для одного:
увидеть, как раздел выглядит на экране до того, как начнётся сбор фактов.
Поэтому у каждой олимпиады стоит `is_placeholder=True`, а страницы рисуют
поверх плашку «Демонстрационные данные».

Наполнение намеренно НЕРОВНОЕ: у ВсОШ есть всё, у МОШ и Высшей пробы —
даты, у остальных тринадцати только скелет. Так и будет выглядеть раздел
ещё месяцами, и проверять надо именно это состояние, а не идеальное.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from olympiads.models import (
    FactUpdateProposal, Olympiad, OlympiadBenefit, OlympiadEvent,
    OlympiadLevelYear, OlympiadScore, OlympiadStage, OlympiadVariant,
    RegionalCoordinator, UniversityProgram,
)

YEAR = '2026/27'
ADMISSION_YEAR = 2026

# ── Олимпиады ───────────────────────────────────────────────────────────
# slug, полное имя, короткое, организатор, kind, группа, класс с, класс по,
# ранг, уровень 2026/27, командная, отбор онлайн, финал онлайн
OLYMPIADS = [
    ('vseros', 'Всероссийская олимпиада школьников', 'ВсОШ',
     'Министерство просвещения Российской Федерации',
     'vsosh', 'main', 9, 11, 100, None, False, False, False),
    ('mosh', 'Московская олимпиада школьников', 'МОШ',
     'Департамент образования Москвы, МЦНМО',
     'perechen', 'main', 8, 11, 90, 1, False, True, False),
    ('vp', 'Высшая проба по экономике', 'Высшая проба',
     'НИУ «Высшая школа экономики»',
     'perechen', 'main', 9, 11, 88, 1, False, True, False),
    ('spbgu', 'Олимпиада школьников СПбГУ по экономике', 'Олимпиада СПбГУ',
     'Санкт-Петербургский государственный университет',
     'perechen', 'main', 9, 11, 80, 1, False, True, False),
    ('lom', 'Олимпиада школьников «Ломоносов» по экономике', '«Ломоносов»',
     'МГУ имени М. В. Ломоносова',
     'perechen', 'main', 9, 11, 78, 1, False, True, False),
    ('pleh', 'Плехановская олимпиада школьников', 'Плехановская',
     'РЭУ имени Г. В. Плеханова',
     'perechen', 'main', 9, 11, 60, 2, False, True, False),
    ('kondrat', 'Олимпиада имени Н. Д. Кондратьева', 'Кондратьева',
     'Международный фонд Н. Д. Кондратьева',
     'perechen', 'main', 8, 11, 45, 3, False, True, False),
    ('ranepa', 'Олимпиада РАНХиГС по экономике', 'РАНХиГС',
     'Российская академия народного хозяйства и государственной службы',
     'perechen', 'main', 9, 11, 50, 2, False, True, False),
    ('mis', 'Миссия выполнима. Твоё призвание — финансист',
     'Миссия выполнима',
     'Финансовый университет при Правительстве РФ',
     'perechen', 'main', 9, 11, 55, 2, False, True, False),
    ('sb', 'Олимпиада «Сибириада. Шаг в мечту»', 'Сибириада',
     'Кемеровский государственный университет',
     'perechen', 'main', 5, 11, 30, 3, False, True, False),
    ('nes', 'Конкурс Российской экономической школы', 'Конкурс РЭШ',
     'Российская экономическая школа',
     'perechen', 'main', 9, 11, 40, 2, False, True, True),
    ('ieo', 'International Economics Olympiad', 'IEO',
     'International Economics Olympiad Committee',
     'international', 'main', 9, 11, 70, None, True, True, False),
    ('dano', 'Олимпиада DANO по анализу данных в экономике', 'DANO',
     'НИУ ВШЭ и Тинькофф',
     'perechen', 'main', 9, 11, 65, 2, True, True, True),
    ('och', 'Открытый чемпионат школьников по экономике',
     'Открытый чемпионат',
     'Ассоциация организаторов школьных олимпиад',
     'other', 'main', 7, 11, 20, None, False, True, True),
    ('kolokolnikov', 'Олимпиада Колокольникова по экономике',
     'Олимпиада Колокольникова',
     'Тюменский государственный университет',
     'other', 'main', 9, 11, 15, None, False, True, False),
    ('volnc', 'Олимпиада НОЦ ВолНЦ РАН по экономике', 'НОЦ ВолНЦ',
     'Вологодский научный центр РАН',
     'other', 'main', 8, 11, 10, None, False, True, True),
    # ── Смежный профиль ────────────────────────────────────────────────
    ('vp-ob', 'Высшая проба по основам бизнеса', 'ВП: основы бизнеса',
     'НИУ «Высшая школа экономики»',
     'perechen', 'related', 9, 11, 35, 2, False, True, False),
    ('vp-fingram', 'Высшая проба по финансовой грамотности',
     'ВП: финграмотность',
     'НИУ «Высшая школа экономики»',
     'perechen', 'related', 9, 11, 33, 2, False, True, False),
    ('finat', 'Всероссийская олимпиада по защите прав потребителей '
              'финансовых услуг', 'Финатлон',
     'Финансовый университет при Правительстве РФ',
     'perechen', 'related', 8, 11, 28, 3, False, True, False),
    ('skol', 'Кейс-чемпионат SKOLKOVO', 'SKOLKOVO',
     'Московская школа управления СКОЛКОВО',
     'other', 'related', 9, 11, 12, None, True, True, True),
    ('icef-evening-school', 'ICEF evening school', 'ICEF evening school',
     'МИЭФ НИУ ВШЭ',
     'other', 'related', 9, 11, 8, None, False, False, False),
]

DESCRIPTIONS = {
    'vseros': (
        'Главная школьная олимпиада страны: её проводит государство, и '
        'участвовать в школьном этапе может любой желающий. Проходит в '
        'четыре этапа — школьный, муниципальный, региональный и '
        'заключительный. Диплом победителя или призёра заключительного '
        'этапа даёт право поступления без вступительных испытаний, и это '
        'право установлено законом, а не решением отдельного вуза. '
        'Подтверждать результат баллом ЕГЭ по профильному предмету не '
        'требуется. Задания заключительного этапа традиционно сочетают '
        'микроэкономику, макроэкономику и задачи на работу с данными.'
    ),
    'mosh': (
        'Одна из самых массовых олимпиад перечня: отборочный тур проходит '
        'онлайн, а заключительный — очно в Москве и ряде городов-площадок. '
        'Задания заметно ближе к школьному курсу, чем у ВсОШ, но требуют '
        'аккуратной работы с графиками. Олимпиада традиционно держит первый '
        'уровень в перечне.'
    ),
    'vp': (
        'Олимпиада НИУ ВШЭ с сильным упором на формальные модели: спрос и '
        'предложение, поведение фирмы, простая теория игр. Отборочный тур '
        'онлайн, заключительный — очно на площадках вуза в нескольких '
        'городах. Хороший вход для тех, кто целится в экономические '
        'факультеты Вышки.'
    ),
}

# ── Этапы ВсОШ: образец подробного заполнения ──────────────────────────
# код, имя, порядок, формат, как попасть, города
# ⚠️ БЕЗ ДЛИТЕЛЬНОСТИ И МАКСИМУМА БАЛЛОВ. Их устанавливает предметно-
# методическая комиссия и публикует в требованиях к этапу; наполнение
# примерами их не знает. Прежде тут стояли выдуманные 235 и 240 минут —
# на экране они выглядели ровно как настоящие и прожили две сессии.
# Настоящие приходят импортом из data/olympiads/out/stages.jsonl,
# вместе со ссылкой на документ.
VSEROS_STAGES = [
    ('sch', 'Школьный этап', 1, 'offline',
     'Прийти в свою школу в назначенный день — отбора нет, участвовать '
     'может любой школьник подходящего класса.', []),
    ('mun', 'Муниципальный этап', 2, 'offline',
     'Набрать проходной балл школьного этапа, который устанавливает '
     'ваш муниципалитет.', []),
    ('reg', 'Региональный этап', 3, 'offline',
     'Набрать проходной балл муниципального этапа своего региона либо '
     'быть призёром или победителем регионального этапа прошлого года.', []),
    ('final', 'Заключительный этап', 4, 'offline',
     'Набрать всероссийский проходной балл на региональном этапе или '
     'отобраться по квоте для региона.',
     ['Москва', 'Санкт-Петербург', 'Казань', 'Тюмень', 'Сочи']),
]

# События ВсОШ на 2026/27. НИ ОДНОЙ конкретной даты, и это не лень:
# школьный и муниципальный этапы назначает каждый субъект своим приказом,
# а федеральный график регионального этапа на этот сезон ещё не издан.
VSEROS_EVENTS = [
    ('sch', 'stage', 'approx_last_year', 'обычно сентябрь — октябрь'),
    ('mun', 'stage', 'approx_last_year', 'обычно ноябрь — декабрь'),
    ('reg', 'stage', 'awaiting', 'график ещё не опубликован'),
    ('final', 'stage', 'awaiting', 'объявляют обычно в декабре'),
]

# ── Скелетные этапы остальных олимпиад ─────────────────────────────────
SKELETON_STAGES = {
    'mosh': [('qual', 'Отборочный тур', 1, 'online',
              'Зарегистрироваться на сайте и решить отборочный тур онлайн.',
              []),
             ('final', 'Заключительный тур', 2, 'offline',
              'Набрать проходной балл отборочного тура.',
              ['Москва', 'Санкт-Петербург', 'Екатеринбург', 'Новосибирск'])],
    'vp': [('qual', 'Отборочный тур', 1, 'online',
            'Зарегистрироваться и решить отборочный тур онлайн.', []),
           ('final', 'Заключительный тур', 2, 'offline',
            'Набрать проходной балл отборочного тура.',
            ['Москва', 'Санкт-Петербург', 'Нижний Новгород', 'Пермь'])],
    'spbgu': [('qual', 'Отборочный тур', 1, 'online', '', []),
              ('final', 'Заключительный тур', 2, 'offline',
               '', ['Санкт-Петербург'])],
    'lom': [('qual', 'Отборочный тур', 1, 'online', '', []),
            ('final', 'Заключительный тур', 2, 'offline',
             '', ['Москва'])],
    'pleh': [('qual', 'Отборочный тур', 1, 'online', '', []),
             ('final', 'Заключительный тур', 2, 'offline',
              '', ['Москва'])],
    'kondrat': [('final', 'Заключительный тур', 1, 'offline', '', ['Москва'])],
    'ranepa': [('qual', 'Отборочный тур', 1, 'online', '', []),
               ('final', 'Заключительный тур', 2, 'offline',
                '', ['Москва'])],
    'mis': [('qual', 'Отборочный тур', 1, 'online', '', []),
            ('final', 'Заключительный тур', 2, 'offline',
             '', ['Москва'])],
    'sb': [('qual', 'Отборочный тур', 1, 'online', '', []),
           ('final', 'Заключительный тур', 2, 'offline',
            '', ['Кемерово'])],
    'nes': [('qual', 'Отборочный тур', 1, 'online', '', [])],
    'ieo': [('qual', 'National selection', 1, 'online',
             '', []),
            ('final', 'International final', 2, 'offline',
             '', ['Не объявлен'])],
    'dano': [('qual', 'Отборочный тур', 1, 'online', '', []),
             ('final', 'Финал', 2, 'mixed', '', ['Москва'])],
    'och': [('final', 'Чемпионат', 1, 'online', '', [])],
    'kolokolnikov': [('final', 'Заключительный тур', 1, 'offline', '', ['Тюмень'])],
    'volnc': [('qual', 'Отборочный тур', 1, 'online', '', []),
              ('final', 'Заключительный тур', 2, 'online',
               '', [])],
    'vp-ob': [('qual', 'Отборочный тур', 1, 'online', '', [])],
    'vp-fingram': [('qual', 'Отборочный тур', 1, 'online',
                    '', [])],
    'finat': [('qual', 'Отборочный тур', 1, 'online', '', [])],
    'skol': [('final', 'Кейс-чемпионат', 1, 'mixed', '',
              ['Москва'])],
    'icef-evening-school': [('final', 'Итоговое испытание', 1, 'offline', '', ['Москва'])],
}

# ── События с подтверждёнными датами: МОШ и Высшая проба ───────────────
# Ради контраста в ленте: рядом с ориентирами ВсОШ видно, как выглядит
# подтверждённая дата. Открытие регистрации МОШ намеренно в прошлом —
# иначе чип «Идёт регистрация» не на чем было бы проверить.
DATED_EVENTS = [
    ('mosh', None, 'registration_open', '2026-08-25'),
    ('mosh', None, 'registration_close', '2026-10-20'),
    ('mosh', 'qual', 'stage', '2026-11-22'),
    ('vp', None, 'registration_open', '2026-09-20'),
    ('vp', None, 'registration_close', '2026-11-05'),
    ('vp', 'qual', 'stage', '2026-11-28'),
]

# ── Программы вузов ────────────────────────────────────────────────────
PROGRAMS = [
    (1, 'Совместный бакалавриат НИУ ВШЭ и РЭШ', 'ВШЭ-РЭШ', 'Экономика',
     'Москва'),
    (2, 'Экономический факультет МГУ', 'МГУ', 'Экономика', 'Москва'),
    (3, 'ФЭН НИУ ВШЭ', 'ФЭН ВШЭ', 'Экономика', 'Москва'),
    (4, 'МИЭФ НИУ ВШЭ', 'МИЭФ ВШЭ', 'Экономика', 'Москва'),
    (5, 'Санкт-Петербургский государственный университет', 'СПбГУ',
     'Экономика', 'Санкт-Петербург'),
    (6, 'Финансовый университет при Правительстве РФ', 'Финуниверситет',
     'Экономика', 'Москва'),
    (7, 'РАНХиГС', 'РАНХиГС', 'Экономика', 'Москва'),
]

# Льготы: три олимпиады на семь программ. Набор типов намеренно разный —
# таблица обязана уметь показать и «льготы нет».
BENEFITS = {
    'vseros': ['bvi'] * 7,
    'mosh': ['bvi', 'bvi', 'bvi', 'bvi', 'score_100', 'score_100', 'none'],
    'vp': ['bvi', 'bvi', 'score_100', 'score_100', 'score_100', 'none',
           'none'],
}

# Проходные на заключительный этап ВсОШ. 2022 год по 9 классу намеренно
# ПРОПУЩЕН: блок обязан честно показать пробел, а не сгладить его.
SCORES = [
    (2022, 10, 62), (2022, 11, 68),
    (2023, 9, 54), (2023, 10, 61), (2023, 11, 70),
    (2024, 9, 57), (2024, 10, 64), (2024, 11, 72),
    (2025, 9, 52), (2025, 10, 59), (2025, 11, 66),
    (2026, 9, 58), (2026, 10, 65), (2026, 11, 74),
]

# Комплекты заданий ВсОШ: год, этап, класс, разборы.
# ⚠️ НИ ЧИСЕЛ, НИ АДРЕСОВ ЗДЕСЬ НЕТ — это КАРКАС, а не данные.
# Сначала отсюда убрали выдуманные адреса (вида vos.olimpiada.ru/2026/final/11:
# выглядели рабочими, страниц по ним нет), теперь — выдуманные числа: стояли
# «6 заданий, 240 минут, 100 баллов» и «5 заданий, 235 минут», повторённые для
# всех лет механически. Настоящие числа берутся из шапок файлов заданий на
# vso.edsoo.ru и приходят импортом из data/olympiads/out/variants.jsonl —
# у заключительного этапа это 4 задания, 48 баллов, 210 минут НА ТУР, у
# регионального 18 заданий, 100 баллов, 180 минут. Ни одно из выдуманных
# чисел не совпало с настоящим. [ADR 0067]
VARIANTS = [
    (2026, 'final', 11, True),
    (2026, 'final', 10, True),
    (2026, 'reg', 11, True),
    (2026, 'reg', 9, False),
    (2025, 'final', 11, True),
    (2025, 'reg', 10, False),
    (2024, 'final', 11, True),
    (2024, 'reg', 11, False),
    (2023, 'final', 10, False),
    (2023, 'mun', 9, False),
    (2022, 'final', 11, False),
    (2022, 'reg', 11, False),
]

REGIONS = [
    'Республика Адыгея', 'Республика Алтай', 'Республика Башкортостан',
    'Республика Бурятия', 'Республика Дагестан', 'Республика Ингушетия',
    'Кабардино-Балкарская Республика', 'Республика Калмыкия',
    'Карачаево-Черкесская Республика', 'Республика Карелия',
    'Республика Коми', 'Республика Крым', 'Республика Марий Эл',
    'Республика Мордовия', 'Республика Саха (Якутия)',
    'Республика Северная Осетия — Алания', 'Республика Татарстан',
    'Республика Тыва', 'Удмуртская Республика', 'Республика Хакасия',
    'Чеченская Республика', 'Чувашская Республика',
    'Алтайский край', 'Забайкальский край', 'Камчатский край',
    'Краснодарский край', 'Красноярский край', 'Пермский край',
    'Приморский край', 'Ставропольский край', 'Хабаровский край',
    'Амурская область', 'Архангельская область', 'Астраханская область',
    'Белгородская область', 'Брянская область', 'Владимирская область',
    'Волгоградская область', 'Вологодская область', 'Воронежская область',
    'Ивановская область', 'Иркутская область', 'Калининградская область',
    'Калужская область', 'Кемеровская область', 'Кировская область',
    'Костромская область', 'Курганская область', 'Курская область',
    'Ленинградская область', 'Липецкая область', 'Магаданская область',
    'Московская область', 'Мурманская область', 'Нижегородская область',
    'Новгородская область', 'Новосибирская область', 'Омская область',
    'Оренбургская область', 'Орловская область', 'Пензенская область',
    'Псковская область', 'Ростовская область', 'Рязанская область',
    'Самарская область', 'Саратовская область', 'Сахалинская область',
    'Свердловская область', 'Смоленская область', 'Тамбовская область',
    'Тверская область', 'Томская область', 'Тульская область',
    'Тюменская область', 'Ульяновская область', 'Челябинская область',
    'Ярославская область',
    'Москва', 'Санкт-Петербург', 'Севастополь',
    'Еврейская автономная область',
    'Ненецкий автономный округ', 'Ханты-Мансийский автономный округ — Югра',
    'Чукотский автономный округ', 'Ямало-Ненецкий автономный округ',
]

EXPECTED = {
    'Olympiad всего': 21,
    "Olympiad display_group='main'": 16,
    "Olympiad display_group='related'": 5,
    'OlympiadStage у vseros': 4,
    'OlympiadEvent у vseros': 4,
    'OlympiadEvent у vseros с датой': 0,
    'UniversityProgram': 7,
    'OlympiadBenefit': 21,
    'OlympiadScore': 14,
    'OlympiadVariant': 12,
    'RegionalCoordinator': 85,
}


class Command(BaseCommand):
    help = ('Демонстрационные данные раздела олимпиад. Без --yes только '
            'печатает план и ничего не пишет.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes', action='store_true',
            help='Действительно записать данные в базу.')
        parser.add_argument(
            '--wipe', action='store_true',
            help='Сначала удалить существующие записи раздела.')

    def handle(self, *args, **options):
        if not options['yes']:
            self.stdout.write('ПЛАН (ничего не записано, нужен --yes):')
            for name, value in EXPECTED.items():
                self.stdout.write('  {:<32} {}'.format(name, value))
            self.stdout.write(
                'Все олимпиады помечаются is_placeholder=True.')
            return

        with transaction.atomic():
            if options['wipe']:
                self._wipe()
            self._seed()

        self._report()

    def _wipe(self):
        # Список удаления один на обе команды — `import_olympiads_data.wipe_section`.
        from olympiads.management.commands.import_olympiads_data import wipe_section
        wipe_section()
        self.stdout.write('Прежние записи раздела удалены.')

    def _seed(self):
        from datetime import date

        olympiads = {}
        for (slug, name_full, name_short, organizer, kind, group,
             gmin, gmax, rank, level, is_team, on_qual, on_final) in OLYMPIADS:
            obj, _ = Olympiad.objects.update_or_create(
                slug=slug,
                defaults=dict(
                    name_full=name_full, name_short=name_short,
                    organizer=organizer, kind=kind, display_group=group,
                    grade_min=gmin, grade_max=gmax, manual_rank=rank,
                    is_team=is_team, has_online_qualifier=on_qual,
                    has_online_final=on_final,
                    description=DESCRIPTIONS.get(slug, ''),
                    # ⚠️ АДРЕСОВ НЕ ВЫДУМЫВАЕМ. Прежде сюда шли
                    # https://example.org/<слаг>/ — и на карточке это была
                    # кнопка «Официальный сайт», ведущая в никуда. Пустое
                    # поле экран переживает, а школьник по такой кнопке
                    # уходит и не возвращается. Настоящие адреса приходят
                    # импортом из olympiads.jsonl.
                    official_url='', registration_url='',
                    language='Английский' if slug == 'ieo' else '',
                    is_placeholder=True, is_published=True,
                ),
            )
            olympiads[slug] = obj

            # Уровень в перечне заводим только тем, кто в перечне вообще
            # бывает. У ВсОШ уровня нет по устройству, и пустая строка с
            # approval_status='approved' говорит об этом прямо.
            if kind == 'vsosh':
                OlympiadLevelYear.objects.update_or_create(
                    olympiad=obj, academic_year=YEAR,
                    defaults=dict(level=None, approval_status='approved'),
                )
            elif kind == 'perechen':
                OlympiadLevelYear.objects.update_or_create(
                    olympiad=obj, academic_year=YEAR,
                    defaults=dict(level=level, approval_status='draft'),
                )

        # ── Этапы ──────────────────────────────────────────────────────
        stages = {}
        for code, name, order, fmt, qualify, cities in VSEROS_STAGES:
            stage, _ = OlympiadStage.objects.update_or_create(
                olympiad=olympiads['vseros'], code=code,
                defaults=dict(
                    name=name, order=order, format=fmt,
                    # ⚠️ ЧИСЛА СЮДА НЕ ПИШЕМ. Наполнение примерами знает
                    # устройство этапов, но не знает длительности и
                    # максимума баллов: их устанавливает предметно-
                    # методическая комиссия и публикует в требованиях.
                    # Выдуманные 235 и 240 минут прожили две сессии, и
                    # отличить их от настоящих на экране было нечем.
                    # Настоящие приходят импортом, вместе с источником.
                    how_to_qualify=qualify, cities=cities,
                ),
            )
            stages[('vseros', code)] = stage

        for slug, rows in SKELETON_STAGES.items():
            for code, name, order, fmt, qualify, cities in rows:
                stage, _ = OlympiadStage.objects.update_or_create(
                    olympiad=olympiads[slug], code=code,
                    defaults=dict(
                        name=name, order=order, format=fmt,
                        # ⚠️ ЧИСЛА СЮДА НЕ ПИШЕМ. Наполнение примерами знает
                        # устройство этапов, но не знает длительности и
                        # максимума баллов: их устанавливает предметно-
                        # методическая комиссия и публикует в требованиях.
                        # Выдуманные 235 и 240 минут прожили две сессии, и
                        # отличить их от настоящих на экране было нечем.
                        # Настоящие приходят импортом, вместе с источником.
                        how_to_qualify=qualify, cities=cities,
                    ),
                )
                stages[(slug, code)] = stage

        # ── События ────────────────────────────────────────────────────
        for code, kind, status, approx in VSEROS_EVENTS:
            event, _ = OlympiadEvent.objects.update_or_create(
                olympiad=olympiads['vseros'],
                stage=stages[('vseros', code)],
                academic_year=YEAR, kind=kind,
                defaults=dict(date_start=None, approx_text=approx,
                              date_status=status),
            )
            event.full_clean()

        for slug, stage_code, kind, iso in DATED_EVENTS:
            stage = stages[(slug, stage_code)] if stage_code else None
            year, month, day = (int(p) for p in iso.split('-'))
            event, _ = OlympiadEvent.objects.update_or_create(
                olympiad=olympiads[slug], stage=stage,
                academic_year=YEAR, kind=kind,
                defaults=dict(date_start=date(year, month, day),
                              approx_text='', date_status='confirmed'),
            )
            event.full_clean()

        # ── Программы и льготы ─────────────────────────────────────────
        programs = []
        for order, uni_name, uni_short, program_name, city in PROGRAMS:
            program, _ = UniversityProgram.objects.update_or_create(
                university_short=uni_short, program_name=program_name,
                defaults=dict(university_name=uni_name, city=city,
                              order=order,
                              # ⚠️ Тот же случай: выдуманный адрес правил
                              # приёма в таблице льгот выглядел рабочей
                              # ссылкой «Смотреть».
                              admission_rules_url=''),
            )
            programs.append(program)

        for slug, types in BENEFITS.items():
            for program, benefit_type in zip(programs, types):
                # У ВсОШ подтверждать результат баллом ЕГЭ не нужно — этим
                # она и отличается от перечневых, и колонка ради этого есть.
                if slug == 'vseros':
                    confirm_subject, confirm_score, required_level = '', None, None
                elif benefit_type == 'none':
                    confirm_subject, confirm_score, required_level = '', None, None
                else:
                    confirm_subject = 'Экономика'
                    confirm_score = 75
                    required_level = 1
                OlympiadBenefit.objects.update_or_create(
                    olympiad=olympiads[slug], program=program,
                    admission_year=ADMISSION_YEAR,
                    defaults=dict(
                        benefit_type=benefit_type,
                        score_100_subject=(
                            'Математика' if benefit_type == 'score_100' else ''),
                        confirm_subject=confirm_subject,
                        confirm_min_score=confirm_score,
                        required_level=required_level,
                        grades_note='9–11 классы',
                    ),
                )

        # ── Проходные баллы и комплекты ────────────────────────────────
        for year, grade, value in SCORES:
            OlympiadScore.objects.update_or_create(
                olympiad=olympiads['vseros'],
                stage=stages[('vseros', 'reg')],
                year=year, grade=grade, score_type='pass_to_final',
                defaults=dict(value=value, max_value=100, scope='federal'),
            )

        for year, code, grade, has_solutions in VARIANTS:
            OlympiadVariant.objects.update_or_create(
                olympiad=olympiads['vseros'],
                stage=stages[('vseros', code)],
                year=year, grade=grade,
                defaults=dict(
                    # ⚠️ ЧИСЛА И АДРЕС НЕ ПИШЕМ — ни настоящих, ни похожих
                    # на настоящие. Заготовка создаёт только каркас записи;
                    # заданий, минут и баллов у неё нет, пока импорт не
                    # принесёт их из шапки файла заданий. Пустое поле
                    # честнее правдоподобного числа: по минутам школьник
                    # ставит себе таймер тренировки. [ADR 0067]
                    problem_count=None, duration_minutes=None, max_score=None,
                    has_solutions=has_solutions,
                    original_url='', original_source='none',
                    ref_event_id='vseros-{}-{}-{}'.format(year, code, grade),
                    # Пометка снимается импортом, когда все три числа
                    # заполнены настоящими; это сторожит тест.
                    is_placeholder=True,
                ),
            )

        for region in REGIONS:
            RegionalCoordinator.objects.update_or_create(
                region_name=region,
                defaults=dict(url='', is_verified=False),
            )

    def _report(self):
        vseros = Olympiad.objects.filter(slug='vseros').first()
        actual = {
            'Olympiad всего': Olympiad.objects.count(),
            "Olympiad display_group='main'":
                Olympiad.objects.filter(display_group='main').count(),
            "Olympiad display_group='related'":
                Olympiad.objects.filter(display_group='related').count(),
            'OlympiadStage у vseros': vseros.stages.count(),
            'OlympiadEvent у vseros': vseros.events.count(),
            'OlympiadEvent у vseros с датой':
                vseros.events.exclude(date_start=None).count(),
            'UniversityProgram': UniversityProgram.objects.count(),
            'OlympiadBenefit': OlympiadBenefit.objects.count(),
            'OlympiadScore': OlympiadScore.objects.count(),
            'OlympiadVariant': OlympiadVariant.objects.count(),
            'RegionalCoordinator': RegionalCoordinator.objects.count(),
        }
        bad = []
        self.stdout.write('ЧИСЛОВЫЕ ИНВАРИАНТЫ:')
        for name, expected in EXPECTED.items():
            got = actual[name]
            mark = 'OK ' if got == expected else 'НЕТ'
            if got != expected:
                bad.append((name, expected, got))
            self.stdout.write('  {} {:<32} ждали {}, получили {}'.format(
                mark, name, expected, got))
        if bad:
            raise SystemExit(
                'Инварианты не сошлись: {}'.format(bad))
        self.stdout.write(self.style.SUCCESS(
            'Все инварианты сошлись. Данные демонстрационные, '
            'is_placeholder=True у всех олимпиад.'))
