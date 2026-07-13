# -*- coding: utf-8 -*-
"""
fix_vsosh_tounicode — лечит PDF ВсОШ-региона с битой текстовой кодировкой
(2024: CID-шрифты Identity-H БЕЗ ToUnicode — извлекаемый «текст» состоит из
сырых glyph ID вместо букв).

Принцип. Все PDF линейки (2023–2025) сверстаны одними шрифтами (Libertinus),
а Identity-H означает «код символа = CID = глиф исходного шрифта». В файлах
2023/2025 ToUnicode есть → через get_texttrace() снимаем пары (глиф → юникод)
и получаем референсные карты. В целевом файле теми же глифами набран текст —
вписываем в каждый шрифт корректный /ToUnicode CMap и сохраняем PDF рядом.
После этого обычное извлечение текста (и parse_vsosh_region) работает как ни
в чём не бывало.

Осторожности:
- В одном документе бывает ДВА одноимённых сабсета с разной нумерацией
  глифов (документ склеен из «теста» и «задач» разных сборок). Карты
  строятся по-сабсетно; референсные страницы, где семейство представлено
  двумя сабсетами сразу, пропускаются.
- Целевой сабсет получает карту-кандидата только если она покрывает все его
  глифы; из кандидатов выбирается тот, чей декод даёт связный русский текст
  (минимум «рваных» слов со сменой регистра внутри). Неоднозначность —
  честная ошибка, файл не пишется.
- Глифы без расшифровки отображаются в U+FFFD — дальше их ловят шлюзы
  качества (check_vsosh_gates) на уровне вопросов.

Запуск: ./venv/bin/python manage.py fix_vsosh_tounicode --year 2024
Выход:  test_answers_<класс>.pdf перезаписывается исправленной копией
        (оригиналы скачанных файлов не трогаются).
"""
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

REFERENCE_PDFS = [
    'materials/vsosh_region/2025/test_answers_9.pdf',
    'materials/vsosh_region/2025/test_answers_10.pdf',
    'materials/vsosh_region/2025/test_answers_11.pdf',
    'materials/vsosh_region/2023/test_answers_9.pdf',
    'materials/vsosh_region/2023/test_answers_10.pdf',
    'materials/vsosh_region/2023/test_answers_11.pdf',
]

# Глифы, которых нет в референсах 2023/2025. Каждый ПРОВЕРЕН ВИЗУАЛЬНО по
# рендеру страницы 2024 (глиф 93 в ASCII-фолбэке маскировался под «]», на
# рендере это «|» — модуль в 1/|ε|). Ключ — год, чтобы карты не протекали
# на другие годы с иной нумерацией глифов.
# Сдвиг версии шрифта: нумерация глифов сабсета отличается от референсной
# на константу — но только в старшем диапазоне (кириллица; пунктуация и
# ASCII не сдвинуты: '(' и дефис переноса декодировались верно ДО сдвига).
# У курсива 2021 (файл 11 класса) кириллические гиды (≥900) на 1 МЕНЬШЕ
# референсных: ref[gid+1] даёт «Премии Шведского…» и «поведенческой
# экономикой» (сверено с рендером; языковой скоринг сдвинутую кириллицу
# не ловит — она остаётся «связной»). Формат: {семейство: (min_gid, сдвиг)},
# карта для gid ≥ min_gid строится как ref[gid+сдвиг].
MANUAL_SHIFTS = {
    2021: {'LibertinusSerif-Italic': (900, 1)},
}

