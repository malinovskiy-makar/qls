# -*- coding: utf-8 -*-
"""Разбор XML из .docx не раскрывает сущности.

Находка bandit B314 в `parse_vsosh_municip` — разбор `word/document.xml` и
`word/numbering.xml` стандартным `xml.etree.ElementTree`. Разобрана в сессии
3Б; выводы такие.

**Внешние сущности не раскрываются.** Это проверяется здесь напрямую: XXE с
`file:///` падает с «undefined entity». Чтения чужих файлов и обращений в
сеть через подсунутый .docx не бывает — ни до правки, ни после.

**Внутренние — раскрывались, и это настоящая дыра.** Девять вложенных
объявлений сущностей («бомба») раздуваются без ограничений и съедают память
машины: отказ в обслуживании при разборе одного файла.

Лечение — `_xml_from_docx`: в OOXML объявлений DTD не бывает (Word их не
пишет), поэтому файл с `<!DOCTYPE` не разбирается вовсе. Новая зависимость
(`defusedxml`) для этого не нужна — её нет в боевом локе, и тянуть её на
сервер ради разовой команды импорта не за что.
"""

import ast
import xml.etree.ElementTree as ET
from pathlib import Path

from django.test import SimpleTestCase

from problems.management.commands.parse_vsosh_municip import _xml_from_docx


def _bomb(depth: int = 9) -> bytes:
    """«Билльон смешков»: каждая сущность удваивает предыдущую."""
    decls = ''.join(
        '<!ENTITY e{i} "{body}">'.format(
            i=i,
            body=('X' * 64) if i == 0 else '&e{p};&e{p};'.format(p=i - 1),
        )
        for i in range(depth)
    )
    return (
        '<?xml version="1.0"?><!DOCTYPE r [' + decls + ']>'
        '<r>&e{last};</r>'.format(last=depth - 1)
    ).encode('utf-8')


XXE = (
    '<?xml version="1.0"?>\n'
    '<!DOCTYPE r [ <!ENTITY x SYSTEM "file:///etc/passwd"> ]>\n'
    '<r>&x;</r>'
).encode('utf-8')

# Как выглядит настоящий кусок word/document.xml — без DTD и без сущностей.
GOOD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
    'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Задача 1</w:t>'
    '</w:r></w:p></w:body></w:document>'
).encode('utf-8')


class DocxXmlEntitiesTests(SimpleTestCase):
    """Что именно делает `_xml_from_docx` с подсунутым файлом."""

    def test_bomb_is_refused(self):
        """Раздувание сущностей не доходит до разбора."""
        with self.assertRaises(ValueError) as ctx:
            _xml_from_docx(_bomb())
        self.assertIn('DOCTYPE', str(ctx.exception))

    def test_external_entity_is_refused(self):
        """XXE тоже не доходит до разбора — отказ раньше, по DOCTYPE."""
        with self.assertRaises(ValueError):
            _xml_from_docx(XXE)

    def test_normal_docx_xml_still_parses(self):
        """Контроль: обычный .docx обязан разбираться как прежде.

        Без этой проверки «починку» можно было бы сделать запретом всего:
        тесты зелёные, импорт мёртв.
        """
        root = _xml_from_docx(GOOD)
        texts = [el.text for el in root.iter() if el.text and el.text.strip()]
        self.assertIn('Задача 1', texts)


class StdlibEntityBehaviourTests(SimpleTestCase):
    """Чем оправдана правка: что стандартный разбор делает на самом деле.

    Эти два теста ничего не защищают — они фиксируют поведение Python, на
    котором построено решение. Если новая версия Python начнёт вести себя
    иначе, они покраснеют, и обоснование в `_xml_from_docx` придётся
    перечитать заново.
    """

    def test_stdlib_does_not_resolve_external_entities(self):
        """Внешние сущности стандартный ElementTree не тянет — XXE не бывает."""
        with self.assertRaises(ET.ParseError):
            ET.fromstring(XXE)

    def test_stdlib_does_expand_internal_entities(self):
        """А внутренние раскрывает — вот почему одного стандарта мало."""
        grown = ET.fromstring(_bomb())
        self.assertGreater(len(grown.text or ''), 10_000)


class NoBareParseLeftTests(SimpleTestCase):
    """`ET.fromstring` в модуле разрешён ровно в одном месте.

    Тест ловит не сегодняшнюю дыру, а завтрашнюю: третий разбор XML,
    добавленный мимо `_xml_from_docx`, вернёт её молча.
    """

    def test_fromstring_is_called_only_inside_the_guard(self):
        path = (Path(__file__).resolve().parent.parent
                / 'management' / 'commands' / 'parse_vsosh_municip.py')
        tree = ast.parse(path.read_text(encoding='utf-8'))

        # Где объявлен защищённый разбор — чтобы исключить его собственный вызов.
        guard = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == '_xml_from_docx'
        )
        allowed = {
            id(node) for node in ast.walk(guard)
        }

        outside = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == 'fromstring'
                    and id(node) not in allowed):
                outside.append(node.lineno)

        self.assertEqual(
            outside, [],
            'ET.fromstring вызывается мимо _xml_from_docx в строках '
            f'{outside} — сущности там не отсечены.',
        )
