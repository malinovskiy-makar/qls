"""Финграмотность и основы бизнеса, сессия 2 (13.10.2026).

МОШ «по основам предпринимательства и финансовой грамотности» в реестре;
разбор `event_id` с дефисом в префиксе через реестр (`event_for`); разбор
очереди «на глаза» с заплатками `pages_v2` и сборкой v2 поверх v1; флаг
`auto_publish_ok`. Данные выдуманные; база не нужна.
"""
from django.test import SimpleTestCase

from problems.olympiad_audit import registry
from problems.olympiad_official import Reference


def _row(event_id, number=1):
    return {'event_id': event_id, 'number': number, 'norm_text': 'x'}


class RegistryEntrepreneurshipTests(SimpleTestCase):
    def test_1_new_slug_own_dir_prefix_and_predecessor_note(self):
        entry = registry.get('mosh-entrepreneurship')
        self.assertEqual(entry.audit_dir, 'audit_finbiz_20261013/mosh_entrepreneurship')
        self.assertEqual(entry.event_prefix, 'mosh-entrepreneurship-')
        self.assertEqual(entry.stages, ('qualifying', 'final'))
        self.assertEqual(entry.olympiad_name, 'Московская олимпиада школьников по основам '
                                              'предпринимательства и финансовой грамотности')
        self.assertEqual(entry.compare, 'markup_free')
        self.assertEqual(entry.family, ('mosh-entrepreneurship',))
        note = entry.official_source_defaults['note']
        self.assertIn('mos.olimpiada.ru/tasks/entr', note)
        self.assertIn('предшественник', note)
        names = registry.official_source_names()
        self.assertIn(entry.official_source_name, names)
        self.assertEqual(len(names), len(set(names)))
        # Старые записи не тронуты.
        self.assertEqual(registry.get('mosh-fingram').event_prefix, 'mosh-fingram-')
        self.assertEqual(registry.get('mosh').audit_dir, 'audit_mosh_20261009')


class ParseEventIdTests(SimpleTestCase):
    def test_2_hyphenated_prefixes_by_registry(self):
        cases = {
            'vp-fingram-2019-final-9-10-v1': ('vp-fingram', '2019', 'final', '9-10', 'v1'),
            'vp-ob-2024-final-11-v1': ('vp-ob', '2024', 'final', '11', 'v1'),
            'mosh-fingram-2017-qualifying-5-11-tour2':
                ('mosh-fingram', '2017', 'qualifying', '5-11', 'tour2'),
            'mosh-entrepreneurship-2012-final-8-11-v1':
                ('mosh-entrepreneurship', '2012', 'final', '8-11', 'v1'),
        }
        for event_id, expected in cases.items():
            self.assertEqual(registry.parse_event_id(event_id), expected, event_id)

    def test_3_old_event_ids_as_before(self):
        self.assertEqual(registry.parse_event_id('vp-2020-final-10-v1'),
                         ('vp', '2020', 'final', '10', 'v1'))
        self.assertEqual(registry.parse_event_id('vp-2021-final-10-reserve'),
                         ('vp', '2021', 'final', '10', 'reserve'))
        self.assertEqual(registry.parse_event_id('mosh-2015-final-8-9-day2'),
                         ('mosh', '2015', 'final', '8-9', 'day2'))
        self.assertIsNone(registry.parse_event_id('нечто'))

    def test_4_event_for_hyphenated_and_old(self):
        ref = Reference([_row('vp-fingram-2019-final-9-10-v1'),
                         _row('vp-fingram-2019-final-11-v1'),
                         _row('mosh-fingram-2018-final-10-11-v1'),
                         _row('mosh-fingram-2018-final-10-11-v2')])
        self.assertEqual(ref.event_for(2019, '9-10'), 'vp-fingram-2019-final-9-10-v1')
        self.assertEqual(ref.event_for(2019, 11), 'vp-fingram-2019-final-11-v1')
        self.assertEqual(ref.event_for(2018, '10-11'), 'mosh-fingram-2018-final-10-11-v1')
        self.assertIsNone(ref.event_for(2020, 11))
        old = Reference([_row('vp-2021-final-10-reserve'), _row('vp-2021-final-10-v1'),
                         _row('mosh-2015-final-8-9-day2')])
        self.assertEqual(old.event_for(2021, 10), 'vp-2021-final-10-v1')
        self.assertEqual(old.event_for(2015, '8-9'), 'mosh-2015-final-8-9-day2')


