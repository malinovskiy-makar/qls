# -*- coding: utf-8 -*-
"""Разбор реестра аккредитованных организаций Рособрнадзора (раунд 3, 29.10.2026).

Открытые данные, набор `7701537808-RAOO`: https://isga.obrnadzor.gov.ru/accredreestr/
opendata/ (обновляется ежедневно). Постоянная ссылка на свежий архив — `ARCHIVE_URL`:
ZIP ≈ 350 МБ, внутри XML ≈ 1 ГБ (+ файл подписи `.sig`). Описание полей — например
https://isga.obrnadzor.gov.ru/xml/data-20160908-structure-20160713.xml.

Один разборщик на две команды: `load_schools --format raoo <файл>` и `sync_schools`.

Что считается школой: организация, у которой в ДЕЙСТВУЮЩЕМ свидетельстве есть
ДЕЙСТВУЮЩЕЕ приложение с программой уровня «… общее образование» (начальное,
основное или среднее). Колледжи, вузы, детсады и доп. образование отсеиваются сами.

⚠️ ОРГАНИЗАЦИЮ БЕРЁМ ИЗ ПРИЛОЖЕНИЯ, А НЕ ИЗ СВИДЕТЕЛЬСТВА. Филиал приходит
приложением к свидетельству головной организации, со своей карточкой
`ActualEducationOrganization` (`IsBranch=1`, свой адрес) — так филиал становится
отдельной школой со своим городом.

⚠️ ИЗ РЕЕСТРА БЕРЁМ ТОЛЬКО СВЕДЕНИЯ ОБ ОРГАНИЗАЦИИ: название, номер, адрес → город,
регион, ИНН/КПП, идентификатор. ФИО директора, телефоны и почты в реестре есть — мы
их не читаем и не храним.

Разбор потоковый (`iterparse` с очисткой элементов), прямо из ZIP, без распаковки.
"""
import io
import re
import zipfile
from functools import lru_cache
# ⚠️ Стандартный разборщик, а не defusedxml (его нет в боевых зависимостях): внешние
# сущности ElementTree не раскрывает, а expat ≥ 2.4.1 (у нас 2.7.3) сам режет
# «billion laughs» и квадратичное раздувание (документация Python, «XML vulnerabilities»).
from xml.etree.ElementTree import iterparse  # nosec B405

ARCHIVE_URL = 'https://isga.obrnadzor.gov.ru/api/spa/accredreestr/opendata/filezip'
PAGE_URL = 'https://isga.obrnadzor.gov.ru/accredreestr/opendata/'

VALID = 'Действующее'
#: Уровни, по которым организация считается школой.
GENERAL_LEVELS = frozenset({'Начальное общее образование', 'Основное общее образование',
                            'Среднее общее образование', 'Среднее (полное) общее образование'})
#: Города федерального значения: «г.» в адресе у них может не стоять.
FEDERAL_CITIES = ('Москва', 'Санкт-Петербург', 'Севастополь')


def open_xml(path):
    """Файловый объект XML реестра: из `.zip` (первый `.xml` внутри) или сам `.xml`.

    Возвращает (файл, закрыть) — `закрыть()` освобождает и ZIP, и поток.
    """
    if zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        names = [n for n in archive.namelist() if n.lower().endswith('.xml')]
        if not names:
            archive.close()
            raise ValueError('в архиве нет XML')
        stream = archive.open(names[0])

        def close():
            stream.close()
            archive.close()
        return stream, close
    handle = open(path, 'rb')
    head = handle.read(64)
    handle.seek(0)
    if not head.lstrip().startswith(b'<'):
        handle.close()
        raise ValueError('файл не ZIP и не XML')
    return handle, handle.close


def _text(element, path):
    found = element.find(path)
    return (found.text or '').strip() if found is not None else ''


def _org(element):
    """Сведения об организации из `ActualEducationOrganization` (без ФИО и контактов)."""
    return {
        'registry_id': _text(element, 'Id'),
        'full_name': _text(element, 'FullName'),
        'short_name': _text(element, 'ShortName'),
        'is_branch': _text(element, 'IsBranch') in ('1', 'true', 'True'),
        'address': _text(element, 'PostAddress'),
        'inn': _text(element, 'INN'),
        'kpp': _text(element, 'KPP'),
        'kind_name': _text(element, 'KindName'),
        'type_name': _text(element, 'TypeName'),
        'region': _text(element, 'RegionName'),
    }


