# -*- coding: utf-8 -*-
"""Зубастость: каждый дефект возвращается в код и обязан покраснить тест.

Тест, который не краснеет от возвращённого дефекта, ничего не стережёт —
он просто зелёный. Скрипт правит файл, гоняет один тест, требует
падения и возвращает файл побайтово обратно (в `finally`, а не «после»:
обрыв на середине оставил бы дефект в рабочем дереве).

Запуск:
    venv313\\Scripts\\python.exe reports/llm_search_eval/mutations.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = os.path.join(ROOT, 'venv313', 'Scripts', 'python.exe')

DJANGO = ('django', )
UNIT = ('unit', )

#: (имя, файл, что заменить, на что, каким тестом ловим, вид запуска)
MUTATIONS = [
    ('RRF считает без учёта ранга',
     'reports/llm_search_eval/poolbuild.py',
     'return 1.0 / (RRF_K + rank + 1)', 'return 1.0',
     'test_poolbuild.RrfTests', UNIT),
    ('k слияния не 60',
     'reports/llm_search_eval/poolbuild.py',
     'RRF_K = 60', 'RRF_K = 10',
     'test_poolbuild.RrfTests.test_вес_считается_по_рангу_с_k_60', UNIT),
    ('дубли из группы остаются в пуле',
     'reports/llm_search_eval/poolbuild.py',
     'if group is None or best[group] == pid:', 'if True:',
     'test_poolbuild.DedupTests', UNIT),
    ('представителем становится не фаворит, а первый попавшийся',
     'reports/llm_search_eval/poolbuild.py',
     'if current is None or (is_best and not groups[current][1]):',
     'if current is None:',
     'test_poolbuild.DedupTests.test_из_группы_остаётся_фаворит', UNIT),
    ('размер пула не проверяется',
     'reports/llm_search_eval/poolbuild.py',
     'if not POOL_MIN <= len(pool) <= POOL_MAX:', 'if False:',
     'test_poolbuild.InvariantTests.test_маленький_пул_роняет', UNIT),
    ('в пул пускают невидимые задачи',
     'reports/llm_search_eval/poolbuild.py',
     'outside = [pid for pid in pool if pid not in visible_ids]',
     'outside = []',
     'test_poolbuild.InvariantTests.test_невидимая_задача_роняет', UNIT),
    ('повтор id в пуле не ловится',
     'reports/llm_search_eval/poolbuild.py',
     'if len(pool) != len(set(pool)):', 'if False:',
     'test_poolbuild.InvariantTests.test_повтор_id_роняет', UNIT),
    ('пара из одной дедуп-группы не ловится',
     'reports/llm_search_eval/poolbuild.py',
     'if group in seen:', 'if False:',
     'test_poolbuild.InvariantTests.test_две_задачи_из_одной_группы_роняют', UNIT),
    ('глагол не делает запрос описательным',
     'reports/llm_search_eval/poolbuild.py',
     "if parsed and any(tag in parsed[0].tag for tag in _VERB_TAGS):",
     'if False:',
     'test_poolbuild.QueryTypeTests.test_глагол_делает_запрос_описательным_даже_коротким',
     UNIT),

    ('бюджет проверяется после вызова, а не до',
     'reports/llm_search_eval/orclient.py',
     'if self.spent + float(estimated_usd) > self.budget_usd:', 'if False:',
     'test_orclient.BudgetTests.test_превышение_бюджета_останавливает_до_вызова',
     UNIT),
    ('слово посредника о цене игнорируется',
     'reports/llm_search_eval/orclient.py',
     'if reply.cost_usd is not None:', 'if False:',
     'test_orclient.BudgetTests.test_потрачено_растёт_по_стоимости_из_ответа',
     UNIT),
    ('без цены посредника считаем ноль',
     'reports/llm_search_eval/orclient.py',
     "price_in, price_out = PRICES.get(model, (0.0, 0.0))",
     'price_in, price_out = (0.0, 0.0)',
     'test_orclient.BudgetTests.test_без_цены_от_посредника_считаем_по_прайсу',
     UNIT),
    ('журнал отказов пишется после паузы',
     'reports/llm_search_eval/orclient.py',
     """                self._log_failure(stage, query_id, model, attempt, error,
                                  will_retry)
                last = error
                if not will_retry:
                    break
                self.sleep(BACKOFF_BASE ** attempt)""",
     """                last = error
                if not will_retry:
                    self._log_failure(stage, query_id, model, attempt, error,
                                      will_retry)
                    break
                self.sleep(BACKOFF_BASE ** attempt)
                self._log_failure(stage, query_id, model, attempt, error,
                                  will_retry)""",
     'test_orclient.FailureLogTests.test_запись_ложится_на_диск_до_паузы', UNIT),
    ('пауза между попытками постоянная',
     'reports/llm_search_eval/orclient.py',
     'self.sleep(BACKOFF_BASE ** attempt)', 'self.sleep(2)',
     'test_orclient.RetryTests.test_пауза_растёт_экспоненциально', UNIT),
    ('массив вместо объекта роняет всю пачку',
     'reports/llm_search_eval/orclient.py',
     '    if not isinstance(data, list):',
     '    if True:',
     'test_orclient.JsonParseTests.test_массив_вместо_объекта_склеивается_в_объект',
     UNIT),
    ('обрезанный JSON не чинится',
     'reports/llm_search_eval/orclient.py',
     '        return _as_object(_repair_truncated(body))',
     '        return {}',
     'test_orclient.JsonParseTests.test_обрезанный_json_отдаёт_разобранную_часть',
     UNIT),
    ('неразобранный ответ отдаёт пустой объект',
     'reports/llm_search_eval/orclient.py',
     "        raise ValueError('Не похоже на JSON: %r' % text[:60])",
     '        return {}',
     'test_orclient.JsonParseTests.test_совсем_не_json_даёт_ошибку_а_не_пустой_объект',
     UNIT),
    ('файл .env перетирает заданную переменную',
     'reports/llm_search_eval/orclient.py',
     'if name and name not in env:', 'if name:',
     'test_orclient.EnvFileTests.test_уже_заданная_переменная_не_перетирается',
     UNIT),

    ('лемматизации нет, ищем по словоформе',
     'catalog/lexical_bm25.py',
     "cached = _morph().parse(token)[0].normal_form.replace('ё', 'е')",
     'cached = token',
     'catalog.tests.test_lexical_bm25.LemmaTests.test_падеж_не_разводит_слово',
     DJANGO),
    ('«ё» и «е» разводят слово на два',
     'catalog/lexical_bm25.py',
     "_TOKEN.findall(text.lower().replace('ё', 'е'))",
     '_TOKEN.findall(text.lower())',
     'catalog.tests.test_lexical_bm25.LemmaTests.test_ё_и_регистр_не_разводят_слово',
     DJANGO),
    ('односимвольные предлоги попадают в отпечаток',
     'catalog/lexical_bm25.py',
     'if len(token) < 2:', 'if False:',
     'catalog.tests.test_lexical_bm25.LemmaTests.test_однобуквенные_предлоги_не_попадают_в_отпечаток',
     DJANGO),
    ('тема, теги и понятия не входят в отпечаток',
     'catalog/lexical_bm25.py',
     "    for name in ('topics', 'tags', 'concepts'):\n        pieces.extend(row.get(name) or [])",
     '    pass',
     'catalog.tests.test_lexical_bm25.IndexTextTests.test_в_отпечаток_входят_все_шесть_частей',
     DJANGO),
    ('нулевой вес BM25 пускают в пул',
     'catalog/lexical_bm25.py',
     'if score > 0]', ']',
     'catalog.tests.test_lexical_bm25.SearchTests.test_запрос_без_общих_слов_не_выдаёт_ничего',
     DJANGO),

    ('стоимость у посредника не запрашивается',
     'problems/ai/providers.py',
     "                extra_body={'usage': {'include': True}},",
     '                extra_body={},',
     'problems.tests.test_openrouter_provider.RequestShapeTests.test_стоимость_запрашивается_явно',
     DJANGO),
    ('молчание посредника о цене читается как ноль',
     'problems/ai/providers.py',
     "        cost = float(cost) if isinstance(cost, (int, float)) else None",
     '        cost = float(cost) if isinstance(cost, (int, float)) else 0.0',
     'problems.tests.test_openrouter_provider.UsageTests.test_без_стоимости_поле_none_а_не_ноль',
     DJANGO),
    ('сырое исключение теряется по дороге в журнал',
     'problems/ai/providers.py',
     """        except openai.APIStatusError as error:
            kind = 'no_key' if error.status_code in (401, 403) else 'other'
            raise self._fail(error, 'OpenRouter вернул ошибку (%s).'
                             % error.status_code, kind=kind)""",
     """        except openai.APIStatusError as error:
            kind = 'no_key' if error.status_code in (401, 403) else 'other'
            raise ProviderError('OpenRouter вернул ошибку (%s).'
                                % error.status_code, kind=kind)""",
     'problems.tests.test_openrouter_provider.FailureTests.test_сырое_исключение_сохраняется_для_журнала_отказов',
     DJANGO),
]


def run(kind, target):
    if kind is DJANGO:
        cmd = [PY, 'manage.py', 'test', target, '-v', '0']
    else:
        cmd = [PY, '-m', 'unittest', target]
    # ⚠️ PYTHONDONTWRITEBYTECODE обязателен, и вот почему. Отметка времени
    # в .pyc хранится с точностью до СЕКУНДЫ, а годность кэша решается по
    # паре «время + размер файла». Две мутации подряд в одном файле,
    # укоротившие его на одинаковое число байт в пределах одной секунды,
    # неотличимы друг от друга — Python берёт .pyc от предыдущей. Ровно
    # это и случилось на первом прогоне: мутация «массив вместо объекта»
    # была объявлена не пойманной, хотя тест её ловит.
    env = dict(os.environ, PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1')
    cwd = ROOT if kind is DJANGO else os.path.join(ROOT, 'reports', 'llm_search_eval')
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True).returncode


def main():
    red, green_by_mistake = 0, []
    for name, rel, old, new, target, kind in MUTATIONS:
        path = os.path.join(ROOT, rel)
        with open(path, encoding='utf-8') as handle:
            original = handle.read()
        if old not in original:
            print('  ПРОПУСК (текст не найден): %s' % name)
            green_by_mistake.append(name + ' — не применилась')
            continue
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(original.replace(old, new, 1))
            code = run(kind, target)
        finally:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(original)
        if code == 0:
            print('  ЗЕЛЁНЫЙ — тест дефект НЕ ловит: %s' % name)
            green_by_mistake.append(name)
        else:
            red += 1
            print('  красный: %s' % name)
    print('\nПокраснело %d из %d' % (red, len(MUTATIONS)))
    if green_by_mistake:
        print('НЕ ПОЙМАНО:')
        for name in green_by_mistake:
            print('  -', name)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