class LayerMetricRepeatedLinesTests(SimpleTestCase):
    """Мерило слоя: строки, повторённые на половине страниц файла (формулировки
    теста, одиночные «1», «2», «3» вариантов), срезаются из слоя как колонтитулы.
    Дословная расшифровка не должна получать за них «лишний текст»."""

    QUESTION = 'Является ли он потребителем по Закону РФ «О защите прав потребителей»?'

    STORIES = ['Авиапассажир смотрит телепрограмму в зале ожидания аэропорта.',
               'Дарья Павловна оставила ребенка в бесплатном детском центре супермаркета.',
               'Геннадий Гаврилович берет в метро бесплатную информационную газету.',
               'Татьяна Андреевна получает молоко на молочной кухне бесплатно.']

    def _layer(self, extra='', story=0):
        return (f'9. Задача 9\n{self.STORIES[story]}\n'
                f'{self.QUESTION}\n1\nНет. Он не является потребителем.\n2\n'
                f'Да. Он является потребителем по определению.\n{extra}')

    def _blocks(self, text_tail=''):
        return [{'type': 'solution', 'number': '9',
                 'text': ('Авиапассажир смотрит телепрограмму в зале ожидания аэропорта.\n\n'
                          f'{self.QUESTION}\n\n1. Нет. Он не является потребителем.\n'
                          '2. Да. Он является потребителем по определению.' + text_tail)}]

    def test_5_repeated_lines_not_extra(self):
        from problems.olympiad_audit import transcribe
        layers = [self._layer(story=i) for i in range(4)]
        footers = transcribe.repeated_lines(layers)
        ratio, numbers_ok, missing, extra, _f = transcribe.layer_metrics(
            self._blocks(), layers[0], footers, page=1)
        self.assertGreaterEqual(ratio, 0.95)
        self.assertEqual(extra, [])
        self.assertTrue(numbers_ok)

    def test_6_real_loss_still_caught(self):
        from problems.olympiad_audit import transcribe
        layers = [self._layer(story=i) for i in range(4)]
        layers[0] = self._layer('Дополнительный абзац о правах пассажира в аэропорту и '
                                'компенсации за задержку рейса составляет 500 рублей.')
        footers = transcribe.repeated_lines(layers)
        ratio, numbers_ok, missing, extra, _f = transcribe.layer_metrics(
            self._blocks(), layers[0], footers, page=1)
        self.assertLess(ratio, 0.90)
        self.assertEqual(missing, ['500'])
        # Выдуманное число, которого нет на странице, — по-прежнему лишнее.
        ratio, numbers_ok, missing, extra, _f = transcribe.layer_metrics(
            self._blocks(' Штраф 7777 рублей.'), self._layer(), footers, page=1)
        self.assertEqual(extra, ['7777'])