def _has_general(supplement):
    for program in supplement.iterfind('EducationalPrograms/EducationalProgram'):
        if _text(program, 'IsCanceled') in ('1', 'true', 'True'):
            continue
        if _text(program, 'EduLevelName') in GENERAL_LEVELS:
            return True
    return False


def iter_raoo(stream):
    """Организации-школы из XML реестра. Одна организация может прийти несколько раз
    (несколько свидетельств или приложений) — склеивает вызывающий по `registry_id`."""
    for _event, element in iterparse(stream, events=('end',)):  # nosec B314 — см. комментарий у импорта
        if element.tag != 'Certificate':
            continue
        if _text(element, 'StatusName') == VALID:
            head = element.find('ActualEducationOrganization')
            for supplement in element.iterfind('Supplements/Supplement'):
                if _text(supplement, 'StatusName') != VALID or not _has_general(supplement):
                    continue
                org = supplement.find('ActualEducationOrganization')
                if org is None or not _text(org, 'Id'):
                    org = head
                if org is not None:
                    data = _org(org)
                    if data['registry_id'] and (data['full_name'] or data['short_name']):
                        yield data
        element.clear()


# ── Город из почтового адреса ─────────────────────────────────────────────
#
# Адреса в реестре пишут как придётся: «ул. Школьная, 18, с. Кемцы, Бологовский район,
# Тверская область, 171062», «356011 Ставропольский край Новоалександровский район
# пос.Горьковский пер.Школьный 2» (без запятых), «ЧЕЛЯБИНСК ГОРОД» и «ГОЙ-ЧУ С»
# (тип после названия), «Россия, Волгоград, ул. …» (без пометки). Порядок поиска:
# город с пометкой → другой населённый пункт с пометкой → тип после названия →
# известный город без пометки → название городского округа.

_LETTER = '[А-ЯЁа-яёA-Za-z]'
#: Пометка города. «г.о.» и «г.п.» — не город (городской округ, городское поселение).
_CITY_MARK = re.compile(r'(?:^|[\s,.;])(?<![пП]\.)(?:г\.(?!\s?[опт]\.)|г(?=\s)|город\s)\s*(' + _LETTER + r'[^,;]*)',
                        re.I)
#: Пометки прочих населённых пунктов. После пометки — буква: «д. 2» — это дом.
_PLACE_MARK = re.compile(
    r'(?:^|[\s,.;])(?:пгт\.?|п\.\s?г\.\s?т\.?|рп\.?|р\.\s?п\.?|рабочий\s+пос[её]лок|'
    r'сельский\s+пос[её]лок|курортный\s+пос[её]лок|г\.\s?п\.|гп\.?|сс?ело|сел\.|с\.|с(?=\s)|'
    r'пос\.|пос[её]лок|п\.|п(?=\s)|дер\.|деревня|д\.|д(?=\s)|ст-ца\.?|станица|ж/д\s+ст\.|'
    r'станция|ст\.|п/ст|хут\.|хутор|х\.|х(?=\s)|аул|а\.|аал|улус|у\.|сл\.|слобода|нп\.?|'
    r'пст\.?|рзд\.?|мест\.)\s*(' + _LETTER + r'[^,;]*)', re.I)
#: Тип после названия (ФИАС): «ЧЕЛЯБИНСК ГОРОД», «ГУДЕРМЕС Г.», «ГОЙ-ЧУ С».
_SUFFIX_MARK = re.compile(r'^(' + _LETTER + r'[^,;]*?)\s+(?:г\.?|город|с\.?|п\.?|пгт|д\.?|х\.?|'
                          r'ст-ца|аул)$', re.I)