MANUAL_GLYPHS = {
    2024: {
        'LibertinusMath-Regular': {
            3406: '\U0001D700',  # 𝜀 — эластичность («по цене 𝜀 = −2»)
            2726: '\U0001D43E',  # 𝐾 — «Q = √(KL)»
            2729: '\U0001D441',  # 𝑁 — «NPV = …»
            2717: '\U0001D435',  # 𝐵 — «MSB = 100 − Q»
            93: '|',             # модуль: 1/|ε|
        },
        'Asana-Math': {
            761: '√',            # радикал («10/√Q», «√KL»)
        },
        'LibertinusSerif-Regular': {
            42: 'I',             # «XXIX» в титуле
            47: 'N',             # «В городе N-ске» (3.3); слэш титула — гид 16.
            #                      Ночная разметка 47='/' была ошибкой: кроп
            #                      попал на колонтитул Montserrat. Сверено по
            #                      рендеру строки вопроса.
            54: 'U',             # «стандартный U-образный вид» (2.2) —
            #                      единственное вхождение во всех трёх файлах,
            #                      сверено рендером ×3; ночная разметка «6»
            #                      была ошибкой кропа (ASCII-порядок гидов
            #                      тоже даёт chr(0x20+54-1)='U')
            60: '[',             # интервалы в вариантах 1.4: «[0 %; 5 %)»
            62: ']',             # «[15 %; 20 %]»
            72: 'g', 83: 'r', 84: 's', 85: 't', 86: 'u', 87: 'v',
            #                    «rosstat.gov.ru» в условии 1.4
            967: 'Я',            # «Яков и Иван» (2.1)
        },
        'LibertinusSerif-Italic': {
            983: 'ы',            # курсивное «убывающей» (2.5)
        },
    },
    # 2021: битый только 11 класс (ToUnicode есть, но врёт). Старая версия
    # шрифтов — часть глифов сдвинута относительно референсов 2023/2025.
    # Каждый проверен визуально по рендеру страницы.
    2021: {
        'LibertinusSerif-Regular': {
            5: '$',              # «дефицитом 2 млн $»
            47: 'N',             # «В городе N располагается…»
            1750: '–',           # '––' в тексте (постпроцесс склеит в «—»)
            1751: '—',           # «Ключевая ставка — другой инструмент»
            1861: '№',           # «Лекарство №1»
        },
        # курсив: кириллический блок сдвинут на 1 против референса —
        # лечится MANUAL_SHIFTS; ручные глифы ниже согласуются со сдвигом
        # (заглавные и 'э'/'ч' — дыры референса, каждая сверена рендером:
        # 984='э' «по экономическим наукам», 936='Н' «А. Нобеля»)
        'LibertinusSerif-Italic': {
            923: 'А', 933: 'К', 936: 'Н', 947: 'Ш', 955: 'а',
            984: 'э',
        },
        'LibertinusMath-Regular': {
            32: '?',             # ASCII-блок глифов: gid = код − 0x1F
            1770: '…',           # «MC(1) + MC(2) + … + MC(q)»
            1952: '→',           # «49 → min»
            1995: '∈',           # «ставке t ∈ (0; 90)»
            2004: '−',           # минус: «(y(2/3) − y(1/3))»
            2165: '⋅',           # «w₁ ⋅ L₁»
            2166: '⋆',           # «q₂⋆ = Q − 3»
            # Блок математического курсива: заглавные 𝐴=2599…(𝐴+i);
            # строчные 𝑎=2625…, слот «h» пропущен (ℎ живёт в Letterlike).
            # Якоря проверены по рендерам: AVC, P_A/P_B, MC=2q, «за N»,
            # «за Q», TR₀, T_d, q_d=90−p, q_s=p/2, «равна r», «ставке t»,
            # L_s=w, y=x³.
            2599: '\U0001D434',  # 𝐴
            2600: '\U0001D435',  # 𝐵
            2601: '\U0001D436',  # 𝐶
            2610: '\U0001D43F',  # 𝐿
            2611: '\U0001D440',  # 𝑀
            2612: '\U0001D441',  # 𝑁
            2614: '\U0001D443',  # 𝑃
            2615: '\U0001D444',  # 𝑄
            2616: '\U0001D445',  # 𝑅
            2618: '\U0001D447',  # 𝑇
            2620: '\U0001D449',  # 𝑉
            2628: '\U0001D451',  # 𝑑
            2629: '\U0001D452',  # 𝑒
            2639: '\U0001D45D',  # 𝑝
            2640: '\U0001D45E',  # 𝑞
            2641: '\U0001D45F',  # 𝑟
            2642: '\U0001D460',  # 𝑠
            2643: '\U0001D461',  # 𝑡
            2646: '\U0001D464',  # 𝑤
            2647: '\U0001D465',  # 𝑥
            2648: '\U0001D466',  # 𝑦
            # Скрипт-кегли (оптические варианты для степеней/индексов) —
            # раскладка сверена по глифовой структуре дробей 1/(1+r) и т.п.
            3551: '2', 3552: '3', 3553: '1', 3554: '0',
            3562: '+', 3565: '(', 3566: ')',
            3610: '{',           # фрагмент фигурной скобки кусочной функции
        },
        'Asana-Math': {
            1527: '⩽',           # «TC(Q) ⩽ Q²»
            1528: '⩾',           # «для любого Q ⩾ 0»
        },
    },
}