class AssembleIntroRepeatTests(SimpleTestCase):
    """МОШ-предпринимательство 2012/13, финал 8-9: вступление второй части
    («Общее время… Максимальное количество баллов…») стоит на КАЖДОЙ странице
    «Ситуаций», а пустая страница теста несёт только «Комплект заданий № 1».
    Такие безномерные блоки — вступление (один раз) или служебная строка, не
    кусок предыдущего задания."""

    INTRO = ('Общее время на выполнение заданий – 60 минут.\nМаксимальное количество '
             'баллов – 19\nДайте правильный и наиболее полный ответ.')

    def test_7_repeated_intro_and_service_line_not_glued(self):
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_asm_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        def page(n, blocks):
            transcribe.Transcriber._write(str(root / 'pages/t' / f'p{n}.json'),
                                          {'status': 'ok', 'blocks': blocks})
        page(1, [{'type': 'task', 'number': '1', 'text': 'Вопрос теста 1.'},
                 {'type': 'task', 'number': '2', 'text': 'Вопрос теста 2.'}])
        page(2, [{'type': 'task', 'number': '', 'text': '**Комплект заданий № 1**'}])
        page(3, [{'type': 'task', 'number': '', 'text': self.INTRO},
                 {'type': 'task', 'number': '3', 'text': 'Ситуация: шуба.'}])
        page(4, [{'type': 'task', 'number': '', 'text': self.INTRO},
                 {'type': 'task', 'number': '4', 'text': 'Ситуация: телефон.'},
                 {'type': 'task', 'number': '', 'text': '(б) кусок условия задания 4'}])
        event = {'event_id': 'mosh-entrepreneurship-2013-final-8-9-v1', 'grade': '8-9',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 4}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['2'].statement, ['Вопрос теста 2.'])
        self.assertEqual(by['3'].statement, ['Ситуация: шуба.'])
        # Настоящий безномерной кусок по-прежнему приклеивается.
        self.assertEqual(by['4'].statement, ['Ситуация: телефон.', '(б) кусок условия задания 4'])
        self.assertEqual(event['preamble'], [self.INTRO])
        self.assertEqual(report['служебная строка — мимо'], 1)
        self.assertEqual(report['повтор вступления — мимо'], 1)

    def test_8_statement_repeated_in_solution_file_not_in_solution(self):
        """Файл ответов МОШ повторяет условие: хвост условия на новой странице
        (`task_continuation` с номером) не становится началом решения, а
        абзацы-повтор условия в начале блока решения срезаются (v1 МОШ-финграм:
        364 из 1 307 решений начинались с текста условия)."""
        import shutil
        import tempfile
        from pathlib import Path

        from problems.olympiad_audit import assemble, transcribe
        root = Path(tempfile.mkdtemp(prefix='finbiz2_sol_'))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        statement = ('Лена получает 50 тыс. рублей в месяц, а тратит 45 тыс. рублей. У Лены есть '
                     'кредитная карта с беспроцентным периодом до погашения долга 7 числа '
                     'каждого месяца и лимитом 100 тыс. рублей.\n\nОпишите оптимальную стратегию Лены.')

        def page(page_dir, n, blocks):
            transcribe.Transcriber._write(str(root / page_dir / f'p{n}.json'),
                                          {'status': 'ok', 'blocks': blocks})
        page('pages/t', 1, [{'type': 'task', 'number': '4', 'text': statement},
                            {'type': 'task', 'number': '5', 'text': 'Как применить поговорку?'}])
        page('pages/s', 1, [{'type': 'task', 'number': '4', 'text': statement[:60]}])
        page('pages/s', 2, [
            {'type': 'task_continuation', 'number': '4',
             'text': 'долга 7 числа каждого месяца и лимитом 100 тыс. рублей.\n\n'
                     'Опишите оптимальную стратегию Лены.'},
            {'type': 'solution', 'number': '4', 'text': '1) Самый высокий доход приносит вклад.'},
            {'type': 'solution', 'number': '5',
             'text': '**Задача 5**\n\nКак применить поговорку?\n\nПокупать одежду в конце сезона.'}])
        event = {'event_id': 'mosh-fingram-2017-final-10-11-v1', 'grade': '10-11',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 2}]}
        tasks, report, _ = assemble.build_event(str(root), event, str(root / 'f'), crop=False)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['4'].solution, ['1) Самый высокий доход приносит вклад.'])
        self.assertEqual(by['5'].solution, ['Покупать одежду в конце сезона.'])
        self.assertEqual(report['повтор условия в файле решений — мимо'], 1)
        self.assertEqual(report['повтор условия в начале решения — срезан'], 1)
        # Решение, которое лишь начинается похоже, но несёт ответ, не срезается целиком.
        self.assertEqual(assemble.strip_statement_echo('Как применить поговорку?',
                                                       'Как применить поговорку?'),
                         'Как применить поговорку?')


_WORDS = ['налог', 'вклад', 'акция', 'облигация', 'кредит', 'страховка', 'пенсия', 'ипотека',
          'лизинг', 'франшиза', 'дивиденд', 'бюджет', 'инфляция', 'депозит', 'вексель']


def _q(n, topic):
    a, b, c = _WORDS[n % 15], _WORDS[(n * 4 + 1) % 15], _WORDS[(n * 7 + 3) % 15]
    return (f'{topic.capitalize()}: что из перечисленного верно про {a}, {b} и {c} '
            f'в ситуации {n}?\n\n- A. {a} важнее\n- B. {c} важнее')


