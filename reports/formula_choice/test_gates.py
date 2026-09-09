"""Фаза 4: зубастые проверки линейки выбора формулы.

Не часть общего прогона сайта (`scripts/run_tests.py`) — сессия не трогает
код каталога/поиска, только эти отчётные скрипты. Запускать вручную:

    venv313/Scripts/python.exe reports/formula_choice/test_gates.py

Каждая функция — один зубастый тест: возвращает (ok: bool, message: str).
Гейт «убедись, что тест краснеет при внесённом дефекте» проверялся руками
при написании (см. отчёт сессии) — здесь остаются позитивные версии,
собранные так, чтобы ЛЮБОЙ из четырёх названных в задании дефектов красил
их в FAIL.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_pool  # noqa: E402
import score  # noqa: E402

HERE = Path(__file__).resolve().parent


def test_score_finds_best_formula_on_synthetic_markup():
    """Синтетика: три формулы, заведомо лучшая — 'best' (все её топ-10 —
    подтверждённо годные), заведомо худшая — 'worst' (ни одной годной).
    Дефект-мишень: перепутать формулы местами при сборке пула/скоринга —
    тогда победителем назовётся не 'best'."""
    formulas = ['best', 'mid', 'worst', 'vec_v2_meta_first']
    good_ids = list(range(1, 11))     # 10 безусловно годных задач
    bad_ids = list(range(11, 21))     # 10 безусловно негодных
    mid_ids_a = good_ids[:5] + bad_ids[:5]

    top10 = {
        'best': [(i, 1.0 - i * 0.001) for i in good_ids],
        'mid': [(i, 1.0 - i * 0.001) for i in mid_ids_a],
        'worst': [(i, 1.0 - i * 0.001) for i in bad_ids],
        'vec_v2_meta_first': [(i, 1.0 - i * 0.001) for i in mid_ids_a],
    }
    merged = build_pool.merge_pool_for_query(top10, formulas)

    pool = {
        'formulas': formulas,
        'queries': [{'query_id': 'qx'}],
        'pool_per_query': {'qx': merged},
    }
    verdicts = {}
    for pid in good_ids:
        verdicts[('qx', pid)] = 'good'
    for pid in bad_ids:
        verdicts[('qx', pid)] = 'bad'

    result = score.run(pool, verdicts, verbose=False)
    if result is None:
        return False, 'score.run вернул None на полностью размеченном синтетическом наборе'

    agg = result['aggregate']
    ranking = sorted(formulas, key=lambda f: -agg[f]['precision10'])
    if ranking[0] != 'best':
        return False, f'победителем назван {ranking[0]!r}, а не best; agg={agg}'
    if agg['best']['precision10'] != 1.0:
        return False, f'best должен иметь precision@10 = 1.0, получено {agg["best"]["precision10"]}'
    if agg['worst']['precision10'] != 0.0:
        return False, f'worst должен иметь precision@10 = 0.0, получено {agg["worst"]["precision10"]}'
    return True, f'ranking={ranking}, best.precision10={agg["best"]["precision10"]}'


def test_pool_is_union_not_intersection():
    """Дефект-мишень: заменить `|` на `&` при сборке пула. Две формулы с
    ПОЛНОСТЬЮ непересекающимися топ-10 обязаны дать пул размером 20, а не 0."""
    formulas = ['a', 'b']
    top10 = {
        'a': [(i, 1.0) for i in range(1, 11)],
        'b': [(i, 1.0) for i in range(101, 111)],
    }
    merged = build_pool.merge_pool_for_query(top10, formulas)
    if len(merged) != 20:
        return False, f'ожидал 20 уникальных задач (объединение), получил {len(merged)}'
    return True, f'{len(merged)} уникальных задач в объединении двух непересекающихся топ-10'


def test_razmetka_hides_formula_names():
    """Дефект-мишень: случайно вписать имя формулы в карточку/данные
    страницы. Ищем все 16 системных имён формул в готовом HTML — их там
    не должно быть НИГДЕ (ни в видимом тексте, ни в data-атрибутах)."""
    path = HERE / 'razmetka.html'
    if not path.exists():
        return False, f'{path} не найден — страница ещё не собрана'
    html = path.read_text(encoding='utf-8')

    pool = build_pool.FORMULAS
    leaked = [name for name in pool if name in html]
    if leaked:
        return False, f'найдены имена формул в razmetka.html: {leaked}'
    return True, f'ни одно из {len(pool)} имён формул не встречается в razmetka.html'


def test_pool_scope_is_all_not_prod():
    """Дефект-мишень: сменить умолчание среза индекса на 'prod'. Пул обязан
    строиться по 'all' — иначе меряем формулу по обрезанному прод-банку
    (14 014 задач скрыты hidden_pending_review) вместо всего банка."""
    if build_pool.SCOPE != 'all':
        return False, f'build_pool.SCOPE = {build_pool.SCOPE!r}, а должен быть "all"'
    return True, 'build_pool.SCOPE == "all"'


TESTS = [
    test_score_finds_best_formula_on_synthetic_markup,
    test_pool_is_union_not_intersection,
    test_razmetka_hides_formula_names,
    test_pool_scope_is_all_not_prod,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            ok, msg = t()
        except Exception as exc:  # noqa: BLE001 — гейт обязан пережить любой дефект
            ok, msg = False, f'{type(exc).__name__}: {exc}'
        status = 'PASS' if ok else 'FAIL'
        print(f'[{status}] {t.__name__}: {msg}')
        if not ok:
            failed += 1
    print()
    if failed:
        print(f'{failed} из {len(TESTS)} тестов красные.')
        sys.exit(1)
    print(f'Все {len(TESTS)} теста зелёные.')


if __name__ == '__main__':
    main()