# MyriadPro-SemiboldIt (2021, 11 класс): этим шрифтом набраны маркеры
# «Комментарий.» и «Ответ:». Кириллица — сплошным блоком А=630…я=693
# (якоря К,о,м,м,е,н,т,а,р,и,й проверены по рендеру и взаимной
# согласованности позиций). ASCII — Adobe-порядок глифов: gid = код − 31
# (пробел=1, «:»=27 — сверено по маркеру «Ответ:»).
_MYRIAD_2021 = {630 + i: chr(0x410 + i) for i in range(64)}
_MYRIAD_2021.update({code - 31: chr(code) for code in range(32, 127)})
MANUAL_GLYPHS[2021]['MyriadPro-SemiboldIt'] = _MYRIAD_2021

WORD_RE = re.compile(r'\S+')
CYR_LOWER = set('абвгдеёжзиклмнопрстуфхцчшщъыьэюя')
CYR_UPPER = set(c.upper() for c in CYR_LOWER)


def norm_family(name):
    """Имя шрифта без тега сабсета и суффикса кодировки."""
    name = name.split('+')[-1]
    if name.endswith('-Identity-H'):
        name = name[:-len('-Identity-H')]
    # старые сборки называют шрифт без «-Regular» (LibertinusMath, 2021)
    if name == 'LibertinusMath':
        name = 'LibertinusMath-Regular'
    return name


def span_family(span):
    """Каноническое семейство для спана texttrace.

    ⚠ texttrace обрезает имя шрифта (~31 символ): «VCMFWA+LibertinusSerif-
    SemiboldItalic» приходит как «LibertinusSerif-Semibold» — глифы жирного
    курсива иначе загрязняют карту обычного Semibold (и у них конфликтующая
    нумерация!). Курсив восстанавливаем по italic-биту flags (бит 1)."""
    fam = norm_family(span['font'])
    # «It» покрывает и полный суффикс Italic, и усечённый (MyriadPro-SemiboldIt)
    if span['flags'] & 2 and 'It' not in fam:
        fam += 'Italic'
    return fam


def page_family_tags(doc, pno):
    """Семейство → [полные имена сабсетов] на странице."""
    fams = {}
    for f in doc.get_page_fonts(pno):
        full = f[3]
        fams.setdefault(norm_family(full), set()).add(full)
    return fams


def collect_reference_maps(paths):
    """Референсные карты: {полное имя сабсета: {глиф: юникод}}.
    Страницы, где семейство представлено ≥2 сабсетами, пропускаются —
    texttrace не говорит, какой из них рисовал спан."""
    import fitz
    subset_maps = {}
    for path in paths:
        doc = fitz.open(path)
        for pno in range(len(doc)):
            fams = page_family_tags(doc, pno)
            ambiguous = {fam for fam, tags in fams.items() if len(tags) > 1}
            tag_of = {fam: next(iter(tags)) for fam, tags in fams.items()
                      if len(tags) == 1}
            for span in doc[pno].get_texttrace():
                fam = span_family(span)
                if fam in ambiguous or fam not in tag_of:
                    continue
                m = subset_maps.setdefault((path, tag_of[fam]), {})
                for uni, gid in ((c[0], c[1]) for c in span['chars']):
                    m[gid] = chr(uni)
        doc.close()
    return subset_maps


def merge_versions(subset_maps):
    """Сабсеты одного семейства, согласные на общих глифах, сливаются в
    «версию». Результат: {семейство: [карта_версии, ...]}."""
    by_family = {}
    for (path, tag), m in subset_maps.items():
        by_family.setdefault(norm_family(tag), []).append(m)
    versions = {}
    for fam, maps_list in by_family.items():
        groups = []
        for m in maps_list:
            for g in groups:
                if all(g[k] == v for k, v in m.items() if k in g):
                    g.update(m)
                    break
            else:
                groups.append(dict(m))
        versions[fam] = groups
    return versions