_OKRUG = re.compile(r'(?:^|\s)(?:г\.\s?о\.|городской\s+округ|го)\s+(' + _LETTER + r'[^,;]*)', re.I)
#: Где название населённого пункта кончается: улица, дом, район, область…
_PLACE_END = re.compile(
    r'(?:\s+|\.|^)(?:ул\b|ул\.|улица|пер\.|переулок|пр\.|пр-кт|проспект|пл\.|площадь|шоссе|'
    r'мкр|микрорайон|м-н|кв-л|квартал|д\.\s*\d|дом\b|зд\.|здание|влд|стр\.|кв\.|р-н|р-на|'
    r'района|район|сельсовета|сельского|муниципальн|железнодорожной|центральная\s+усадьба|'
    r'' + _LETTER + r'+(?:ской|ского|цкой|цкого)\s+(?:области|района|края|р-на|республики)|'
    r'' + _LETTER + r'+(?:ая|ий|ой|ый)\s+(?:область|край|республика)).*$', re.I)
_NOT_A_NAME = re.compile(r'^(?:р-н|район|ул|мкр|микрорайон|дом|россия|российская)\b', re.I)
#: Части названия, которые пишутся со строчной («Ростов-на-Дону»).
_LOWER_PARTS = {'на', 'над', 'под', 'де', 'у', 'в', 'при'}


@lru_cache(maxsize=1)
def _known_cities():
    """norm → написание из `problems/data/cities_ru.json` (Москва, Ростов-на-Дону…)."""
    from problems.school_search import _cities
    return {name_norm: name for name_norm, name, _region, _pop in _cities()}


def _norm(text):
    return ' '.join((text or '').lower().replace('ё', 'е').split())


def _proper_case(name):
    """«СУХИНИЧИ» → «Сухиничи», «РОСТОВ-НА-ДОНУ» → «Ростов-на-Дону»."""
    known = _known_cities().get(_norm(name))
    if known:
        return known
    letters = [c for c in name if c.isalpha()]
    if not letters or any(c.islower() for c in letters):
        return name
    words = []
    for word in name.lower().split(' '):
        parts = word.split('-')
        parts = [p if (i and p in _LOWER_PARTS) else p[:1].upper() + p[1:]
                 for i, p in enumerate(parts)]
        words.append('-'.join(parts))
    return ' '.join(words)


def _clean_place(name):
    name = re.sub(r'\s+', ' ', name or '').strip(' .,"«»')
    # Обрывок пометки: «т. Белая Берёзка» из «п.г.т.», «П. Новоборовицкое» из «Г.П.».
    name = re.sub(r'^[А-ЯЁа-яё]{1,3}\.\s*', '', name)
    name = _PLACE_END.sub('', name)
    # «Кемцы 171062», «Москва (ЮЗАО)» — хвост после названия не нужен.
    name = re.split(r'\s+\d|\s*\(', name)[0].strip(' .,-"«»')
    if len(name) < 2 or _NOT_A_NAME.match(name) or name[0].isdigit():
        return ''
    return _proper_case(name)


def city_from_address(address, region=''):
    """Населённый пункт из почтового адреса реестра или ''."""
    region_n = _norm(region).replace('г. ', '')
    for federal in FEDERAL_CITIES:
        if region_n.startswith(_norm(federal)):
            return federal
    tokens = [re.sub(r'^\d{5,6}\s*', '', t.strip()) for t in re.split(r'[,;]', address or '')]
    tokens = [t for t in tokens if t]
    for token in tokens:
        found = _CITY_MARK.search(token)
        if found:
            name = _clean_place(found.group(1))
            if name:
                return name
    for token in tokens:
        found = _PLACE_MARK.search(token)
        if found:
            name = _clean_place(found.group(1))
            if name:
                return name
    for token in tokens:
        found = _SUFFIX_MARK.match(token)
        if found and not _OKRUG.search(token):
            name = _clean_place(found.group(1))
            if name:
                return name
    known = _known_cities()
    for token in tokens:
        if _norm(token) in known:
            return known[_norm(token)]
    for token in tokens:
        found = _OKRUG.search(token)
        if found:
            name = _clean_place(found.group(1))
            if name:
                return name
    return ''


# ── Название для подсказки ─────────────────────────────────────────────────

