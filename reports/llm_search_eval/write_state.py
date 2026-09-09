# -*- coding: utf-8 -*-
"""Записать STATE.json фазы -1. Только запись файла, базу не трогает."""
import json

state = {
    "session": "llm_search_eval",
    "started": "2026-09-09",
    "branch": "feat/llm-search-eval",
    "branch_base": "51ca189 (feat/embedding-formula-v2)",
    "branch_base_deviation": (
        "Промпт просил ветку от main. Взята от feat/embedding-formula-v2: на main НЕТ "
        "problems/data/eval_set_c_v3.json (это набор C65, один из двух эталонов) и НЕТ "
        "problems/embedding_formula.py со спецификацией активной формулы. От main эксперимент не собрать."
    ),
    "phase": "-1 done, ждём ответа владельца на стоп-гейт",
    "db": {
        "name": "C:/Users/shipu/qls/db.sqlite3",
        "engine": "sqlite3",
        "problem_total": 41307,
        "problempart_total": 65803,
        "fingerprint_problem_md5": "1cee0f22983268345cee9215b2f41254",
        "fingerprint_part_md5": "6fa997765dc8d8eb53428d9e82e34c41",
        "fingerprint_note": (
            "md5 по (id, statement, answer, solution), сортировка по id; сверить в конце "
            "сессии тем же скриптом reports/llm_search_eval/phase_minus1.py"
        ),
    },
    "taxonomy": {
        "econ_concepts": 1886,
        "econ_concept_sections": 33,
        "econ_concept_has_alias_field": False,
        "econ_concept_alias_note": (
            "У модели EconConcept ТОЛЬКО поля canonical и section. Алиасов нет. "
            "Сопоставление concepts_free — точное совпадение по canonical после "
            "нормализации регистра и «ё»."
        ),
        "topics_canonical": 29,
        "topics_total": 865,
        "tags_canonical": 344,
        "tags_total": 896,
        "problems_with_concepts": 38422,
        "title_candidate_nonempty": 40425,
    },
    "visibility": {
        "base_queryset_catalog": 14082,
        "base_queryset_tutor": 26914,
        "chosen_for_experiment": 14082,
        "note": (
            "hidden_pending_review НЕ снят. Все метрики считаются относительно "
            "14 082 видимых поиску задач."
        ),
    },
    "vectors": {
        "with_embedding": 41307,
        "versions": {"95": 41307},
        "builds": {"bge-m3/st-fp32": 41307},
        "active_spec_in_code": "v2_focus_repeat",
        "active_spec_version": 95,
        "visible_with_embedding": 14082,
        "expected_by_prompt": "v2_meta_first (версия 96)",
        "discrepancy": (
            "В банке v2_focus_repeat, не v2_meta_first. Переключение сделано коммитом "
            "51ca189 (09.09). build_check от 09.09 18:06: min_cosine 0.9999999 на 200 "
            "строках — файл и банк сходятся."
        ),
    },
    "semantic": {"enabled": True, "min_score": 0.40, "model": "BAAI/bge-m3", "dim": 1024},
    "reference_sets": {
        "C58": {"file": "problems/data/eval_set_c.json", "cases": 58},
        "C65": {"file": "problems/data/eval_set_c_v3.json", "cases": 61},
        "overlap": 58,
        "union_distinct": 61,
        "BLOCKER": (
            "C58 — ПОДМНОЖЕСТВО C65. Все 58 формулировок C58 есть в C65 (сверка по "
            "нормализованному тексту). Значит «119 запросов» — двойной счёт: "
            "различных формулировок 61."
        ),
        "anchors": "у каждого случая ровно один relevant_id, ни одного случая с двумя",
    },
    "manual_markup": {
        "file": "reports/formula_choice/razmetka_336.json",
        "rows": 336,
        "queries": 10,
        "scale": {"good": 183, "unsure": 111, "bad": 42},
        "pool_file": "reports/formula_choice/pool.json",
        "BLOCKER": (
            "Эти 10 запросов — НЕ отдельные, они взяты из eval_set_c_v3 "
            "(#44,#53,#42,#61,#2,#7,#46,#22,#62,#55) и входят в те же 61. "
            "Значит «129 = 119 + 10» — тоже двойной счёт."
        ),
    },
    "dedup": {
        "groups": 4571,
        "problems_in_groups": 10810,
        "dup_is_best": 4571,
        "visible_in_groups": 3644,
        "visible_groups": 2289,
    },
    "lexical_leg": {
        "catalog/lexical_bm25.py": False,
        "bm25s_installed": False,
        "pymorphy3_installed": "2.0.6",
        "hybrid.py": "существует, старый contains + RRF k=60, код-сирота",
        "prompt_hybrid_eval": "Claude outputs/PROMPT_HYBRID_EVAL_20260909.md — сессия НЕ выполнялась",
        "verdict": "ногу собираю в фазе 1",
    },
    "openrouter": {
        "OPENROUTER_API_KEY": False,
        "key_note": (
            "Ключа нет ни в окружении процесса, ни в пользовательских переменных Windows, "
            "ни в .env (файла .env в проекте нет). Без ключа фазы 1 (S_concept), 2 и 3 "
            "не запускаются."
        ),
        "models_endpoint": "GET https://openrouter.ai/api/v1/models — 200, 430 моделей",
        "slugs": {
            "GLM-5.3-Flash": {"slug": "z-ai/glm-5.3-flash", "in_per_mtok": 0.075,
                              "out_per_mtok": 0.25, "ctx": 1310720},
            "GLM-5.3": {"slug": "z-ai/glm-5.3", "in_per_mtok": 1.40,
                        "out_per_mtok": 4.40, "ctx": 1048576},
            "Claude Haiku 4.5": {"slug": "anthropic/claude-haiku-4.5", "in_per_mtok": 1.00,
                                 "out_per_mtok": 5.00, "ctx": 200000},
            "Claude Sonnet 5": {"slug": "anthropic/claude-sonnet-5", "in_per_mtok": 2.00,
                                "out_per_mtok": 10.00, "ctx": 1000000},
            "GPT-5.6 Sol": {"slug": "openai/gpt-5.6-sol", "in_per_mtok": 2.00,
                            "out_per_mtok": 10.00, "ctx": 1050000},
            "GPT-5.6 Terra": {"slug": "openai/gpt-5.6-terra", "in_per_mtok": 2.00,
                              "out_per_mtok": 12.00, "ctx": 1050000},
            "DeepSeek V4 Pro": {"slug": "deepseek/deepseek-v4-pro", "in_per_mtok": 0.87,
                                "out_per_mtok": 1.74, "ctx": 1048576},
        },
        "substitutions_needed": "нет, все семь моделей нашлись точными слагами",
    },
    "card_tokens_measured": {
        "sample": "200 случайных видимых задач, tiktoken o200k_base",
        "judge_card": {"mean": 349.4, "median": 350, "p90": 468, "max": 541},
        "rerank_card": {"mean": 162.8, "median": 158.5, "p90": 214, "max": 253,
                        "note": "промпт закладывал ~100 токенов; реально 163"},
        "concept_map_prefix": 4213,
    },
    "stop_gate_1": "не пройден: ждём ответа владельца",
}

with open('reports/llm_search_eval/STATE.json', 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=1)
print('STATE.json written')