def garbage_score(text):
    """Число «рваных» слов: смена регистра внутри слова, нерусский мусор."""
    bad = 0
    for w in WORD_RE.findall(text):
        letters = [c for c in w if c.isalpha()]
        if not letters:
            continue
        switches = sum(1 for a, b in zip(letters, letters[1:])
                       if a in CYR_LOWER and b in CYR_UPPER)
        non_cyr = sum(1 for c in letters
                      if c not in CYR_LOWER and c not in CYR_UPPER
                      and not c.isascii())
        if switches or non_cyr:
            bad += 1
    return bad


def build_cmap_stream(mapping):
    """Глиф→юникод → содержимое /ToUnicode CMap (bfchar-блоками по 100)."""
    def uhex(s):
        return ''.join(f'{b:04X}' for ch in s
                       for b in _utf16_units(ch))
    entries = [f'<{gid:04X}> <{uhex(uni)}>' for gid, uni in sorted(mapping.items())]
    blocks = []
    for i in range(0, len(entries), 100):
        chunk = entries[i:i + 100]
        blocks.append(f'{len(chunk)} beginbfchar\n'
                      + '\n'.join(chunk) + '\nendbfchar')
    body = '\n'.join(blocks)
    return f'''/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo <</Registry (Adobe) /Ordering (UCS) /Supplement 0>> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
{body}
endcmap
CMapName currentdict /CMap defineresource pop
end
end'''.encode('utf-8')


def _utf16_units(ch):
    code = ord(ch)
    if code < 0x10000:
        return [code]
    code -= 0x10000
    return [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]


