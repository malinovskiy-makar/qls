# -*- coding: utf-8 -*-
"""
Приводит Topic и Tag к каноническому стандарту таксономии v1.1
(data/taxonomy.json: 29 тем, 344 тега).

По умолчанию сухой прогон — ничего не пишет. Пишет только с --apply,
и только после того, как владелец увидел стоп-гейт и явно согласился.

Темы: 23 существующие переименовываются в канонические (переименование,
а не создание с переносом — сохраняет внешние ключи), 6 создаются пустыми.
Таблица соответствия ниже утверждена владельцем 31.08, читается из этого
файла, а не из JSON — data/taxonomy.json не описывает, откуда куда
переименовывать, только конечный список тем.

Теги: для каждого из 344 канонических имён — находит или создаёт с
kind='canonical'. Связи Problem↔Tag не создаются и не рвутся: их
проставит прогон обогащения. Остальные существующие теги размечаются
по classify_legacy_tag() — author/junk/legacy, ничего не удаляется.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.db import transaction, IntegrityError
from django.core.management.base import BaseCommand

from problems.models import Topic, Tag


TAXONOMY_PATH = Path(settings.BASE_DIR) / 'data' / 'taxonomy.json'
REPORT_DIR = Path(settings.BASE_DIR) / 'reports' / 'taxonomy_v2'
REPORT_PATH = REPORT_DIR / 'load_taxonomy_dry_run.txt'


# ---------------------------------------------------------------------------
# Таблица соответствия старая тема → каноническая (утверждена владельцем).
# None — тема создаётся пустой, её наполнит прогон обогащения.
# ---------------------------------------------------------------------------

THEME_SOURCE = {
    'Введение в экономику и экономическое мышление': 'Введение в экономическую теорию',
    'Альтернативные издержки и КПВ': 'Альтернативные издержки и КПВ',
    'Спрос, предложение и рыночное равновесие': 'Спрос и предложение',
    'Эластичность': 'Эластичность',
    'Теория потребителя и полезность': 'Теория потребителя и полезность',
    'Производство и издержки фирмы': 'Теория фирмы: производство и издержки',
    'Совершенная конкуренция': 'Совершенная конкуренция',
    'Монополия и ценовая дискриминация': 'Монополия и ценовая дискриминация',
    'Олигополия и теория игр': 'Олигополия и теория игр',
    'Вмешательство государства': 'Вмешательство государства',
    'Внешние эффекты и общественные блага': None,
    'Асимметрия информации и риск': None,
    'Рынок труда и факторы производства': 'Рынок труда',
    'Неравенство доходов': 'Неравенство доходов',
    'Международная торговля': 'Международная торговля',
    'Открытая экономика и валютный рынок': None,
    'ВВП и национальные счета': 'ВВП и национальные счета',
    'Инфляция и индексы цен': 'Инфляция и безработица',
    'Безработица и занятость': None,
    'Макроэкономическое равновесие: AD–AS и IS–LM': 'Совокупный спрос и совокупное предложение',
    'Фискальная политика': 'Фискальная политика',
    'Монетарная политика и банковская система': 'Монетарная политика',
    'Экономический рост и циклы': 'Экономический рост и циклы',
    'Проценты, вклады и кредиты': None,
    'Инвестиции и ценные бумаги': 'Финансы и финансовые инструменты',
    'Поведенческая экономика': 'Поведенческая экономика',
    'Данные, статистика и причинность': 'Эконометрика и анализ данных',
    'Математический аппарат': 'Математика и оптимизация',
    'Другое': None,
}

# Темы, которые до прогона обогащения временно приютят чужие задачи.
MIXED_TOPICS = [
    'Инфляция и индексы цен',
    'Инвестиции и ценные бумаги',
    'Международная торговля',
]


# ---------------------------------------------------------------------------
# Slug — тот же паттерн транслитерации, что в apply_topic_mapping.py.
# ---------------------------------------------------------------------------

_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _make_base_slug(name, max_len):
    chars = [_TRANSLIT.get(c, c) for c in name.lower()]
    slug = re.sub(r'[^a-z0-9]+', '-', ''.join(chars)).strip('-')
    return slug[:max_len] or 'item'


def _unique_slug(model, name, max_len):
    base = _make_base_slug(name, max_len)
    slug = base
    n = 1
    while model.objects.filter(slug=slug).exists():
        suffix = f'-{n}'
        slug = f'{base[:max_len - len(suffix)]}{suffix}'
        n += 1
    return slug


# ---------------------------------------------------------------------------
# Классификация тегов вне 344 канонических — правилами, не на глаз.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"^[A-ZА-ЯЁ][a-zа-яё'-]*\.?$")
_INITIALS_RE = re.compile(r'^[A-ZА-ЯЁ]\.([A-ZА-ЯЁ]\.)?$')
_ONLY_DIGITS_PUNCT_RE = re.compile(r'^[\d\W_]+$', re.UNICODE)

# Имя файла, утёкшее в тег при импорте: расширение в конце — верный признак.
_FILE_EXT = ('.pdf', '.docx', '.doc', '.tex', '.txt')

# Имена, которые правило классифицирует неверно, а починить это правилом
# нельзя: «Open Question» и «David Luenberger» формально неотличимы —
# два слова с заглавных букв латиницей. Список короткий, читается глазами,
# пополняется только владельцем.
MANUAL_KIND_OVERRIDES = {
    'Open Question': 'legacy',   # тип вопроса формата IEO, не имя автора
    'Задача Для Подготовки к многопрофильной олимпиаде ГУ-ВШЭ 10 класс': 'legacy',
    # обрубок описания источника, а не мусор: под junk попал по длине
}


def classify_legacy_tag(name):
    """Классифицирует тег, не входящий в 344 канонических: author / junk / legacy.

    junk — URL (http, ://, www.), имя файла (.pdf, .docx, .doc, .tex, .txt),
    либо длиннее 60 символов, либо состоит только из цифр и знаков.
    author — 2-3 слова с заглавных букв (либо инициалы вида «А.А.»), без
    цифр — похоже на имя составителя, а не на экономический термин
    (те в базе лежат отдельными словами в нижнем регистре).
    legacy — всё остальное.

    MANUAL_KIND_OVERRIDES применяется ПОСЛЕ правила и перекрывает его:
    правилом эти случаи не чинятся, они формально неотличимы от верных.
    """
    s = (name or '').strip()
    low = s.lower()

    if 'http' in low or '://' in low or 'www.' in low or len(s) > 60:
        kind = 'junk'
    elif low.endswith(_FILE_EXT):
        kind = 'junk'
    elif _ONLY_DIGITS_PUNCT_RE.match(s):
        kind = 'junk'
    else:
        words = s.split()
        if 2 <= len(words) <= 3 and all(
            _WORD_RE.match(w) or _INITIALS_RE.match(w) for w in words
        ):
            kind = 'author'
        else:
            kind = 'legacy'

    return MANUAL_KIND_OVERRIDES.get(s, kind)


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = ('Приводит Topic и Tag к каноническому стандарту таксономии v1.1. '
            'По умолчанию сухой прогон, пишет только с --apply.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Боевой прогон: записать изменения. Без флага — только отчёт.')

    def handle(self, *args, **opts):
        apply_ = opts['apply']

        with open(TAXONOMY_PATH, encoding='utf-8') as f:
            taxonomy = json.load(f)
        themes = taxonomy['themes']

        missing_in_source = [t['name'] for t in themes if t['name'] not in THEME_SOURCE]
        if missing_in_source:
            self.stderr.write(self.style.ERROR(
                'В THEME_SOURCE нет соответствия для тем: ' + ', '.join(missing_in_source)))
            return

        problem_topic_before = Topic.problems.through.objects.count()
        problem_tag_before = Tag.problems.through.objects.count()

        topic_plan = self._plan_topics(themes)
        tag_plan = self._plan_tags(taxonomy)

        if apply_:
            self._apply_topics(topic_plan)
            self._apply_tags(tag_plan)

        problem_topic_after = Topic.problems.through.objects.count()
        problem_tag_after = Tag.problems.through.objects.count()

        self._report(topic_plan, tag_plan,
                     problem_topic_before, problem_topic_after,
                     problem_tag_before, problem_tag_after,
                     apply_)

    # --- планирование: темы -------------------------------------------------

    def _plan_topics(self, themes):
        """Возвращает список записей {theme, state, topic} без записи в базу.

        state: 'already_canonical' | 'renamed' | 'created'
        needs_write: True, если после апдейта хоть одно поле изменится.
        """
        plan = []
        for theme in themes:
            canonical_name = theme['name']
            old_name = THEME_SOURCE[canonical_name]

            topic = Topic.objects.filter(name=canonical_name).first()
            if topic is not None:
                state = 'already_canonical'
            elif old_name is not None:
                topic = Topic.objects.filter(name=old_name).first()
                state = 'renamed' if topic is not None else 'created'
            else:
                state = 'created'

            needs_write = (
                topic is None
                or topic.name != canonical_name
                or topic.is_canonical is not True
                or topic.description != theme['description']
                or topic.order != theme['id']
            )

            plan.append({
                'theme': theme,
                'canonical_name': canonical_name,
                'topic': topic,
                'state': state,
                'needs_write': needs_write,
            })
        return plan

    def _apply_topics(self, plan):
        for entry in plan:
            if not entry['needs_write']:
                continue
            theme = entry['theme']
            topic = entry['topic']
            if topic is None:
                slug = _unique_slug(Topic, entry['canonical_name'], 220)
                topic = Topic.objects.create(
                    name=entry['canonical_name'], slug=slug,
                    description=theme['description'], order=theme['id'],
                    is_canonical=True,
                )
            else:
                topic.name = entry['canonical_name']
                topic.is_canonical = True
                topic.description = theme['description']
                topic.order = theme['id']
                topic.save(update_fields=['name', 'is_canonical', 'description', 'order'])
            entry['topic'] = topic

    # --- планирование: теги --------------------------------------------------

    def _plan_tags(self, taxonomy):
        canonical_names = []
        for theme in taxonomy['themes']:
            canonical_names.extend(theme['tags'])
        canonical_set = set(canonical_names)

        canon_plan = []
        for name in canonical_names:
            tag = Tag.objects.filter(name=name).first()
            canon_plan.append({
                'name': name,
                'tag': tag,
                'found_existing': tag is not None,
                'needs_write': tag is None or tag.kind != 'canonical',
            })

        legacy_plan = []
        author_names = []
        junk_names = []
        legacy_count = 0
        for tag in Tag.objects.exclude(name__in=canonical_set):
            kind = classify_legacy_tag(tag.name)
            legacy_plan.append({'tag': tag, 'kind': kind, 'needs_write': tag.kind != kind})
            if kind == 'author':
                author_names.append(tag.name)
            elif kind == 'junk':
                junk_names.append(tag.name)
            else:
                legacy_count += 1

        return {
            'canon_plan': canon_plan,
            'legacy_plan': legacy_plan,
            'author_names': sorted(author_names),
            'junk_names': sorted(junk_names),
            'legacy_count': legacy_count,
        }

    def _apply_tags(self, tag_plan):
        for entry in tag_plan['canon_plan']:
            if not entry['needs_write']:
                continue
            tag = entry['tag']
            if tag is None:
                slug = _unique_slug(Tag, entry['name'], 120)
                try:
                    with transaction.atomic():
                        tag = Tag.objects.create(
                            name=entry['name'][:99], slug=slug, kind='canonical')
                except IntegrityError:
                    tag = Tag.objects.get(name=entry['name'])
                    tag.kind = 'canonical'
                    tag.save(update_fields=['kind'])
            else:
                tag.kind = 'canonical'
                tag.save(update_fields=['kind'])
            entry['tag'] = tag

        for entry in tag_plan['legacy_plan']:
            if not entry['needs_write']:
                continue
            tag = entry['tag']
            tag.kind = entry['kind']
            tag.save(update_fields=['kind'])

    # --- отчёт -----------------------------------------------------------

    def _report(self, topic_plan, tag_plan,
                pt_before, pt_after, tt_before, tt_after, apply_):
        renamed = sum(1 for e in topic_plan if e['state'] == 'renamed')
        created = sum(1 for e in topic_plan if e['state'] == 'created')
        already = sum(1 for e in topic_plan if e['state'] == 'already_canonical')
        # Прогноз, не текущее состояние: «переименовано» и «создано новых»
        # ещё не записаны при сухом прогоне, поэтому считаем от текущего
        # общего числа строк Topic, а не по факту совпадения имён.
        non_canonical_left = Topic.objects.count() - (renamed + already)

        w = self.stdout.write
        w(self.style.MIGRATE_HEADING('\nТЕМЫ'))
        w(f'  переименовано:      {renamed}')
        w(f'  создано новых:      {created}')
        w(f'  уже канонические:   {already}')
        w(f'  осталось неканоническими: {non_canonical_left}')
        w('  ⚠️ временно смешанные темы:')
        for name in MIXED_TOPICS:
            topic = Topic.objects.filter(name=name).first()
            if topic is None:
                old_name = THEME_SOURCE.get(name)
                topic = Topic.objects.filter(name=old_name).first() if old_name else None
            count = topic.problems.count() if topic is not None else 0
            w(f'     {name:<35} — {count} задач (не разделено до прогона)')

        found_existing = sum(1 for e in tag_plan['canon_plan'] if e['found_existing'])
        tag_created = sum(1 for e in tag_plan['canon_plan'] if not e['found_existing'])
        author_names = tag_plan['author_names']
        junk_names = tag_plan['junk_names']
        legacy_count = tag_plan['legacy_count']

        w(self.style.MIGRATE_HEADING('\nТЕГИ'))
        w(f'  найдено существующих из 344:   {found_existing}')
        w(f'  создано новых:                 {tag_created}')
        w(f'  помечено author:               {len(author_names)}')
        w(f'  помечено junk:                 {len(junk_names)}')
        w(f'  помечено legacy:               {legacy_count}')

        w(self.style.MIGRATE_HEADING('\nСВЯЗИ'))
        w(f'  Problem→Topic до / после:  {pt_before} / {pt_after}')
        w(f'  Problem→Tag   до / после:  {tt_before} / {tt_after}')

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write('=== author (владелец сверяет глазами) ===\n')
            f.write('\n'.join(author_names) + '\n\n')
            f.write('=== junk (владелец сверяет глазами) ===\n')
            f.write('\n'.join(junk_names) + '\n')
        w(f'\nСписки author/junk целиком: {REPORT_PATH}')

        if apply_:
            total_writes = (
                sum(1 for e in topic_plan if e['needs_write'])
                + sum(1 for e in tag_plan['canon_plan'] if e['needs_write'])
                + sum(1 for e in tag_plan['legacy_plan'] if e['needs_write'])
            )
            w(self.style.SUCCESS(f'\n[--apply] Записано изменений: {total_writes}.'))
        else:
            w(self.style.NOTICE(
                '\n[dry-run] Ничего не записано. Нужно явное «да» владельца, '
                'затем --apply.'))