#: Организационно-правовая форма в начале: ГБОУ, МБОУ, МАОУ, ЧОУ, ПОУ, АНОО…
_LEGAL_ABBR = re.compile(r'^([А-ЯЁ]{2,7})(?:\s+|-|(?=[«"“„]))')
_LEGAL_ENDINGS = ('ОУ', 'ОО', 'ОЧУ', 'ЧУ', 'ДО', 'ПО', 'НО', 'УДО')
_LEGAL_SET = {'АНО', 'АНОО', 'ОАНО', 'ЧОУ', 'НОУ', 'ЧУОО', 'НОЧУ', 'БОУ', 'КОУ', 'ОУ'}
#: Короткое название на деле полное: «муниципальное бюджетное … учреждение …».
_VERBOSE = re.compile(r'^(?:муниципальн|государственн|частн|федеральн|негосударственн|автономн|'
                      r'некоммерческ|областн|краев|республиканск|бюджетн|казенн|казённ)', re.I)
_QUOTED = re.compile(r'[«"“„]([^«»"“”„]+)[»"”“]')
#: Хвосты: «г. Москвы», «города Казани», «Г.О. ДОНЕЦК», «М.О.», «Орловского
#: муниципального округа», «КАЛИНИНСКОГО РАЙОНА САНКТ-ПЕТЕРБУРГА».
_TAILS = (
    re.compile(r'[\s,]+(?:г\.(?!\s?[опО]\.)|города|гор\.)\s*' + _LETTER + r'.*$', re.I),
    re.compile(r'[\s,]+(?:г\.\s?о\.|м\.\s?о\.|м\.\s?р-н|мо|го)(?:\s.*|)$', re.I),
    re.compile(r'[\s,]+' + _LETTER + r'+(?:ого|его|ой)\s+(?:муниципального\s+|городского\s+)?'
               r'(?:района|округа|области|края|республики|поселения)\b.*$', re.I),
)
#: Сокращения, которые остаются прописными при переводе КАПСЛОКА.
_ABBR = {'СОШ', 'ООШ', 'НОШ', 'СШ', 'ОШ', 'ЦО', 'ЦОД', 'РФ', 'СССР', 'МО', 'ГО', 'ИЭЛ', 'ФМЛ',
         'ЦДО', 'ОЦ', 'ВСОШ', 'СОШИ', 'ООШИ', 'НШ', 'НШДС', 'ОК', 'УВК', 'ЦПМ', 'ЦЭО', 'ЛИТ'}


