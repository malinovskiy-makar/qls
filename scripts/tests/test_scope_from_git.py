# -*- coding: utf-8 -*-
"""Тесты сопоставления путь -> тестовый лейбл (scripts/scope_from_git.py).

Запуск:
    venv313/Scripts/python.exe -m unittest discover -s scripts/tests -t .
"""
import unittest

from scripts.scope_from_git import (
    resolve_labels, _dotted_module, build_reverse_import_index, _parse_status_porcelain,
    changed_files,
)


class DottedModuleTests(unittest.TestCase):

    def test_plain_module(self):
        self.assertEqual(_dotted_module('teacher/access.py'), 'teacher.access')

    def test_nested_module(self):
        self.assertEqual(
            _dotted_module('problems/management/commands/apply_topic_mapping.py'),
            'problems.management.commands.apply_topic_mapping')

    def test_init_module_drops_filename(self):
        self.assertEqual(_dotted_module('game/generators/__init__.py'), 'game.generators')

    def test_non_python_file_has_no_module(self):
        self.assertIsNone(_dotted_module('catalog/templates/catalog/problem_detail.html'))


class ResolveLabelsTests(unittest.TestCase):

    def test_empty_input_runs_nothing(self):
        result = resolve_labels([])
        self.assertEqual(result.labels, frozenset())
        self.assertFalse(result.full_run)

    def test_unmapped_path_contributes_nothing(self):
        result = resolve_labels(['materials/branch_comparison_20260820/notes.txt'])
        self.assertEqual(result.labels, frozenset())
        self.assertFalse(result.full_run)

    def test_calc2_is_fully_isolated_leaf(self):
        result = resolve_labels(['calc2/views.py'])
        self.assertEqual(result.labels, frozenset({'calc2'}))
        self.assertFalse(result.full_run)

    def test_leaf_app_without_dependents(self):
        result = resolve_labels(['catalog/views.py'])
        self.assertEqual(result.labels, frozenset({'catalog'}))

    def test_leaf_app_with_reverse_dependent(self):
        index = {'teacher.access': frozenset({'calendar_stub'})}
        result = resolve_labels(['teacher/access.py'], reverse_index=index)
        self.assertEqual(result.labels, frozenset({'teacher', 'calendar_stub'}))

    def test_leaf_app_reverse_dependent_excludes_self(self):
        # свой же лейбл в индексе не должен давать дублирования/сюрпризов
        index = {'game.views': frozenset({'game', 'problems'})}
        result = resolve_labels(['game/views.py'], reverse_index=index)
        self.assertEqual(result.labels, frozenset({'game', 'problems'}))

    def test_problems_core_file_is_blanket(self):
        result = resolve_labels(['problems/models.py'])
        self.assertEqual(
            result.labels,
            frozenset({'problems', 'catalog', 'student', 'teacher', 'game', 'calendar_stub'}))
        self.assertNotIn('calc2', result.labels)

    def test_problems_management_command_isolated_by_default(self):
        result = resolve_labels(
            ['problems/management/commands/import_matek.py'], reverse_index={})
        self.assertEqual(result.labels, frozenset({'problems'}))

    def test_problems_management_command_with_known_dependent(self):
        index = {
            'problems.management.commands.apply_topic_mapping':
                frozenset({'catalog', 'teacher', 'game'}),
        }
        result = resolve_labels(
            ['problems/management/commands/apply_topic_mapping.py'], reverse_index=index)
        self.assertEqual(result.labels, frozenset({'problems', 'catalog', 'teacher', 'game'}))

    def test_problems_tests_isolated_by_default(self):
        result = resolve_labels(['problems/tests/test_hw_generator.py'], reverse_index={})
        self.assertEqual(result.labels, frozenset({'problems'}))

    def test_problems_tests_factories_has_known_dependent(self):
        index = {'problems.tests.factories': frozenset({'catalog'})}
        result = resolve_labels(['problems/tests/factories.py'], reverse_index=index)
        self.assertEqual(result.labels, frozenset({'problems', 'catalog'}))

    def test_search_service_maps_to_catalog(self):
        result = resolve_labels(['search_service/app.py'])
        self.assertEqual(result.labels, frozenset({'catalog'}))

    def test_union_across_multiple_changed_files(self):
        index = {'game.views': frozenset({'problems'})}
        result = resolve_labels(['catalog/views.py', 'game/views.py'], reverse_index=index)
        self.assertEqual(result.labels, frozenset({'catalog', 'game', 'problems'}))

    def test_windows_backslashes_are_normalized(self):
        result = resolve_labels(['calc2\\views.py'])
        self.assertEqual(result.labels, frozenset({'calc2'}))

    def test_config_change_triggers_full_run(self):
        result = resolve_labels(['config/settings.py'])
        self.assertTrue(result.full_run)

    def test_manage_py_triggers_full_run(self):
        result = resolve_labels(['manage.py'])
        self.assertTrue(result.full_run)

    def test_requirements_change_triggers_full_run(self):
        result = resolve_labels(['requirements/base.in'])
        self.assertTrue(result.full_run)

    def test_docker_compose_change_triggers_full_run(self):
        result = resolve_labels(['docker-compose.dev.yml'])
        self.assertTrue(result.full_run)

    def test_claude_md_change_triggers_full_run(self):
        result = resolve_labels(['CLAUDE.md'])
        self.assertTrue(result.full_run)

    def test_docs_change_triggers_full_run(self):
        result = resolve_labels(['docs/TESTING.md'])
        self.assertTrue(result.full_run)

    def test_root_template_change_triggers_full_run(self):
        result = resolve_labels(['templates/_nav.html'])
        self.assertTrue(result.full_run)

    def test_app_owned_template_does_not_trigger_full_run(self):
        # catalog/templates/catalog/... лежит ПОД catalog/, это не общий templates/
        result = resolve_labels(['catalog/templates/catalog/problem_detail.html'])
        self.assertFalse(result.full_run)
        self.assertEqual(result.labels, frozenset({'catalog'}))

    def test_full_run_trigger_short_circuits_scoping(self):
        result = resolve_labels(['config/settings.py', 'calc2/views.py'])
        self.assertTrue(result.full_run)


