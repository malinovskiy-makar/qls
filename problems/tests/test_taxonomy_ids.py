# -*- coding: utf-8 -*-
"""Идентификаторы тем/тегов для enum схемы (Б4-2, диета префикса, 31.08.2026).

`data/taxonomy.json` не меняется — идентификаторы выводятся из его порядка.
Эти тесты защищают инвариант: уникальность и обратимость преобразования,
без которых модель молча возвращала бы id, который ни на что не разбирается.
"""
from django.test import SimpleTestCase

from problems.enrich import taxonomy


class TaxonomyIdsTests(SimpleTestCase):
    def test_29_уникальных_идентификаторов_тем(self):
        ids = taxonomy.theme_ids()
        self.assertEqual(len(ids), 29)
        self.assertEqual(len(set(ids)), 29)

    def test_344_уникальных_идентификатора_тегов(self):
        ids = taxonomy.tag_ids()
        self.assertEqual(len(ids), 344)
        self.assertEqual(len(set(ids)), 344)

    def test_обратное_преобразование_темы_даёт_исходное_название(self):
        for identifier, name in zip(taxonomy.theme_ids(), taxonomy.theme_names()):
            self.assertEqual(taxonomy.theme_name_from_id(identifier), name)

    def test_обратное_преобразование_тега_даёт_исходное_название(self):
        for identifier, name in zip(taxonomy.tag_ids(), taxonomy.all_tags()):
            self.assertEqual(taxonomy.tag_name_from_id(identifier), name)

    def test_id_тега_это_номер_темы_точка_номер_тега_внутри_темы(self):
        """Формат `<id темы>.<номер тега>` — то, что реально идёт в enum схемы."""
        for theme in taxonomy.themes():
            for index, tag in enumerate(theme['tags'], start=1):
                self.assertEqual(taxonomy.tag_id(tag), '%d.%d' % (theme['id'], index))

    def test_tree_text_подписывает_каждый_тег_его_идентификатором(self):
        text = taxonomy.tree_text()
        for identifier in taxonomy.tag_ids():
            self.assertIn(identifier, text)
