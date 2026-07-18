# -*- coding: utf-8 -*-
"""Тесты разблокировки группы Б (problems.batch2_unblock).

Реальные случаи из ревью — регресс: #49939 (расщепление пункта надвое),
#50130 (в базе не хватает пункта — model длиннее existing), #30402
(статья уже перестроена другим процессом — «оболочка» короче нормы).
"""
from django.test import SimpleTestCase, TestCase

from problems.batch2_unblock import (
    apply_glue, build_apply_pipeline, classify_bad_trim,
    classify_conflict_solution, classify_unknown_label, introduces_pipe_table,
    match_parts_by_content, normalize_quotes, pipeline_changes,
)
from problems.models import ProblemPart
from problems.tests.factories import make_problem


def _rec(cleaned_statement='', cleaned_parts=None, has_solution=False,
        extracted_solution=''):
    return {'data': {
        'cleaned_statement': cleaned_statement,
        'cleaned_parts': cleaned_parts or {},
        'has_solution': has_solution,
        'extracted_solution': extracted_solution,
        'flags': [],
    }}


class MatchPartsByContentTests(SimpleTestCase):
    def test_confident_one_to_one_match(self):
        existing = [(1, 'а', 'Построить КПВ экономики острова.'),
                   (2, 'б', 'Объяснить альтернативные издержки каждого товара.')]
        cleaned = {'а': 'Построить КПВ экономики острова и объяснить форму.',
                  'б': 'Дать объяснение альтернативным издержкам каждого товара.'}
        match = match_parts_by_content(existing, cleaned)
        self.assertEqual(match, {
            1: 'Построить КПВ экономики острова и объяснить форму.',
            2: 'Дать объяснение альтернативным издержкам каждого товара.',
        })

    def test_split_part_is_ambiguous(self):
        # Реальный случай #49939: одна существующая строка склеивает ДВА
        # вопроса («...бензина?\nс) Как изменилась ситуация...»), Sonnet
        # предлагает их как два отдельных пункта — оба лучше всего похожи
        # на ОДИН и тот же существующий пункт → неоднозначность.
        existing = [(1, 'а', 'Первый вопрос про рынок нефти.'),
                   (2, 'Ь', 'Как изменение цены на нефть повлияло на рынок '
                           'бензина?\nс) Как изменилась ситуация на рынках '
                           'автомобилей?'),
                   (3, 'd', 'Третий вопрос про теплоизоляцию.')]
        cleaned = {'б': 'Как изменение цены на нефть повлияло на рынок бензина?',
                  'с': 'Как изменилась ситуация на рынках автомобилей?'}
        self.assertIsNone(match_parts_by_content(existing, cleaned))

    def test_missing_part_in_db_is_ambiguous(self):
        # Реальный случай #50130: модель вернула на один пункт больше, чем
        # есть в базе (пункт был потерян при импорте) — не изобретаем pk.
        existing = [(1, 'а', 'Студент дневного отделения вуза.'),
                   (2, 'Ь', 'Выпускник школы, проваливший экзамены в вуз.'),
                   (3, 'd', 'Девушка, вышедшая замуж и уволившаяся с работы.')]
        cleaned = {'а': 'Студент дневного отделения вуза.',
                  'b': 'Выпускник школы, проваливший экзамены в вуз.',
                  'c': 'Преподаватель экономики в отпуске.',  # нового пункта в базе нет
                  'd': 'Девушка, вышедшая замуж и уволившаяся с работы.'}
        self.assertIsNone(match_parts_by_content(existing, cleaned))

    def test_no_existing_parts_returns_none(self):
        self.assertIsNone(match_parts_by_content([], {'а': 'текст'}))

    def test_low_similarity_returns_none(self):
        existing = [(1, 'а', 'Про эластичность спроса на кофе.')]
        cleaned = {'б': 'Совершенно другой текст про налоги и субсидии на бензин.'}
        self.assertIsNone(match_parts_by_content(existing, cleaned))


class ApplyGlueTests(SimpleTestCase):
    def test_glues_mid_sentence_break(self):
        text = 'Налог на продажи товаров\nявляется регрессивным.'
        self.assertEqual(apply_glue(text),
                         'Налог на продажи товаров является регрессивным.')

    def test_empty_text_untouched(self):
        self.assertEqual(apply_glue(''), '')

    def test_no_newline_untouched(self):
        text = 'Одна строка без переносов.'
        self.assertEqual(apply_glue(text), text)