class AssembleSectionsTests(SimpleTestCase):
    """МОШ-предпринимательство, финалы: несколько тестов в файле теста,
    повторный сброс нумерации в файле условий, ответы с повтором вопроса."""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        self.root = Path(tempfile.mkdtemp(prefix='finbiz2_sec_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def page(self, page_dir, n, blocks):
        from problems.olympiad_audit import transcribe
        transcribe.Transcriber._write(str(self.root / page_dir / f'p{n}.json'),
                                      {'status': 'ok', 'blocks': blocks})

    def build(self, event):
        from problems.olympiad_audit import assemble
        return assemble.build_event(str(self.root), event, str(self.root / 'f'), crop=False)

    def test_9_two_tests_in_test_file_do_not_merge(self):
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест1')}
                                 for n in range(1, 11)])
        self.page('pages/t', 2, [{'type': 'task', 'number': '', 'text': 'Тест № 2.'}] +
                  [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест2')} for n in (1, 2, 3)])
        event = {'event_id': 'mosh-entrepreneurship-2010-final-8-11-v1', 'grade': '8-11',
                 'task_files': [{'file': 'raw/pdf/tasks-entr-test-final-2009-10.pdf',
                                 'page_dir': 'pages/t', 'pages': 2}]}
        tasks, report, _ = self.build(event)
        numbers = [t.number for t in tasks]
        self.assertEqual(len(tasks), 13)
        self.assertIn('тест-1.10', numbers)
        self.assertIn('тест-2.3', numbers)
        self.assertEqual({t.number: t for t in tasks}['тест-2.1'].statement, [_q(1, 'тест2')])

    def test_10_second_restart_makes_subquestions_of_next_task(self):
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест')}
                                 for n in range(1, 11)])
        self.page('pages/t', 2, [{'type': 'task', 'number': '2', 'text': 'Задание 2. Блок-схема.'},
                                 {'type': 'task', 'number': '3', 'text': 'Задание 3. Задачи.'}])
        self.page('pages/t', 3, [{'type': 'task', 'number': str(n), 'text': f'Кейс, вопрос {n}.'}
                                 for n in (1, 2, 3)])
        event = {'event_id': 'mosh-entrepreneurship-2014-final-10-11-v1', 'grade': '10-11',
                 'task_files': [{'file': 'raw/pdf/tasks-entr-10-11-final-13-4.pdf',
                                 'page_dir': 'pages/t', 'pages': 3}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual(len(tasks), 15)
        self.assertEqual(by['2'].statement, ['Задание 2. Блок-схема.'])
        self.assertEqual(by['4.1'].statement, ['Кейс, вопрос 1.'])
        self.assertIn('тест-10', by)
        self.assertEqual(report['нумерация снова с 1: подпункты следующего задания'], 1)

    def test_11_answers_with_repeated_question_matched_by_text(self):
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест')}
                                 for n in range(1, 11)])
        self.page('pages/t', 2, [{'type': 'task', 'number': str(n), 'text': f'Задача {n}: посчитайте '
                                  f'доход семьи Петровых за {n + 2} года.'} for n in (1, 2)])
        # Ответы: вопрос теста повторён с отмеченным ответом, номер «1»; затем
        # решение без повтора вопроса с номером «7» — только тест-7.
        self.page('pages/s', 1, [
            {'type': 'task', 'number': '1', 'text': _q(1, 'тест'), 'answer': 'A'},
            {'type': 'solution', 'number': '7', 'text': 'Ответ: B'},
            {'type': 'task', 'number': '1', 'text': 'Задача 1: посчитайте доход семьи '
                                                    'Петровых за 3 года.'},
            {'type': 'solution', 'number': '1', 'text': 'Доход 300 тыс.'}])
        event = {'event_id': 'mosh-entrepreneurship-2014-final-8-9-v1', 'grade': '8-9',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 2}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['тест-1'].answer, 'A')
        self.assertEqual(by['1'].answer, '')
        self.assertEqual(by['тест-7'].solution, ['Ответ: B'])
        self.assertEqual(by['1'].solution, ['Доход 300 тыс.'])
        self.assertEqual(by['тест-1'].solution, [])

    def test_12_answer_grid_blank_gives_test_answers(self):
        from problems.olympiad_audit import assemble
        marks = ('| 1 | 2 | 3 |\n|---|---|---|\n| 1 | 1 (отмечено) | 1 |\n'
                 '| 2 (отмечено) | 2 | 2 |\n| 3 | 3 | 3 (отмечено) |')
        self.assertEqual(assemble.parse_answer_grid('БЛАНК ОТВЕТОВ\n\n' + marks),
                         {'1': '2', '2': '1', '3': '3'})
        plus = ('**Тест № 1. Ответы**\n\n| № | А | В | С | № | А | В | С |\n'
                '|---|---|---|---|---|---|---|---|\n| 1 | | | + | 11 | + | | |\n'
                '| 2 | + | | | 12 | | + | |')
        self.assertEqual(assemble.parse_answer_grid(plus),
                         {'1': 'С', '2': 'А', '11': 'А', '12': 'В'})
        # Обычная таблица данных — не бланк.
        self.assertEqual(assemble.parse_answer_grid('| Q | P |\n|---|---|\n| 1 | 10 |\n| 2 | 8 |'),
                         {})
        self.page('pages/t', 1, [{'type': 'task', 'number': str(n), 'text': _q(n, 'тест')}
                                 for n in range(1, 4)])
        self.page('pages/s', 1, [{'type': 'task', 'number': '', 'text': 'БЛАНК ОТВЕТОВ\n\n' + marks}])
        event = {'event_id': 'mosh-entrepreneurship-2013-final-7-v1', 'grade': '7',
                 'task_files': [{'file': 'raw/pdf/tasks-finance-7-test-final.pdf',
                                 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/otvet.pdf', 'page_dir': 'pages/s',
                                     'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual((by['тест-1'].answer, by['тест-3'].answer), ('2', '3'))
        self.assertEqual(report['бланк ответов → ответы теста'], 3)

    def test_13_kit_number_in_header_is_not_variant(self):
        from problems.olympiad_audit import assemble
        self.assertEqual(assemble._variant_of_header(
            {'variant': 'Комплект заданий № 2 (основы потребительских знаний)'}), '')
        self.assertEqual(assemble._variant_of_header({'variant': 'Решебник, 16 марта 2014 г.'}), '')
        self.assertEqual(assemble._variant_of_header({'variant': '2 Вариант'}), '2')
        self.assertEqual(assemble._variant_of_header({'variant': '1'}), '1')

    def test_14_solution_inside_repeated_statement(self):
        statement = ('Петр приобрел во время весенней распродажи сноуборд. Следующей зимой он '
                     'обнаружил, что основание доски расслоилось. Удастся ли Петру вернуть деньги?')
        self.page('pages/t', 1, [{'type': 'task', 'number': '1', 'text': statement},
                                 {'type': 'task', 'number': '2', 'text': 'Другая ситуация про '
                                  'кастрюлю для индукционной плиты и коробку от другой кастрюли.'}])
        self.page('pages/s', 1, [{'type': 'task', 'number': '1', 'text': statement + '\n\nСТ. 18'},
                                 {'type': 'task', 'number': '2', 'text': 'Другая ситуация про '
                                  'кастрюлю для индукционной плиты и коробку от другой кастрюли.'}])
        event = {'event_id': 'mosh-entrepreneurship-2014-final-7-v1', 'grade': '7',
                 'task_files': [{'file': 'raw/pdf/t.pdf', 'page_dir': 'pages/t', 'pages': 1}],
                 'solution_files': [{'file': 'raw/pdf/s.pdf', 'page_dir': 'pages/s', 'pages': 1}]}
        tasks, report, _ = self.build(event)
        by = {t.number: t for t in tasks}
        self.assertEqual(by['1'].solution, ['СТ. 18'])
        self.assertEqual(by['2'].solution, [])
        self.assertEqual(report['решение внутри повтора условия'], 1)
        from problems.olympiad_audit import assemble
        self.assertEqual(assemble.strip_statement_echo(
            '**5. Задача 5**\n\nЧто относится к природным ресурсам Земли?\n\n4. **торф** (отмечено)',
            'Что относится к природным ресурсам Земли?\n\n1. рыба\n4. торф'),
            '4. **торф** (отмечено)')
