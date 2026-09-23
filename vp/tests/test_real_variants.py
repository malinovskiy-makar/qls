"""Сторож содержимого настоящих вариантов: `data/vp/vp-1tur-*.yaml`.

`import_vp` проверяет устройство варианта (44 задания, 100 баллов, номера),
но пропускает дефекты разметки, которые ученик видит сразу:

* в заданиях 31–35 потерян пропуск «______»: предложение читается без места
  для слова;
* в тексте остались «математические» буквы Unicode (𝑄, 𝑃, 𝑀𝑅) вместо формул
  `$…$`: KaTeX их не трогает, и на экране каша;
* непарный знак `$`: формула до конца строки показывается сырой
  (`$$…$$` – законная выключная формула, она не в счёт);
* в разборе остался колонтитул «Имя Фамилия, 18.09.2026» или заголовок
  соседнего блока «Задания 41–42»;
* ответ змейки повторяет слово, уже напечатанное перед полем (prefix) или
  после него (suffix): ученик пишет «Оукена», а эталон «закономерность Оукена»;
* разрыв цепочки змейки: `import_vp` без `--strict-chain` его только
  предупреждает.

Черновики из DRAFTS не проверяются, кроме шапки: её видит персонал.
Тест не ходит в базу: читает файлы и разбирает их тем же `vp.loader`,
что и `import_vp`.

Отдельно: в шапке варианта (название и остальное, кроме `items`) длинного
тире нет — она видна на сайте (карточки `/vp/variants/`, интро, `<title>`
вкладки), а `scripts/check_em_dash.py` файлы `data/vp` не читает.
"""
import pathlib
import re

import yaml
from django.test import SimpleTestCase

from vp.loader import find_chain_breaks, normalize

DATA = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'vp'
DRAFTS = {'vp-1tur-2026-olmat-9-10-v4.yaml'}  # черновик: скрыт, разметку не чинили
MIN_FILES = 18  # опубликованных вариантов в data/vp на 23.09.2026

GAP_RUN = re.compile(r'_{3,}')
MATH_ALNUM = re.compile('[\U0001D400-\U0001D7FF]')
COLONTITLE = re.compile(r'[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+,\s*\d{2}\.\d{2}\.20\d{2}')
BLOCK_HEADER = re.compile(r'Задания\s+\d')
DISPLAY_MATH = re.compile(r'\$\$.+?\$\$', re.S)
TEXT_FIELDS = ('intro', 'statement', 'prefix', 'answer', 'suffix',
               'figure_caption', 'figure_source', 'solution')


def variant_files():
    return [p for p in sorted(DATA.glob('vp-1tur-*.yaml')) if p.name not in DRAFTS]


def load(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def texts(item):
    """(поле, строка) для всех текстов задания, включая options и accepted."""
    for key in TEXT_FIELDS:
        value = item.get(key)
        if isinstance(value, str):
            yield key, value
    for key in ('options', 'accepted'):
        for i, value in enumerate(item.get(key) or [], start=1):
            if isinstance(value, str):
                yield f'{key}[{i}]', value


def words(text):
    return str(text or '').lower().replace('ё', 'е').split()


class RealVariantsContentTests(SimpleTestCase):
    maxDiff = None

    def setUp(self):
        self.files = variant_files()

    def each_item(self):
        for path in self.files:
            for item in load(path)['items']:
                yield path.name, item

    def test_files_found(self):
        self.assertGreaterEqual(len(self.files), MIN_FILES)

    def test_header_has_no_em_dash(self):
        """Шапка варианта (всё, кроме items) видна на сайте: карточки /vp/variants/,
        интро, <title> вкладки. Длинного тире там нет, а сканер check_em_dash.py
        файлы data/vp не читает. Черновики тоже: их видит персонал. Тексты заданий
        не проверяем: это материал олимпиады."""
        files = sorted(DATA.glob('vp-1tur-*.yaml'))
        # Пустая маска прошла бы молча: ноль файлов – ноль нарушений.
        self.assertGreaterEqual(len(files), MIN_FILES + len(DRAFTS))
        bad = [f'{path.name}: {key}'
               for path in files
               for key, value in load(path).items()
               if key != 'items' and isinstance(value, str) and '—' in value]
        self.assertEqual(bad, [])

    def test_gapfill_has_exactly_one_gap(self):
        problems = []
        for name, item in self.each_item():
            if 31 <= item['n'] <= 35:
                runs = GAP_RUN.findall(str(item.get('statement', '')))
                if runs != ['______']:
                    problems.append(f'{name} №{item["n"]}: пропуски {runs}')
        self.assertEqual(problems, [])

    def test_no_unicode_math_letters(self):
        problems = [f'{name} №{item["n"]} {field}'
                    for name, item in self.each_item()
                    for field, text in texts(item) if MATH_ALNUM.search(text)]
        self.assertEqual(problems, [])

    def test_dollars_are_paired(self):
        # $$…$$ – законная формула на отдельной строке (демоверсия, №43);
        # после неё одиночных знаков $ должно остаться чётное число.
        problems = [f'{name} №{item["n"]} {field}'
                    for name, item in self.each_item()
                    for field, text in texts(item)
                    if DISPLAY_MATH.sub('', text).count('$') % 2]
        self.assertEqual(problems, [])

    def test_no_page_junk(self):
        problems = []
        for name, item in self.each_item():
            for field, text in texts(item):
                if COLONTITLE.search(text):
                    problems.append(f'{name} №{item["n"]} {field}: колонтитул')
            if BLOCK_HEADER.search(str(item.get('solution') or '')):
                problems.append(f'{name} №{item["n"]}: заголовок блока в разборе')
        self.assertEqual(problems, [])

    def test_snake_answer_does_not_repeat_printed_words(self):
        problems = []
        for name, item in self.each_item():
            if item.get('block') != 'snake':
                continue
            answer, prefix, suffix = (words(item.get(k)) for k in ('answer', 'prefix', 'suffix'))
            if suffix and answer[-len(suffix):] == suffix:
                problems.append(f'{name} №{item["n"]}: ответ кончается на suffix «{item["suffix"]}»')
            if prefix and answer[:len(prefix)] == prefix:
                problems.append(f'{name} №{item["n"]}: ответ начинается с prefix «{item["prefix"]}»')
        self.assertEqual(problems, [])

    def test_snake_chain_is_closed(self):
        problems = []
        for path in self.files:
            parsed = normalize(load(path))
            problems += [f'{path.name}: {b}' for b in find_chain_breaks(parsed.items)]
        self.assertEqual(problems, [])
