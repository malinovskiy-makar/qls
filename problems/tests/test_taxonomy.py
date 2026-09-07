# -*- coding: utf-8 -*-
"""Таксономия v1.1 — классификация легаси-тегов и канон из файла.

Стандарт (29 тем, 344 тега) лежит в data/taxonomy.json и правится только
владельцем. Здесь проверяется код, который на этот файл опирается:
classify_legacy_tag() из команды load_taxonomy.

⚠️ Почему у классификатора есть именованный словарь исключений. Правило
«2-3 слова с заглавных букв — имя составителя» верное, но «Open Question»
и «David Luenberger» формально неотличимы. Чинить это правилом — значит
сочинять признак, которого в строке нет; вместо этого короткий список,
который читается глазами. Тесты стерегут ОБА механизма: и правило, и то,
что список перекрывает правило, а не наоборот.
"""
from django.test import TestCase

from problems.management.commands.load_taxonomy import (
    MANUAL_KIND_OVERRIDES,
    classify_legacy_tag,
)


class ClassifyLegacyTagTests(TestCase):
    """Правила разметки тегов, не вошедших в 344 канонических."""

    def test_ссылка_это_мусор(self):
        # Половина мусорных тегов в базе — ссылки на iloveeconomics,
        # утёкшие в поле при импорте комментариев.
        self.assertEqual(
            classify_legacy_tag('http://iloveeconomics.ru/zadachi/z6'), 'junk')
        self.assertEqual(
            classify_legacy_tag('http://www.iloveeconomics.ru/zadachi/z1722'),
            'junk')
        self.assertEqual(classify_legacy_tag('www.example.com'), 'junk')

    def test_имя_файла_это_мусор(self):
        # reshenie_zadachi_ekonomika_i_shahmaty.pdf — реальный тег из базы.
        # Под правило «ссылка» он не подходит, под «длиннее 60» тоже.
        self.assertEqual(
            classify_legacy_tag('reshenie_zadachi_ekonomika_i_shahmaty.pdf'),
            'junk')
        for name in ('konspekt.docx', 'listok.DOC', 'zadanie.TeX', 'notes.txt'):
            self.assertEqual(classify_legacy_tag(name), 'junk', name)

    def test_слишком_длинная_строка_это_мусор(self):
        self.assertEqual(classify_legacy_tag('я' * 61), 'junk')

    def test_только_цифры_и_знаки_это_мусор(self):
        self.assertEqual(classify_legacy_tag('2010 — 2011'), 'junk')

    def test_имя_составителя_это_author(self):
        # Имена составителей — ценные данные о происхождении задачи,
        # они просто лежат не в том поле. Удалять их нельзя.
        for name in ('Данил Фёдоровых', 'Алексей Суздальцев',
                     'Павел Кривенко', 'Иван Лазарев', 'Дмитрий Сорокин',
                     'А.А. Мицкевич', 'Попов Александр Михайлович'):
            self.assertEqual(classify_legacy_tag(name), 'author', name)

    def test_экономический_термин_это_legacy(self):
        # Старые теги-термины лежат в нижнем регистре — под правило
        # «слова с заглавных букв» не попадают.
        for name in ('эффект дохода', 'предельные издержки', 'монополия'):
            self.assertEqual(classify_legacy_tag(name), 'legacy', name)

    def test_словарь_исключений_перекрывает_правило(self):
        # «Open Question» правило считает именем (два слова с заглавных
        # латиницей) — словарь обязан это перебить. Если словарь применить
        # ДО правила, значение вернётся к 'author'.
        self.assertEqual(classify_legacy_tag('Open Question'), 'legacy')
        long_stub = ('Задача Для Подготовки к многопрофильной олимпиаде '
                     'ГУ-ВШЭ 10 класс')
        self.assertEqual(classify_legacy_tag(long_stub), 'legacy')
        self.assertIn('Open Question', MANUAL_KIND_OVERRIDES)

    def test_сборник_харива_остаётся_author(self):
        # Не ФИО, но происхождение задачи — владелец решил оставить.
        self.assertEqual(classify_legacy_tag('Сборник Харива'), 'author')

    def test_пустая_строка_не_роняет(self):
        self.assertEqual(classify_legacy_tag(''), 'legacy')
        self.assertEqual(classify_legacy_tag(None), 'legacy')