def _decaps(name):
    """«ШКОЛА № 71 ИМ. П.Ф. БАТУЛЫ» → «Школа № 71 им. П.Ф. Батулы»."""
    letters = [c for c in name if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return name
    out, cap_next = [], True
    for word in name.split(' '):
        core = word.strip('«»"().,')
        low = word.lower()
        # «им.», «с.», «пгт.» — строчные, следующее слово (фамилия, название села) — с прописной.
        if core.upper() in ('ИМ', 'ИМЕНИ', 'С', 'П', 'Д', 'Г', 'Х', 'ПГТ', 'ПОС', 'СТ', 'СЕЛО', 'АУЛ'):
            out.append(low)
            cap_next = True
            continue
        # Сокращение: из списка, инициалы или слово в 3–4 буквы почти без гласных (ЛДК, МОК).
        if (core in _ABBR or re.fullmatch(r'(?:[А-ЯЁ]\.)+[А-ЯЁ]?', core)
                or (3 <= len(core) <= 4 and core.isalpha()
                    and sum(c in 'АЕЁИОУЫЭЮЯ' for c in core) <= 1)):
            out.append(word)
            cap_next = core not in _ABBR
            continue
        if cap_next and any(c.isalpha() for c in low):
            at = next(i for i, c in enumerate(low) if c.isalpha())
            low = low[:at] + low[at].upper() + low[at + 1:]
            cap_next = False
        out.append(low)
    return ' '.join(out)


def _only_abbr_and_city(prefix):
    """«МБОУ», «БОУ г. Омска», «ГБОУ ПО» — только сокращения и, может, «г. Город»."""
    words = prefix.replace('г.', ' г. ').split()
    if 'г.' in words:
        at = words.index('г.')
        if len(words) - at > 2:
            return False
        words = words[:at]
    # «СПб ГБПОУ» — тоже сокращения (две и больше прописных).
    return all(re.fullmatch(r'[А-ЯЁ]{1,7}', w)
               or (len(w) <= 7 and sum(c.isupper() for c in w) >= 2) for w in words)


def human_name(short_name, full_name=''):
    """«ГБОУ Школа № 57 г. Москвы» → «Школа № 57».

    Возвращает (название, это_полное): если короткого нет — полное (как есть, его
    подсказка показывает мелко).
    """
    base = re.sub(r'\s+', ' ', (short_name or '').replace('&quot;', '"')).strip()
    if not base:
        return re.sub(r'\s+', ' ', (full_name or '')).strip(), True
    name = base
    if _VERBOSE.match(name):
        quoted = _QUOTED.search(full_name or '') or _QUOTED.search(name)
        if quoted:
            name = quoted.group(1).strip()
    for _ in range(3):
        found = _LEGAL_ABBR.match(name)
        if not found:
            break
        abbr = found.group(1)
        if abbr in _ABBR or not (abbr in _LEGAL_SET or abbr.endswith(_LEGAL_ENDINGS)):
            break
        name = name[found.end():].strip()
    # Название целиком в кавычках, может быть с вложенными («Лицей «Вторая школа»»)
    # и с хвостом после них: берём всё до ПОСЛЕДНЕЙ закрывающей кавычки.
    outer = re.match(r'^[«"“„](.*)[»"”“]', name)
    quoted = None if outer else _QUOTED.search(name)
    if outer:
        name = outer.group(1).strip()
        name = re.sub(r'[“„"]([^"“”„]*)[”"]', r'«»', name)
        # Кавычек поровну: «Лицей «Надежда» (в реестре одна закрывающая на две) → «…»».
        name = name + '»' * max(0, name.count('«') - name.count('»'))
        while name.count('»') > name.count('«') and name.endswith('»'):
            name = name[:-1]
    elif quoted:
        prefix, inner = name[:quoted.start()].strip(), quoted.group(1).strip()
        # До кавычек только сокращения и «г. Омска» — название внутри кавычек.
        # ⚠️ Проверка по словам, а не регуляркой `(?:[А-ЯЁ]{1,7}\s*)*`: вложенный
        # квантификатор на длинном префиксе капслоком перебирает экспоненциально
        # (на реестре 29.10.2026 разбор встал намертво).
        if not prefix or _only_abbr_and_city(prefix):
            name = inner
        else:
            name = '%s «%s»' % (prefix, inner)
    for tail in _TAILS:
        shorter = tail.sub('', name).strip(' ,-')
        if len(shorter) >= 3:
            name = shorter
    name = re.sub(r'№\s*(\d)', r'№ \1', name).strip(' ,-')
    name = _decaps(name)
    # «школа № 57» (так в реестре) → «Школа № 57».
    if name[:1].islower():
        name = name[0].upper() + name[1:]
    return (name or base), False


def merge(orgs):
    """Склеить повторы одной организации по `registry_id` (последняя запись главнее)."""
    merged = {}
    for org in orgs:
        merged[org['registry_id']] = org
    return merged


def to_school_fields(org):
    """Поля `School` из записи реестра."""
    from problems.school_search import number_in_name

    name, is_full = human_name(org['short_name'], org['full_name'])
    return {
        'registry_id': org['registry_id'][:64],
        'inn': org['inn'][:12],
        'kpp': org['kpp'][:9],
        'name': (org['full_name'] or name)[:300],
        'short_name': ('' if is_full else name)[:200],
        'number': number_in_name(name),
        'city': city_from_address(org['address'], org['region'])[:120],
        'region': org['region'][:200],
        'is_branch': org['is_branch'],
    }


def read_file(path):
    """Все школы из файла реестра: {registry_id: поля School}."""
    stream, close = open_xml(path)
    try:
        return {key: to_school_fields(org) for key, org in merge(iter_raoo(stream)).items()}
    finally:
        close()


def read_bytes(payload):
    """То же для байтов в памяти (тесты)."""
    stream = io.BytesIO(payload)
    if zipfile.is_zipfile(stream):
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            name = [n for n in archive.namelist() if n.lower().endswith('.xml')][0]
            with archive.open(name) as inner:
                return {k: to_school_fields(o) for k, o in merge(iter_raoo(inner)).items()}
    stream.seek(0)
    return {k: to_school_fields(o) for k, o in merge(iter_raoo(stream)).items()}
