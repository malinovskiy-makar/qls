# -*- coding: utf-8 -*-
r"""Собирает data/econ_terms.json из markdown-словаря терминов (С6).

Источник — `data/econ_terms_source.md`, 13 341 строка: машинный перебор
десяти учебников (6 743 страницы), три русских олимпиадных источника
(РЭМ, САФ, АА) с приоритетом при выборе канонической формы.

⚠️ ИСТОЧНИК НЕ ПРАВИТСЯ РУКАМИ, И ЭТО НАМЕРЕННО. Он лежит в репозитории
как артефакт-первоисточник: по нему можно проверить любое расхождение и
пересобрать JSON заново. Все известные пропуски чинятся здесь, в
`KNOWN_FIXES`, — так починка видна в коде, покрыта тестом и не потеряется
молча, когда придёт новая версия словаря. Если бы мы правили сам markdown,
следующая присланная версия тихо откатила бы починку.

Запуск:
    venv313/Scripts/python.exe manage.py build_econ_terms
    venv313/Scripts/python.exe manage.py build_econ_terms --check   # не писать, только сверить
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SOURCE_NAME = 'econ_terms_source.md'
OUTPUT_NAME = 'econ_terms.json'

# Заголовки разделов словаря.
CATALOG_HEADING = '## Каталог терминов'
INDEX_HEADING = '## Обратный индекс'
QUALITY_HEADING = '## Контроль качества'

# Поля одной записи. Порядок в словаре именно такой, но парсер на порядок
# не опирается — ищет по имени поля.
FIELD_SYNONYMS = 'Синонимы и русские варианты'
FIELD_ENGLISH = 'English'
FIELD_NOTATIONS = 'Сокращения и обозначения'
FIELD_WORD_FORMS = 'Частые словоформы'
FIELD_SOURCES = 'Источники/покрытие'

# «Поля нет» в словаре обозначено длинным тире, а не пустой строкой.
EMPTY_MARK = '—'

# Падежные метки словоформ: «род. абсолютной величины; дат. ...».
CASE_LABELS = ('род.', 'дат.', 'твор.', 'предл.', 'им.', 'вин.')

RE_SECTION = re.compile(r'^###\s+(?P<name>.+?)\s*$')
RE_TERM = re.compile(r'^-\s+\*\*(?P<term>.+?)\*\*\s*$')
RE_FIELD = re.compile(r'^\s{2,}-\s+(?P<name>[^:]+):\s*(?P<value>.*?)\s*$')
RE_INDEX_ROW = re.compile(r'^\|\s*(?P<symbol>.+?)\s*\|\s*(?P<terms>.+?)\s*\|\s*$')


# ⚠️ ИЗВЕСТНЫЕ ПРОПУСКИ СЛОВАРЯ — чинятся здесь, а не в источнике.
#
# AD–AS: сам словарь в разделе «Контроль качества» честно пишет про себя
# «Обязательные олимпиадные обозначения: MISSING: AD–AS». Разбор показал,
# что именно пропущено: термин «модель AD–AS» в словаре ЕСТЬ, и в его
# обозначениях стоит `AD-AS` через ОБЫЧНЫЙ ДЕФИС, а вариант через
# ЕН-ТИРЕ `AD–AS` — только в заголовке раздела и в English-поле, то есть
# в обратный индекс он не попадает.
#
# Это ровно тот класс пропуска, который потом ищут часами: в условиях
# задач встречаются оба начертания (авторы набирают то дефис, то тире,
# Word и вовсе меняет одно на другое автозаменой), а нормализация молча
# видела бы только половину.
KNOWN_FIXES = {
    # канонический термин -> обозначения, которые надо к нему добавить
    # ВРЕМЕННО ОТКЛЮЧЕНО фазой зубастости — TODO(toothy-phase): вернуть AD–AS.
}


def _split_list(value):
    """Значение поля -> список. `—` даёт пустой список, а не ['—']."""
    value = (value or '').strip()
    if not value or value == EMPTY_MARK:
        return []
    parts = [p.strip() for p in value.split(';')]
    return [p for p in parts if p and p != EMPTY_MARK]


def _clean_notation(raw):
    """Обозначение как есть -> голый символ.

    В словаре одно и то же обозначение встречается и как `AC`, и как
    `\\(AC\\)` — второе это разметка формулы, а не другой символ. Для
    поиска по тексту задачи нужен голый вид, иначе один и тот же `AC`
    лёг бы в индекс двумя разными ключами.
    """
    text = raw.strip().strip('`').strip()
    if text.startswith('\\(') and text.endswith('\\)'):
        text = text[2:-2]
    return text.strip()


def _parse_word_forms(value):
    """«род. X; дат. Y» -> {'род': 'X', 'дат': 'Y'}.

    Метка падежа отделяется от самой формы, потому что контрольным
    набором для лемматизации служит именно ФОРМА («абсолютной величины»),
    а не строка с приклеенной меткой.
    """
    forms = {}
    for chunk in _split_list(value):
        for label in CASE_LABELS:
            if chunk.startswith(label):
                case = label.rstrip('.')
                forms[case] = chunk[len(label):].strip()
                break
    return forms


def _parse_sources(value):
    """«РЭМ, САФ, АА; приоритет: олимпиадное ядро» -> (список, приоритет).

    ⚠️ Звёздочка после кода источника значит своё (см. сноску в конце
    словаря): термин нормализован по тематическому охвату учебника, но
    буквально в его англоязычном тексте не встречался. Признак сохраняем
    отдельным флагом, а сам код источника чистим — иначе «NS» и «NS*»
    были бы разными источниками при подсчёте покрытия.
    """
    priority = ''
    codes_part = value or ''
    if ';' in codes_part:
        head, _, tail = codes_part.partition(';')
        if 'приоритет' in tail:
            codes_part = head
            priority = tail.split(':', 1)[-1].strip()
    codes = []
    approximate = []
    for code in (c.strip() for c in codes_part.split(',')):
        if not code or code == EMPTY_MARK:
            continue
        if code.endswith('*'):
            code = code.rstrip('*').strip()
            approximate.append(code)
        if code:
            codes.append(code)
    return codes, priority, approximate


class Command(BaseCommand):
    help = 'Собирает data/econ_terms.json из markdown-словаря терминов'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check', action='store_true',
            help='Ничего не записывать: разобрать источник и напечатать числа. '
                 'Нужен, чтобы сверить словарь, не трогая рабочий JSON.',
        )

    def handle(self, *args, **options):
        data_dir = Path(settings.BASE_DIR) / 'data'
        source_path = data_dir / SOURCE_NAME
        if not source_path.exists():
            raise CommandError('Нет файла словаря: %s' % source_path)

        text = source_path.read_text(encoding='utf-8')
        lines = text.splitlines()

        terms = self._parse_terms(lines)
        self._apply_known_fixes(terms)
        index_rows = self._parse_reverse_index(lines)
        notation_index = self._build_notation_index(terms, index_rows)
        declared = self._parse_declared_counts(text)

        payload = {
            'meta': {
                'source_file': SOURCE_NAME,
                'source_lines': len(lines),
                'schema': (
                    'канонический термин -> синонимы -> English -> обозначения '
                    '-> словоформы -> источники -> раздел'
                ),
                'declared_counts': declared,
                'actual_counts': {
                    'terms': len(terms),
                    'ru_aliases': sum(len(t['synonyms']) for t in terms),
                    'english': sum(len(t['english']) for t in terms),
                    'notations': sum(len(t['notations']) for t in terms),
                    'sections': len({t['section'] for t in terms}),
                    'index_symbols': len(notation_index),
                    'ambiguous_symbols': sum(
                        1 for v in notation_index.values() if not v['auto_normalize']
                    ),
                },
                'known_fixes_applied': {k: v for k, v in KNOWN_FIXES.items()},
            },
            'terms': terms,
            'notation_index': notation_index,
        }

        counts = payload['meta']['actual_counts']
        for key, value in counts.items():
            self.stdout.write('  %-20s %s' % (key, value))

        # ⚠️ СВЕРКА УЧИТЫВАЕТ НАШИ ЖЕ ПОЧИНКИ, ИНАЧЕ ОНА БЕСПОЛЕЗНА.
        # KNOWN_FIXES добавляют обозначения, которых в источнике нет, —
        # значит разобранное число обозначений ЗАКОНОМЕРНО больше
        # заявленного ровно на их количество. Без этой поправки сверка
        # вечно показывала бы расхождение, к нему привыкли бы, и она
        # перестала бы ловить настоящую поломку парсера.
        fixes_added = sum(len(v) for v in KNOWN_FIXES.values())
        expected_delta = {'notations': fixes_added}
        problems_found = []
        for key, value in declared.items():
            delta = expected_delta.get(key, 0)
            actual = counts.get(key)
            if actual == value + delta:
                mark = 'ok' if not delta else 'ok (+%d наших починок)' % delta
            else:
                mark = 'РАСХОЖДЕНИЕ'
                problems_found.append(key)
            self.stdout.write('  заявлено %-12s %-6s (разобрано %s) %s'
                              % (key, value, actual, mark))

        if problems_found:
            raise CommandError(
                'Разобранное не сходится с заявленным по: %s. Это значит, что '
                'парсер не понял часть записей словаря — молча недоразобранный '
                'словарь выглядел бы как рабочий.' % ', '.join(problems_found))

        if options['check']:
            self.stdout.write(self.style.WARNING('--check: файл не записан'))
            return

        output_path = data_dir / OUTPUT_NAME
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False),
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS('Записан %s' % output_path))

    # -- разбор ------------------------------------------------------------

    def _parse_terms(self, lines):
        """Каталог терминов: разделы `###` и записи `- **термин**`."""
        terms = []
        section = ''
        in_catalog = False
        current = None

        for line in lines:
            if line.startswith(CATALOG_HEADING):
                in_catalog = True
                continue
            if line.startswith(INDEX_HEADING) or line.startswith(QUALITY_HEADING):
                in_catalog = False
                continue
            if not in_catalog:
                continue

            match_section = RE_SECTION.match(line)
            if match_section:
                section = match_section.group('name')
                current = None
                continue

            match_term = RE_TERM.match(line)
            if match_term:
                current = {
                    'canonical': match_term.group('term').strip(),
                    'section': section,
                    'synonyms': [],
                    'english': [],
                    'notations': [],
                    'word_forms': {},
                    'sources': [],
                    'priority': '',
                    'sources_approximate': [],
                }
                terms.append(current)
                continue

            if current is None:
                continue

            match_field = RE_FIELD.match(line)
            if not match_field:
                continue
            name = match_field.group('name').strip()
            value = match_field.group('value')

            if name == FIELD_SYNONYMS:
                current['synonyms'] = _split_list(value)
            elif name == FIELD_ENGLISH:
                current['english'] = _split_list(value)
            elif name == FIELD_NOTATIONS:
                current['notations'] = [
                    _clean_notation(v) for v in _split_list(value)
                ]
                current['notations'] = [n for n in current['notations'] if n]
            elif name == FIELD_WORD_FORMS:
                current['word_forms'] = _parse_word_forms(value)
            elif name == FIELD_SOURCES:
                codes, priority, approximate = _parse_sources(value)
                current['sources'] = codes
                current['priority'] = priority
                current['sources_approximate'] = approximate

        return terms

    def _apply_known_fixes(self, terms):
        by_name = {t['canonical']: t for t in terms}
        for canonical, extra in KNOWN_FIXES.items():
            target = by_name.get(canonical)
            if target is None:
                raise CommandError(
                    'KNOWN_FIXES ссылается на термин «%s», которого нет в '
                    'словаре. Либо словарь заменили новой версией с другой '
                    'формулировкой, либо опечатка в починке.' % canonical)
            for notation in extra:
                if notation not in target['notations']:
                    target['notations'].append(notation)

    def _parse_reverse_index(self, lines):
        """Таблица обратного индекса в конце словаря."""
        rows = []
        in_index = False
        for line in lines:
            if line.startswith(INDEX_HEADING):
                in_index = True
                continue
            if line.startswith(QUALITY_HEADING):
                in_index = False
                continue
            if not in_index or not line.startswith('|'):
                continue
            match = RE_INDEX_ROW.match(line)
            if not match:
                continue
            symbol = _clean_notation(match.group('symbol'))
            terms_cell = match.group('terms').strip()
            # Строка-разделитель таблицы и её шапка.
            if not symbol or set(symbol) <= set('-: ') or 'Канонический термин' in terms_cell:
                continue
            rows.append((symbol, [t.strip() for t in terms_cell.split(';') if t.strip()]))
        return rows

    def _build_notation_index(self, terms, index_rows):
        """Символ -> канонические термины, плюс флаг автонормализации.

        ⚠️ ПРАВИЛО ИЗ САМОГО СЛОВАРЯ, И ОНО КОНТРИНТУИТИВНО: если у
        обозначения больше одного канонического термина, оно НЕ
        нормализуется автоматически вовсе. `P` — это и цена, и уровень
        цен, и put-опцион; `S` — и предложение, и сбережения, и цена
        базисного актива. Однозначное сопоставление без контекста
        УХУДШАЕТ качество поиска, а не улучшает: кажется, что чем больше
        сопоставлений, тем лучше, — здесь наоборот.
        """
        index = {}

        def add(symbol, canonical):
            if not symbol or not canonical:
                return
            slot = index.setdefault(symbol, {'terms': [], 'auto_normalize': True})
            if canonical not in slot['terms']:
                slot['terms'].append(canonical)

        # Сначала обозначения из карточек терминов — они первичны: там
        # сказано, какому термину символ принадлежит по определению.
        for term in terms:
            for notation in term['notations']:
                add(notation, term['canonical'])

        # Потом таблица обратного индекса: она добавляет формульные
        # варианты (`C′(q)`, `dTC/dQ`), которых в карточках нет.
        for symbol, canonicals in index_rows:
            for canonical in canonicals:
                add(symbol, canonical)

        for slot in index.values():
            slot['auto_normalize'] = len(slot['terms']) == 1
        return index

    def _parse_declared_counts(self, text):
        """Числа, которые словарь заявляет о себе сам, — из его шапки.

        Нужны не для красоты: расхождение разобранного с заявленным
        означает, что парсер не понял часть записей, а молчаливо
        недоразобранный словарь выглядел бы как рабочий.
        """
        declared = {}
        patterns = {
            'terms': r'\*\*([\d\s,]+?)\s*канонических терминов\*\*',
            'ru_aliases': r'\*\*([\d\s,]+?)\s*русских алиасов\*\*',
            'english': r'\*\*([\d\s,]+?)\s*английских эквивалентов\*\*',
            'notations': r'\*\*([\d\s,]+?)\s*форм сокращений/обозначений\*\*',
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                declared[key] = int(match.group(1).replace(',', '').replace(' ', ''))
        return declared
