"""Пересобирает `catalog/data/topic_map.json` из дерева тем и тегов.

Запускать после правки `catalog/data/taxonomy_tree.md` или списка связей
в `catalog/taxonomy_map.py`. Базу данных НЕ трогает — читает файл, пишет файл.

    manage.py build_topic_map           # пересобрать и записать
    manage.py build_topic_map --check   # только проверить, ничего не писать
"""
from django.core.management.base import BaseCommand, CommandError

from catalog.taxonomy_map import (JSON_PATH, TREE_PATH, build_map, load_tree,
                                  read_map, write_map)


class Command(BaseCommand):
    help = 'Собирает справочник тем и тегов в catalog/data/topic_map.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check', action='store_true',
            help='только проверить, что записанный JSON совпадает со сборкой',
        )

    def handle(self, *args, **options):
        if not TREE_PATH.exists():
            raise CommandError('нет файла дерева: %s' % TREE_PATH)

        tree = load_tree()
        data = build_map(tree)

        themes = [n for n in data['nodes'] if n['k'] == 'theme']
        tags = [n for n in data['nodes'] if n['k'] == 'tag']
        tree_links = [ln for ln in data['links'] if ln['k'] == 'tree']
        cross_links = [ln for ln in data['links'] if ln['k'] == 'cross']
        counted = [t for t in tags if t['c'] is not None]
        sizes = sorted(len(th['tags']) for th in tree)

        if options['check']:
            try:
                on_disk = read_map()
            except FileNotFoundError:
                raise CommandError('нет файла %s — соберите без --check' % JSON_PATH)
            if on_disk != data:
                raise CommandError(
                    'topic_map.json разошёлся с деревом — пересоберите '
                    'командой manage.py build_topic_map')
            self.stdout.write(self.style.SUCCESS('topic_map.json совпадает с деревом'))
            return

        size = write_map(data)

        self.stdout.write('Тем:            %d' % len(themes))
        self.stdout.write('Тегов:          %d  (разброс %d..%d, медиана %d)' % (
            len(tags), sizes[0], sizes[-1], sizes[len(sizes) // 2]))
        self.stdout.write('Со счётчиком:   %d, сумма задач %d' % (
            len(counted), sum(t['c'] for t in counted)))
        self.stdout.write('Узлов:          %d' % len(data['nodes']))
        self.stdout.write('Рёбер:          %d  (дерево %d + перекрёстных %d)' % (
            len(data['links']), len(tree_links), len(cross_links)))
        self.stdout.write(self.style.SUCCESS(
            'Записано: %s (%.1f КБ)' % (JSON_PATH, size / 1024)))