class Command(BaseCommand):
    help = ('Вписывает корректные ToUnicode в PDF ВсОШ-региона с битой '
            'кодировкой (карты глифов снимаются с соседних годов)')

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True)

    def handle(self, *args, **options):
        import fitz

        year = options['year']
        folder = Path('materials/vsosh_region') / str(year)
        if not folder.is_dir():
            raise CommandError(f'Нет папки {folder}')

        self.stdout.write('Снимаю референсные карты глифов (2023, 2025)…')
        subset_maps = collect_reference_maps(REFERENCE_PDFS)
        versions = merge_versions(subset_maps)
        for fam, groups in sorted(versions.items()):
            self.stdout.write(f'  {fam}: версий {len(groups)}, глифов '
                              + '/'.join(str(len(g)) for g in groups))
        manual = MANUAL_GLYPHS.get(year, {})
        shifts = MANUAL_SHIFTS.get(year, {})

        for grade in (9, 10, 11):
            pdf = folder / f'test_answers_{grade}.pdf'
            if not pdf.exists():
                raise CommandError(f'Нет файла {pdf}')
            self._fix_one(fitz, pdf, versions, manual, shifts)

    def _fix_one(self, fitz, pdf, versions, manual, shifts):
        doc = fitz.open(pdf)

        # Сам факт наличия ToUnicode ничего не гарантирует: у 11 класса 2021
        # CMap есть, но маппит в мусор. Критерий здоровья — документный:
        # текст первой страницы читается по-русски → шрифты с ToUnicode не
        # трогаем; не читается → перезаписываем карты всем.
        page1 = doc[0].get_text()
        letters = [c for c in page1 if c.isalpha()]
        cyr = sum(1 for c in letters if 'Ѐ' <= c <= 'ӿ')
        doc_readable = bool(letters) and cyr / len(letters) > 0.5
        healthy = set()
        if doc_readable:
            for pno in range(len(doc)):
                for f in doc.get_page_fonts(pno):
                    t, _ = doc.xref_get_key(f[0], 'ToUnicode')
                    if t == 'xref':
                        healthy.add(f[3])
        all_tags = {f[3] for pno in range(len(doc))
                    for f in doc.get_page_fonts(pno)}
        if healthy == all_tags:
            doc.close()
            self.stdout.write(self.style.SUCCESS(
                f'  {pdf.name}: текст читается, у всех шрифтов есть '
                'ToUnicode — пропуск'))
            return

        # Использованные глифы каждого сабсета: с texttrace постранично,
        # тег сабсета берём из шрифтов страницы (однозначен на странице).
        used = {}      # полное имя сабсета -> set(глифов)
        pages_of = {}  # (полное имя, глиф) -> set(страниц) — для отчёта
        xref_of = {}   # полное имя сабсета -> xref
        skipped_pages = []
        for pno in range(len(doc)):
            fams = page_family_tags(doc, pno)
            for f in doc.get_page_fonts(pno):
                xref_of.setdefault(f[3], f[0])
            ambiguous = {fam for fam, tags in fams.items() if len(tags) > 1}
            if ambiguous:
                skipped_pages.append((pno + 1, sorted(ambiguous)))
            tag_of = {fam: next(iter(tags)) for fam, tags in fams.items()
                      if len(tags) == 1}
            for span in doc[pno].get_texttrace():
                fam = span_family(span)
                if fam in ambiguous or fam not in tag_of:
                    continue
                tag = tag_of[fam]
                for c in span['chars']:
                    used.setdefault(tag, set()).add(c[1])
                    pages_of.setdefault((tag, c[1]), set()).add(pno + 1)
        for pno, fams in skipped_pages:
            self.stdout.write(self.style.WARNING(
                f'  {pdf.name} стр. {pno}: два сабсета {fams} — глифы '
                'страницы не декодируются (останутся U+FFFD)'))

        # Подбор версии карты на сабсет
        chosen = {}
        for tag, gids in used.items():
            if tag in healthy:
                continue
            fam = norm_family(tag)
            candidates = []
            for m in versions.get(fam, []):
                covered = gids & set(m)
                text = ''.join(m.get(g, '�') for g in sorted(gids))
                candidates.append((len(gids - set(m)), garbage_score(text), m))
            garbage = 0
            if candidates:
                candidates.sort(key=lambda c: (c[0], c[1]))
                miss, garbage, best = candidates[0]
                if (len(candidates) > 1
                        and candidates[1][:2] == (miss, garbage)):
                    raise CommandError(
                        f'{pdf.name}: {tag} — неоднозначный выбор версии карты')
                mapping = dict(best)
                if fam in shifts:
                    min_gid, s = shifts[fam]
                    mapping = {g: (best[g + s] if g >= min_gid
                                   else best.get(g))
                               for g in gids
                               if (g + s in best if g >= min_gid
                                   else g in best)}
                    self.stdout.write(f'  {pdf.name}: {tag} — сдвиг версии '
                                      f'{s:+d} для гидов ≥{min_gid}')
            else:
                # референса нет — карта только из ручных глифов + U+FFFD,
                # чтобы сырые гиды не маскировались под честные символы
                mapping = {}
            # Ручные глифы (проверены визуально) — только поверх пробелов
            for gid, ch in manual.get(fam, {}).items():
                if gid in mapping and mapping[gid] != ch:
                    raise CommandError(
                        f'{pdf.name}: {tag} глиф {gid} — ручное значение '
                        f'{ch!r} противоречит референсу {mapping[gid]!r}')
                mapping[gid] = ch
            unmapped = gids - set(mapping)
            # Непокрытые глифы — явный U+FFFD: иначе MuPDF отдаёт chr(gid)
            # и мусор маскируется под безобидные ASCII/греческие символы.
            # С FFFD парсер честно отправляет вопрос в unparsed.
            for gid in unmapped:
                mapping[gid] = '�'
            chosen[tag] = mapping
            note = ('полное покрытие' if not unmapped
                    else f'{len(unmapped)} глифов без расшифровки (U+FFFD)')
            self.stdout.write(f'  {pdf.name}: {tag} → карта '
                              f'({len(mapping)} глифов, {note}, мусор {garbage})')
            for gid in sorted(unmapped):
                pages = sorted(pages_of.get((tag, gid), ()))
                self.stdout.write(self.style.WARNING(
                    f'      без расшифровки: глиф {gid} (стр. '
                    f'{", ".join(map(str, pages))})'))

        # Вписываем ToUnicode
        for tag, mapping in chosen.items():
            stream = build_cmap_stream(mapping)
            new_xref = doc.get_new_xref()
            doc.update_object(new_xref, '<<>>')
            doc.update_stream(new_xref, stream, new=True)
            doc.xref_set_key(xref_of[tag], 'ToUnicode', f'{new_xref} 0 R')

        tmp = pdf.with_suffix('.fixed.pdf')
        doc.save(str(tmp), deflate=True)
        doc.close()
        tmp.replace(pdf)

        # Контроль: текст читается
        doc = fitz.open(pdf)
        page1 = doc[0].get_text()
        ok = ('лимпиада' in page1 or 'кономик' in page1)
        n_bad = page1.count('�')
        doc.close()
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(style(
            f'  {pdf.name}: сохранён; страница 1 читается: {ok}, '
            f'U+FFFD на стр.1: {n_bad}'))