class ClassifyConflictSolutionTests(TestCase):
    def test_solution_never_touched_stmt_applied(self):
        p = make_problem(statement='Старое грязное\nусловие с решением внутри.',
                         solution='Уже есть решение в базе.')
        rec = _rec(cleaned_statement='Новое чистое условие.',
                  has_solution=True, extracted_solution='Решение из Sonnet.')
        res = classify_conflict_solution(p, rec)
        self.assertTrue(res['apply'])
        self.assertEqual(res['changes']['stmt_raw'], 'Новое чистое условие.')
        self.assertNotIn('solution', res['changes'])
        self.assertEqual(res['extracted_solution'], 'Решение из Sonnet.')

    def test_suspicious_trim_vs_current_goes_to_remainder(self):
        p = make_problem(statement='Очень длинное содержательное условие задачи '
                                   'про рынок труда и минимальную зарплату.',
                         solution='Решение уже есть.')
        rec = _rec(cleaned_statement='Кратко.', has_solution=True,
                  extracted_solution='Решение.')
        res = classify_conflict_solution(p, rec)
        self.assertFalse(res['apply'])
        self.assertIn('stmt_suspicious_trim_vs_current', res['reasons'])
        # решение всё равно попадает в лог — это не запись в базу
        self.assertEqual(res['extracted_solution'], 'Решение.')

    def test_no_net_change_when_only_solution_present(self):
        p = make_problem(statement='Условие уже в порядке.', solution='Есть решение.')
        rec = _rec(cleaned_statement='', has_solution=True,
                  extracted_solution='Извлечённое решение.')
        res = classify_conflict_solution(p, rec)
        self.assertFalse(res['apply'])
        self.assertEqual(res['reasons'], ['no_net_change_besides_solution'])
        self.assertEqual(res['extracted_solution'], 'Извлечённое решение.')

    def test_parts_applied_by_pk_not_label(self):
        p = make_problem(statement='Условие.', solution='Решение есть.')
        ProblemPart.objects.create(problem=p, label='а', order=1,
                                   statement='Найти равновесную цену на рынке товара.',
                                   answer='')
        rec = _rec(cleaned_parts={'а': 'Найти равновесную цену на рынке товара X.'},
                  has_solution=False)
        res = classify_conflict_solution(p, rec)
        self.assertTrue(res['apply'])
        part_pk = p.parts.get().pk
        self.assertEqual(res['changes']['parts_raw'],
                         {part_pk: 'Найти равновесную цену на рынке товара X.'})


