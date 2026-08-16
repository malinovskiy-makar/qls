"""
Таблицы всей платформы (ревью 16.08, фаза 6).

6.1 Столбец, который не текстовый, выравнивается ПО ЦЕНТРУ — и заголовок,
    и значения. Владелец: «Тип находится левее всех значений в ячейках».
    Правило было, но жило в наборе деталей кабинета, а каталог — экран
    ученика — набор не подключает.
6.2 На экране занятия таблица учеников стоит ВЫШЕ матрицы «ученики × темы».
6.3 Первый столбец матрицы закреплён.

⚠️ СОВПАДЕНИЕ ЦЕНТРОВ ПРОВЕРЯЕТ БРАУЗЕР (`scripts/r16_tables_probe.js`):
питон видит атрибут, но не видит координат. Здесь — что атрибут есть у
каждого нетекстового столбца и что правило доезжает до обеих сторон сайта.
"""
import glob
import os
import re

from django.template.loader import render_to_string
from django.test import TestCase

# Экраны с таблицами и столбцы, которые обязаны быть размечены.
# Текстовые столбцы («Ученик», «Работа», «Тема») сюда НЕ входят: они
# читаются слева, и центрировать их нельзя.
NUMERIC_HEADS = (
    'Открытых задач', 'Средний балл', 'Тестов', 'Верных', 'Решено',
    'Доля верных', 'Сдано работ', 'Попыток', 'Доля', 'Балл',
    '% верных задач', '% верных тестов', 'Оценка', 'Статус', 'Сложн.',
    'Реш.',
)


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as handle:
        return handle.read()


def screens():
    """Все шаблоны с таблицами — обе стороны сайта."""
    found = []
    for root in ('teacher/templates', 'student/templates',
                 'problems/templates/platform', 'catalog/templates'):
        for path in glob.glob(root + '/**/*.html', recursive=True):
            text = read(path)
            if '<th' in text:
                found.append((path, text))
    return found


class ColumnsAreMarkedTests(TestCase):
    """6.1 — у каждого нетекстового столбца есть признак."""

    def test_every_numeric_head_is_marked(self):
        misses = []
        for path, text in screens():
            if 'admin' in path:
                # Админка Django — не экран продукта, её вид задаёт Django.
                continue
            # ⚠️ `<th([^>]*)>` ловит и `<thead>`: «ead» становится списком
            # атрибутов, а содержимым — первая ячейка шапки. Требуем либо
            # пробел после `th`, либо сразу закрывающую скобку.
            for head in re.finditer(r'<th(\s[^>]*)?>(.*?)</th>', text, re.S):
                attrs, label = head.group(1) or '', head.group(2)
                clean = re.sub(r'<[^>]+>|\{%.*?%\}|\{\{.*?\}\}', '',
                               label).strip()
                if clean in NUMERIC_HEADS and 'data-type' not in attrs:
                    misses.append('%s: «%s»' % (path, clean))
        self.assertEqual(misses, [], 'столбцы без признака: %s' % misses)

    def test_values_carry_the_same_mark_as_the_head(self):
        """Признак стоит и на ячейках: правило адресуется по нему."""
        for path, text in screens():
            if 'admin' in path or 'data-type' not in text:
                continue
            heads = len(re.findall(r'<th[^>]*data-type=', text))
            cells = len(re.findall(r'<td[^>]*data-type=', text))
            if heads:
                self.assertTrue(cells, '%s: заголовки размечены, ячейки нет'
                                % path)


class RuleReachesBothSidesTests(TestCase):
    """6.1 — правило доезжает и до кабинета, и до каталога."""

    def test_rule_lives_in_one_file(self):
        align = read('templates', '_table_align.html')
        self.assertIn('text-align: center', align)
        self.assertIn('tabular-nums', align)
        # В наборе остался только вызов — иначе правил было бы два.
        kit = read('templates', '_kit.html')
        self.assertIn('_table_align.html', kit)
        self.assertNotIn('table th[data-type="num"]', kit)

    def test_catalog_includes_the_rule(self):
        """⚠️ Каталог — экран ученика, набор деталей кабинета он не тянет."""
        base = read('catalog', 'templates', 'catalog', 'base.html')
        self.assertIn('_table_align.html', base)

    def test_date_columns_are_centred_too(self):
        """Дата — столбец нетекстовый; замер показал расхождение до 52 px."""
        align = read('templates', '_table_align.html')
        rule = align[align.index('text-align: center'):]
        head = align[:align.index('text-align: center')]
        self.assertIn('data-type="date"', head + rule[:200])

    def test_text_columns_are_left_alone(self):
        align = read('templates', '_table_align.html')
        self.assertNotIn('data-type="text"', align)

    def test_chip_is_centred_with_its_background(self):
        """Длина слова в чипе не должна сдвигать столбец."""
        align = read('templates', '_table_align.html')
        self.assertIn('.badge', align)
        self.assertIn('inline-flex', align)


class OverviewOrderTests(TestCase):
    """6.2 — список людей выше матрицы."""

    def test_students_block_comes_first(self):
        text = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        students = text.index('{# ── Таблица учеников')
        matrix = text.index('{# ── Тепловая матрица')
        self.assertLess(students, matrix)


class FrozenColumnTests(TestCase):
    """6.3 — первый столбец матрицы закреплён."""

    def test_name_cells_are_marked(self):
        text = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        matrix = text[text.index('{# ── Тепловая матрица'):]
        self.assertIn('class="no-sort matrix-name"', matrix)
        self.assertIn('<td class="matrix-name">', matrix)

    def test_sticky_rules_exist(self):
        style = read('problems', 'templates', 'platform',
                     '_stats_style.html')
        rules = style[style.index('.stats-table td.matrix-name'):]
        rules = rules[:rules.index('}')]
        self.assertIn('position: sticky', rules)
        self.assertIn('left: 0', rules)

    def test_frozen_cell_has_its_own_background(self):
        """⚠️ `position: sticky` не рисует фон — клетки просвечивали бы."""
        style = read('problems', 'templates', 'platform',
                     '_stats_style.html')
        rules = style[style.index('.stats-table td.matrix-name'):]
        rules = rules[:rules.index('}')]
        self.assertIn('background: var(--surface)', rules)
        self.assertIn('box-shadow', rules)


class RenderedTablesTests(TestCase):
    """Правило действительно попадает в разметку страниц."""

    def test_kit_renders_the_alignment_rule(self):
        kit = render_to_string('_kit.html')
        self.assertIn('td[data-type="num"]', kit)

    def test_catalog_base_renders_it_too(self):
        base = render_to_string('catalog/base.html')
        self.assertIn('td[data-type="num"]', base)
