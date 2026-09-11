# -*- coding: utf-8 -*-
"""Зубастость: каждый дефект возвращается в код и обязан покраснить тест.

Тест, который не краснеет от возвращённого дефекта, ничего не стережёт —
он просто зелёный. Скрипт правит файл, гоняет один тест, требует падения
и возвращает файл побайтово обратно (в `finally`, а не «после»: обрыв на
середине оставил бы дефект в рабочем дереве).

⚠️ Мутация, текст которой в коде НЕ НАЙДЕН, считается провалом, а не
пропуском. Иначе стенд молча вырождается: код уезжает вперёд, мутации
перестают применяться, а отчёт продолжает показывать «все красные».

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

POOL = 'reports/llm_search_eval/poolbuild.py'
CLIENT = 'reports/llm_search_eval/orclient.py'
BRIDGE = 'reports/llm_search_eval/envbridge.py'
JUDGE = 'reports/llm_search_eval/judging.py'
METRICS = 'reports/llm_search_eval/metrics.py'
CONCEPTS = 'reports/llm_search_eval/concepts.py'
LEX = 'catalog/lexical_bm25.py'
PROVIDERS = 'problems/ai/providers.py'
RERANK = 'reports/llm_search_eval/reranking.py'

#: (имя, файл, что заменить, на что, каким тестом ловим, вид запуска)
MUTATIONS = [
    # ── сборка пула ────────────────────────────────────────────────────
    ('RRF считает без учёта ранга', POOL,
     'return 1.0 / (RRF_K + rank + 1)', 'return 1.0',
     'test_poolbuild.RrfTests', UNIT),
    ('k слияния не 60', POOL,
     'RRF_K = 60', 'RRF_K = 10',
     'test_poolbuild.RrfTests.test_вес_считается_по_рангу_с_k_60', UNIT),
    ('дубли из группы остаются в пуле', POOL,
     'if group is None or best[group] == pid:', 'if True:',
     'test_poolbuild.DedupTests', UNIT),
    ('представителем становится первый попавшийся, а не фаворит', POOL,
     'if current is None or (is_best and not groups[current][1]):',
     'if current is None:',
     'test_poolbuild.DedupTests.test_из_группы_остаётся_фаворит', UNIT),
    ('размер пула не проверяется', POOL,
     'if not POOL_MIN <= len(pool) <= POOL_MAX:', 'if False:',
     'test_poolbuild.InvariantTests.test_маленький_пул_роняет', UNIT),
    ('верхняя граница пула не 300', POOL,
     'POOL_MIN, POOL_MAX = 30, 300', 'POOL_MIN, POOL_MAX = 30, 1000',
     'test_poolbuild.InvariantTests.test_большой_пул_роняет', UNIT),
    ('в пул пускают невидимые задачи', POOL,
     'outside = [pid for pid in pool if pid not in visible_ids]',
     'outside = []',
     'test_poolbuild.InvariantTests.test_невидимая_задача_роняет', UNIT),
    ('повтор id в пуле не ловится', POOL,
     'if len(pool) != len(set(pool)):', 'if False:',
     'test_poolbuild.InvariantTests.test_повтор_id_роняет', UNIT),
    ('пара из одной дедуп-группы не ловится', POOL,
     'if group in seen:', 'if False:',
     'test_poolbuild.InvariantTests.test_две_задачи_из_одной_группы_роняют', UNIT),
    ('граница короткого запроса не 4 слова', POOL,
     'SHORT_WORDS = 4', 'SHORT_WORDS = 40',
     'test_poolbuild.QueryTypeTests.test_пять_слов_уже_описательный', UNIT),
    ('пунктуация считается словом', POOL,
     'words = [w for w in text.split() if any(c.isalpha() for c in w)]',
     'words = text.split()',
     'test_poolbuild.QueryTypeTests.test_пунктуация_не_считается_словом', UNIT),

    # ── клиент: бюджет, повторы, журнал, разбор ────────────────────────
    ('потолок проверяется после вызова, а не до', CLIENT,
     'if spent + float(estimated_usd) > ceiling:', 'if False:',
     'test_orclient.BudgetTests.test_превышение_бюджета_останавливает_до_вызова',
     UNIT),
    ('потолок общий, а не по провайдерам', CLIENT,
     '        spent = self.spent.get(provider, 0.0)',
     '        spent = sum(self.spent.values())',
     'test_orclient.BudgetTests.test_потолок_одного_провайдера_не_запирает_другого',
     UNIT),
    ('слово провайдера о цене игнорируется', CLIENT,
     'if reply.cost_usd is not None:', 'if False:',
     'test_orclient.BudgetTests.test_потрачено_растёт_по_стоимости_из_ответа',
     UNIT),
    ('прайс провайдера не найден и считается нулём', CLIENT,
     'price_in, price_out = PRICES.get((provider, model), (0.0, 0.0))',
     'price_in, price_out = (0.0, 0.0)',
     'test_orclient.BudgetTests.test_без_цены_от_провайдера_считаем_по_прайсу',
     UNIT),
    ('пиковый тариф DeepSeek не применяется', CLIENT,
     "    if provider == 'deepseek':", '    if False:',
     'test_orclient.BudgetTests.test_у_deepseek_пиковый_тариф_вдвое_дороже', UNIT),
    ('выходные считаются пиком', CLIENT,
     '    if moment.weekday() >= 5:', '    if False:',
     'test_orclient.BudgetTests.test_пик_определяется_по_часу_utc_и_дню_недели',
     UNIT),
    ('журнал отказов пишется после паузы', CLIENT,
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
    ('пауза между попытками постоянная', CLIENT,
     'self.sleep(BACKOFF_BASE ** attempt)', 'self.sleep(2)',
     'test_orclient.RetryTests.test_пауза_растёт_экспоненциально', UNIT),
    ('массив вместо объекта роняет всю пачку', CLIENT,
     '    if not isinstance(data, list):', '    if True:',
     'test_orclient.JsonParseTests.test_массив_вместо_объекта_склеивается_в_объект',
     UNIT),
    ('обёртка rows не разворачивается', CLIENT,
     "        rows = data.get('rows')", '        rows = None',
     'test_orclient.JsonParseTests.test_обёртка_rows_разворачивается', UNIT),
    ('обрезанный JSON не чинится', CLIENT,
     '        return _as_object(_repair_truncated(body))', '        return {}',
     'test_orclient.JsonParseTests.test_обрезанный_json_отдаёт_разобранную_часть',
     UNIT),
    ('неразобранный ответ отдаёт пустой объект', CLIENT,
     "        raise ValueError('Не похоже на JSON: %r' % text[:60])",
     '        return {}',
     'test_orclient.JsonParseTests.test_совсем_не_json_даёт_ошибку_а_не_пустой_объект',
     UNIT),
    ('файл .env перетирает заданную переменную', CLIENT,
     'if name and name not in env:', 'if name:',
     'test_orclient.EnvFileTests.test_уже_заданная_переменная_не_перетирается',
     UNIT),

    # ── мост ключей ────────────────────────────────────────────────────
    ('ключ Z.ai не пробрасывается под именем кода', BRIDGE,
     "ALIASES = {'ZAI_API_KEY': 'GLM_API_KEY'}", 'ALIASES = {}',
     'test_envbridge.AliasTests.test_zai_пробрасывается_под_именем_glm', UNIT),
    ('псевдоним перетирает заданный в оболочке ключ', BRIDGE,
     'if env.get(source) and target not in env:', 'if env.get(source):',
     'test_envbridge.AliasTests.test_уже_заданный_glm_сильнее_файла', UNIT),
    ('в отчёт о ключах попадает значение', BRIDGE,
     '    return {name: bool(env.get(name)) for name in EXPECTED}',
     "    return {name: env.get(name, '') for name in EXPECTED}",
     'test_envbridge.PresenceTests.test_отчёт_только_да_нет', UNIT),

    # ── разметка судьями ───────────────────────────────────────────────
    ('условие в карточке судьи не обрезается', JUDGE,
     "(row.get('statement') or '')[:STATEMENT_CHARS]",
     "(row.get('statement') or '')",
     'test_judging.CardTests.test_условие_обрезано_шестьюстами_знаками', UNIT),
    ('дано и найти не обрезаются', JUDGE,
     "'дано: %s' % (row.get('given') or '')[:FIELD_CHARS]",
     "'дано: %s' % (row.get('given') or '')",
     'test_judging.CardTests.test_дано_и_найти_обрезаны_тремястами', UNIT),
    ('сложность 0 превращается в пустоту', JUDGE,
     "row.get('difficulty') if row.get('difficulty')",
     "row.get('difficulty') if row.get('difficulty') and row.get('difficulty')",
     'test_judging.CardTests.test_сложность_ноль_не_превращается_в_пустоту', UNIT),
    ('пачка не по 25', JUDGE,
     'BATCH = 25', 'BATCH = 7',
     'test_judging.BatchTests.test_пачки_по_двадцать_пять', UNIT),
    ('пропущенный кандидат молча получает ноль', JUDGE,
     '    missing = [pid for pid in expected_ids if pid not in labels]',
     '    labels.update({pid: 0 for pid in expected_ids if pid not in labels})\n    missing = []',
     'test_judging.ParseTests.test_пропущенный_кандидат_назван_а_не_занулён', UNIT),
    ('чужой id принимается как свой', JUDGE,
     '        if pid not in expected:', '        if False:',
     'test_judging.ParseTests.test_чужой_id_уходит_в_лишние', UNIT),
    ('метка вне шкалы проходит как есть', JUDGE,
     '        labels[pid] = max(0, min(2, score))', '        labels[pid] = score',
     'test_judging.ParseTests.test_метка_вне_шкалы_прижимается_к_границе', UNIT),
    ('разногласие судей не помечается', JUDGE,
     "'disagreement': a != b", "'disagreement': False",
     'test_judging.MergeTests.test_спор_годится_против_не_годится_даёт_спорно_с_флагом',
     UNIT),
    ('одного «годится» хватает для итогового «годится»', JUDGE,
     '        if a == 2 and b == 2:', '        if a == 2 or b == 2:',
     'test_judging.MergeTests.test_годится_против_спорно_тоже_спорно', UNIT),
    ('спорное остаётся в бинарном согласии', JUDGE,
     '              if machine[pid] != 1 and manual[pid] != 1]', '              ]',
     'test_judging.AgreementTests.test_спорное_выброшено_из_бинарной_доли', UNIT),

    ('мягкое правило требует согласия обоих', JUDGE,
     "        if a == 2 or b == 2:", "        if a == 2 and b == 2:",
     'test_judging.MergeRuleTests.test_мягкое_засчитывает_одну_двойку', UNIT),
    ('строгое правило прощает один ноль', JUDGE,
     "        if a == 0 or b == 0:", "        if a == 0 and b == 0:",
     'test_judging.MergeRuleTests.test_строгое_роняет_пару_от_одного_нуля', UNIT),
    ('неизвестное правило тихо откатывается к строгому', JUDGE,
     "    if rule == 'строгое':", "    if rule in ('строгое', 'как-нибудь'):",
     'test_judging.MergeRuleTests.test_неизвестное_правило_ошибка_а_не_тихий_откат',
     UNIT),

    # ── реранкер ───────────────────────────────────────────────────────
    ('в карточку реранкера попадает условие', RERANK,
     "'тип: %s' % (row.get('problem_type') or ''),",
     "'условие: %s' % (row.get('statement') or ''),",
     'test_reranking.CardTests.test_карточка_короткая_и_без_условия', UNIT),
    ('пометка о совпавших понятиях не пишется', RERANK,
     '    if concept_hits:', '    if False:',
     'test_reranking.CardTests.test_пометка_о_совпавших_понятиях_попадает_в_карточку',
     UNIT),
    ('неоценённый кандидат получает ноль вместо хвоста', RERANK,
     '        ranked += [pid for pid in all_ids if pid not in scores]',
     '        ranked = sorted(set(ranked) | set(all_ids))',
     'test_reranking.MergeTests.test_кандидат_без_балла_уходит_в_хвост', UNIT),
    ('балл вне шкалы не прижимается', RERANK,
     'return max(0, min(100, int(score)))', 'return int(score)',
     'test_reranking.MergeTests.test_балл_вне_шкалы_прижимается', UNIT),

    # ── метрики ────────────────────────────────────────────────────────
    ('спорное засчитывается как годное', METRICS,
     'GOOD = 2', 'GOOD = 1',
     'test_metrics.PrecisionTests.test_спорное_не_считается_годным', UNIT),
    ('precision делится на k, а не на показанные', METRICS,
     'return sum(1 for label in shown if label >= GOOD) / len(shown)',
     'return sum(1 for label in shown if label >= GOOD) / k',
     'test_metrics.PrecisionTests.test_выдача_короче_k_делится_на_её_длину', UNIT),
    ('прирост nDCG линейный, а не 2^метка − 1', METRICS,
     'gains = [2 ** label - 1 for label in _labels_of(ranked, labels, k)]',
     'gains = [label for label in _labels_of(ranked, labels, k)]',
     'test_metrics.NdcgTests.test_число_на_известном_примере', UNIT),
    ('верхняя оценка без разметки отдаёт ноль', METRICS,
     '    if not shown:\n        return None', '    if not shown:\n        return 0.0',
     'test_metrics.PrecisionAmongLabelledTests.test_совсем_без_разметки_даёт_none_а_не_ноль',
     UNIT),

    # ── словарь понятий ────────────────────────────────────────────────
    ('«ё» и «е» разводят понятие на два', CONCEPTS,
     "(name or '').lower().replace('ё', 'е')", "(name or '').lower()",
     'test_concepts.MatchTests.test_ё_в_запросе_находит_ё_в_словаре', UNIT),
    ('несловарное понятие молча проходит в пул', CONCEPTS,
     '        if canonical is None:', '        if False:',
     'test_concepts.MatchTests.test_несловарное_уходит_в_отчёт', UNIT),
    ('понятие весит столько же, сколько тег', CONCEPTS,
     'CONCEPT_WEIGHT = 2', 'CONCEPT_WEIGHT = 1',
     'test_concepts.ScoreTests.test_понятие_весит_вдвое_против_тега', UNIT),

    # ── лексическая нога ───────────────────────────────────────────────
    ('лемматизации нет, ищем по словоформе', LEX,
     "cached = _morph().parse(token)[0].normal_form.replace('ё', 'е')",
     'cached = token',
     'catalog.tests.test_lexical_bm25.LemmaTests.test_падеж_не_разводит_слово',
     DJANGO),
    ('«ё» и «е» разводят слово на два', LEX,
     "_TOKEN.findall(text.lower().replace('ё', 'е'))",
     '_TOKEN.findall(text.lower())',
     'catalog.tests.test_lexical_bm25.LemmaTests.test_ё_и_регистр_не_разводят_слово',
     DJANGO),
    ('односимвольные предлоги попадают в отпечаток', LEX,
     'if len(token) < 2:', 'if False:',
     'catalog.tests.test_lexical_bm25.LemmaTests.test_однобуквенные_предлоги_не_попадают_в_отпечаток',
     DJANGO),
    ('тема, теги и понятия не входят в отпечаток', LEX,
     "    for name in ('topics', 'tags', 'concepts'):\n        pieces.extend(row.get(name) or [])",
     '    pass',
     'catalog.tests.test_lexical_bm25.IndexTextTests.test_в_отпечаток_входят_все_шесть_частей',
     DJANGO),
    ('нулевой вес BM25 пускают в пул', LEX,
     'if score > 0]', ']',
     'catalog.tests.test_lexical_bm25.SearchTests.test_запрос_без_общих_слов_не_выдаёт_ничего',
     DJANGO),

    # ── поставщики ─────────────────────────────────────────────────────
    ('стоимость у посредника не запрашивается', PROVIDERS,
     "                extra_body={'usage': {'include': True}},",
     '                extra_body={},',
     'problems.tests.test_openrouter_provider.RequestShapeTests.test_стоимость_запрашивается_явно',
     DJANGO),
    ('молчание посредника о цене читается как ноль', PROVIDERS,
     '        cost = float(cost) if isinstance(cost, (int, float)) else None',
     '        cost = float(cost) if isinstance(cost, (int, float)) else 0.0',
     'problems.tests.test_openrouter_provider.UsageTests.test_без_стоимости_поле_none_а_не_ноль',
     DJANGO),
    ('кэш DeepSeek читается из чужого поля', PROVIDERS,
     "        cache_read = _num(usage, 'prompt_cache_hit_tokens')",
     "        cache_read = _num(getattr(usage, 'prompt_tokens_details', None),\n                          'cached_tokens')",
     'problems.tests.test_deepseek_provider.UsageTests.test_кэш_читается_из_своего_поля',
     DJANGO),
    ('DeepSeek получает поле thinking от GLM', PROVIDERS,
     "                extra_body={'reasoning_effort': effort},",
     "                extra_body={'reasoning_effort': effort, 'thinking': {'type': 'enabled'}},",
     'problems.tests.test_deepseek_provider.RequestShapeTests.test_поля_thinking_от_glm_здесь_нет',
     DJANGO),
    ('сырое исключение теряется по дороге в журнал', PROVIDERS,
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
    # ⚠️ PYTHONDONTWRITEBYTECODE обязателен, и вот почему. Отметка времени
    # в .pyc хранится с точностью до СЕКУНДЫ, а годность кэша решается по
    # паре «время + размер файла». Две мутации подряд в одном файле,
    # укоротившие его на одинаковое число байт в пределах одной секунды,
    # неотличимы друг от друга — Python берёт .pyc от предыдущей. Ровно
    # это и случилось на первом прогоне: мутация «массив вместо объекта»
    # была объявлена не пойманной, хотя тест её ловит.
    env = dict(os.environ, PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1')
    if kind is DJANGO:
        cmd = [PY, 'manage.py', 'test', target, '-v', '0']
        cwd = ROOT
    else:
        cmd = [PY, '-m', 'unittest', target]
        cwd = os.path.join(ROOT, 'reports', 'llm_search_eval')
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True).returncode


def main():
    red, failed = 0, []
    for name, rel, old, new, target, kind in MUTATIONS:
        path = os.path.join(ROOT, rel)
        with open(path, encoding='utf-8') as handle:
            original = handle.read()
        if old not in original:
            print('  НЕ ПРИМЕНИЛАСЬ (текста нет в коде): %s' % name)
            failed.append(name + ' — текст мутации устарел')
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
            failed.append(name)
        else:
            red += 1
            print('  красный: %s' % name)
    print('\nПокраснело %d из %d' % (red, len(MUTATIONS)))
    if failed:
        print('НЕ ПОЙМАНО:')
        for name in failed:
            print('  -', name)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