class ClassifyUnknownLabelTests(TestCase):
    def test_confident_mapping_applied(self):
        p = make_problem(statement='Условие.')
        ProblemPart.objects.create(problem=p, label='а', order=1,
                                   statement='Построить КПВ острова.', answer='')
        ProblemPart.objects.create(problem=p, label='Ь', order=2,
                                   statement='Объяснить издержки упущенных возможностей.',
                                   answer='')
        pks = list(p.parts.values_list('pk', flat=True))
        rec = _rec(cleaned_parts={
            'а': 'Построить КПВ острова и объяснить форму.',
            'б': 'Дать объяснение издержкам упущенных возможностей.',
        })
        res = classify_unknown_label(p, rec)
        self.assertTrue(res['apply'])
        self.assertEqual(set(res['changes']['parts_raw'].keys()), set(pks))

    def test_unchanged_matched_part_not_written(self):
        # Находка пост-контроля применения (2026-07-19): Sonnet иногда
        # включает в cleaned_parts пункт, текст которого byte-в-byte
        # совпадает с текущим — сопоставление находится, но писать в базу
        # одно и то же поле не нужно (реальный случай #50010, part «Ь»).
        p = make_problem(statement='Условие.')
        ProblemPart.objects.create(problem=p, label='а', order=1,
                                   statement='Первый пункт.', answer='')
        ProblemPart.objects.create(problem=p, label='Ь', order=2,
                                   statement='Второй пункт без изменений.', answer='')
        rec = _rec(cleaned_parts={
            'а': 'Первый пункт переформулирован.',
            'б': 'Второй пункт без изменений.',  # идентично текущему
        })
        res = classify_unknown_label(p, rec)
        self.assertTrue(res['apply'])
        pks = {pp.label: pp.pk for pp in p.parts.all()}
        self.assertEqual(set(res['changes']['parts_raw'].keys()), {pks['а']})

    def test_all_matched_parts_unchanged_goes_to_remainder(self):
        p = make_problem(statement='Условие.')
        ProblemPart.objects.create(problem=p, label='Ь', order=1,
                                   statement='Пункт без изменений.', answer='')
        rec = _rec(cleaned_parts={'б': 'Пункт без изменений.'})
        res = classify_unknown_label(p, rec)
        self.assertFalse(res['apply'])
        self.assertEqual(res['reasons'], ['no_net_change'])

    def test_ambiguous_mapping_to_remainder(self):
        p = make_problem(statement='Условие.')
        ProblemPart.objects.create(problem=p, label='а', order=1,
                                   statement='Первый вопрос.', answer='')
        rec = _rec(cleaned_parts={
            'а': 'Первый вопрос переформулирован.',
            'б': 'Совсем другой вопрос, которого в базе нет вообще.',
        })
        res = classify_unknown_label(p, rec)
        self.assertFalse(res['apply'])
        self.assertIn('parts_ambiguous', res['reasons'])

    def test_solution_written_when_no_conflict(self):
        p = make_problem(statement='Условие.', solution='')
        ProblemPart.objects.create(problem=p, label='Ь', order=1,
                                   statement='Пункт про эластичность спроса.',
                                   answer='')
        rec = _rec(cleaned_parts={'б': 'Пункт про эластичность спроса на бензин.'},
                  has_solution=True, extracted_solution='Новое решение.')
        res = classify_unknown_label(p, rec)
        self.assertTrue(res['apply'])
        self.assertEqual(res['changes']['solution_raw'], 'Новое решение.')

    def test_solution_conflict_logged_not_applied(self):
        p = make_problem(statement='Условие.', solution='Уже есть решение.')
        ProblemPart.objects.create(problem=p, label='Ь', order=1,
                                   statement='Пункт про эластичность спроса.',
                                   answer='')
        rec = _rec(cleaned_parts={'б': 'Пункт про эластичность спроса на бензин.'},
                  has_solution=True, extracted_solution='Конфликтующее решение.')
        res = classify_unknown_label(p, rec)
        self.assertTrue(res['apply'])  # части применяются
        self.assertNotIn('solution_raw', res['changes'])  # решение — нет
        self.assertEqual(res['extracted_solution'], 'Конфликтующее решение.')


class ClassifyBadTrimTests(TestCase):
    def test_always_manual_never_auto_applies(self):
        p = make_problem(statement='Очень длинное содержательное условие задачи '
                                   'на много символов подряд без остановки текста.')
        rec = _rec(cleaned_statement='Коротко.')
        res = classify_bad_trim(p, rec)
        self.assertFalse(res['apply'])
        self.assertEqual(res['reasons'], ['manual_review_required'])
        self.assertGreater(res['shrink_pct'], 80)

    def test_short_current_statement_flagged(self):
        # Реальный случай #30402: текущее условие — короткая «шапка»
        # (реальный контент уже в подпунктах), предложение Sonnet может
        # опираться на устаревшую посылку.
        p = make_problem(statement='ОСНОВА\n\nБЛИЦ')
        rec = _rec(cleaned_statement='БЛИЦ')
        res = classify_bad_trim(p, rec)
        self.assertIn('current_statement_very_short', res['notes'])


class PipelineChangesTests(SimpleTestCase):
    def test_glue_applied_to_statement_and_parts(self):
        changes = {
            'stmt_raw': 'Условие оборвано\nпосреди фразы про экономику.',
            'parts_raw': {5: 'Пункт оборван\nпосреди предложения.'},
            'solution_raw': 'Решение остаётся как есть.',
        }
        out = pipeline_changes(changes)
        self.assertEqual(out['stmt'],
                         'Условие оборвано посреди фразы про экономику.')
        self.assertEqual(out['parts'][5], 'Пункт оборван посреди предложения.')
        self.assertEqual(out['solution'], 'Решение остаётся как есть.')


class NormalizeQuotesTests(SimpleTestCase):
    def test_paired_angle_quotes_replaced(self):
        self.assertEqual(normalize_quotes('Он сказал <<привет>> и ушёл.'),
                         'Он сказал «привет» и ушёл.')

    def test_multiple_pairs_on_one_line(self):
        self.assertEqual(normalize_quotes('Смесь: <<А>> и <<Б>>.'),
                         'Смесь: «А» и «Б».')

    def test_single_angle_inequality_untouched(self):
        text = 'x < 5 и y > 10, это неравенства.'
        self.assertEqual(normalize_quotes(text), text)

    def test_mixed_quotes_and_inequality_untouched_and_replaced(self):
        self.assertEqual(normalize_quotes('Смесь: <<А>> и x < 5 и <<Б>>.'),
                         'Смесь: «А» и x < 5 и «Б».')

    def test_unclosed_angle_left_untouched(self):
        text = 'Незакрытый <<пример без конца.'
        self.assertEqual(normalize_quotes(text), text)

    def test_empty_text(self):
        self.assertEqual(normalize_quotes(''), '')