class ReverseImportIndexOnRealRepoTests(unittest.TestCase):
    """Живая документация: конкретные межпакетные связи, найденные код-чеком
    2026-08-25. Если тест покраснеет — связь пропала (или переехала), и
    NARROW_PROBLEMS_PREFIXES/BLANKET_PROBLEMS_DEPENDENTS в scope_from_git.py
    стоит перечитать заново, а не просто ослабить проверку."""

    @classmethod
    def setUpClass(cls):
        cls.index = build_reverse_import_index()

    def test_calendar_stub_depends_on_teacher_access(self):
        self.assertIn('calendar_stub', self.index.get('teacher.access', frozenset()))

    def test_apply_topic_mapping_has_three_known_dependents(self):
        dependents = self.index.get('problems.management.commands.apply_topic_mapping', frozenset())
        self.assertTrue({'catalog', 'teacher', 'game'} <= dependents)

    def test_factories_depends_on_by_catalog(self):
        self.assertIn('catalog', self.index.get('problems.tests.factories', frozenset()))

    def test_problems_depends_on_game_views(self):
        self.assertIn('problems', self.index.get('game.views', frozenset()))

    def test_calc2_never_appears_as_a_dependent_of_anything(self):
        for module, dependents in self.index.items():
            if not module.startswith('calc2.'):
                self.assertNotIn(
                    'calc2', dependents,
                    'calc2 задокументирован как полностью изолированный, '
                    'а %r импортируется из calc2' % module)


class ParseStatusPorcelainTests(unittest.TestCase):

    def test_modified_tracked_file(self):
        self.assertEqual(_parse_status_porcelain(' M catalog/views.py'), ['catalog/views.py'])

    def test_untracked_file(self):
        self.assertEqual(_parse_status_porcelain('?? scripts/scope_from_git.py'),
                          ['scripts/scope_from_git.py'])

    def test_staged_and_modified_combo(self):
        self.assertEqual(_parse_status_porcelain('MM problems/models.py'), ['problems/models.py'])

    def test_renamed_file_keeps_new_path_only(self):
        self.assertEqual(
            _parse_status_porcelain('R  old_name.py -> new_name.py'), ['new_name.py'])

    def test_multiple_lines(self):
        output = ' M catalog/views.py\n?? teacher/access.py\n'
        self.assertEqual(
            sorted(_parse_status_porcelain(output)),
            ['catalog/views.py', 'teacher/access.py'])

    def test_blank_lines_are_skipped(self):
        self.assertEqual(_parse_status_porcelain(' M a.py\n\n'), ['a.py'])

    def test_quoted_path_with_spaces(self):
        self.assertEqual(
            _parse_status_porcelain('?? "path with spaces.py"'), ['path with spaces.py'])


class ChangedFilesIntegrationTests(unittest.TestCase):
    """Лёгкий интеграционный тест на реальном репозитории — без mock'а git."""

    def test_returns_a_sorted_list_without_error(self):
        result = changed_files()
        self.assertIsInstance(result, list)
        self.assertEqual(result, sorted(result))

    def test_accepts_explicit_base_ref(self):
        result = changed_files(base_ref='HEAD')
        self.assertIsInstance(result, list)


if __name__ == '__main__':
    unittest.main()