class IntroducesPipeTableTests(SimpleTestCase):
    def test_new_pipe_table_detected(self):
        old = 'Обычный текст без таблиц.'
        new = '| a | b |\n|---|---|\n| 1 | 2 |'
        self.assertTrue(introduces_pipe_table(old, new))

    def test_pipe_inside_formula_not_flagged(self):
        # |x| — модуль внутри $...$, не разделитель таблицы
        old = r'Модуль $|x|$ равен 5.'
        new = r'Модуль $|x|$ равен пяти.'
        self.assertFalse(introduces_pipe_table(old, new))

    def test_pipe_already_present_in_old_not_flagged(self):
        # правка не ВНОСИТ '|' — он уже был вне формулы
        old = 'Столбец A | Столбец B, как есть.'
        new = 'Столбец A | Столбец B, почищено.'
        self.assertFalse(introduces_pipe_table(old, new))

    def test_new_formula_pipe_not_flagged(self):
        # новый '|' появился, но ВНУТРИ формулы — не разделитель
        old = 'Текст без формул вообще.'
        new = r'Модуль $|x|$ равен 5.'
        self.assertFalse(introduces_pipe_table(old, new))


class BuildApplyPipelineTests(TestCase):
    def test_conflict_solution_applies_stmt_never_solution(self):
        p = make_problem(statement='Старое условие с <<утёкшим>> решением.',
                         solution='Уже есть решение в базе.')
        rec = _rec(cleaned_statement='Новое чистое условие.',
                  has_solution=True, extracted_solution='Решение Sonnet.')
        final, exclude_reason, extracted = build_apply_pipeline(
            p, rec, 'conflict_solution')
        self.assertIsNone(exclude_reason)
        self.assertEqual(final['stmt'], 'Новое чистое условие.')
        self.assertNotIn('solution', final)
        self.assertEqual(extracted, 'Решение Sonnet.')

    def test_unknown_label_never_writes_solution_this_session(self):
        # даже когда классификатор готов был бы записать решение (не
        # конфликтует) — сессия применения его сознательно не пишет
        p = make_problem(statement='Условие.', solution='')
        ProblemPart.objects.create(problem=p, label='Ь', order=1,
                                   statement='Пункт про эластичность спроса.',
                                   answer='')
        rec = _rec(cleaned_parts={'б': 'Пункт про эластичность спроса на бензин.'},
                  has_solution=True, extracted_solution='Новое решение.')
        final, exclude_reason, extracted = build_apply_pipeline(
            p, rec, 'unknown_label')
        self.assertIsNone(exclude_reason)
        self.assertNotIn('solution', final)
        self.assertIn('parts', final)

    def test_pipe_table_excludes_whole_record(self):
        p = make_problem(statement='Обычное условие без таблиц.')
        rec = _rec(cleaned_statement='| a | b |\n|---|---|\n| 1 | 2 |')
        final, exclude_reason, extracted = build_apply_pipeline(
            p, rec, 'conflict_solution')
        self.assertIsNone(final)
        self.assertEqual(exclude_reason, 'introduces_pipe_table:statement')

    def test_quotes_normalized_before_glue(self):
        p = make_problem(statement='Условие.')
        rec = _rec(cleaned_statement='Он сказал <<привет,\nдруг>> и ушёл.')
        final, exclude_reason, extracted = build_apply_pipeline(
            p, rec, 'conflict_solution')
        self.assertIsNone(exclude_reason)
        self.assertEqual(final['stmt'], 'Он сказал «привет, друг» и ушёл.')

    def test_no_apply_returns_none_without_exclude_reason(self):
        p = make_problem(statement='Условие уже в порядке.')
        rec = _rec(cleaned_statement='')  # нечего применять
        final, exclude_reason, extracted = build_apply_pipeline(
            p, rec, 'conflict_solution')
        self.assertIsNone(final)
        self.assertIsNone(exclude_reason)
