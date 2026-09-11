# -*- coding: utf-8 -*-
"""Числовой отпечаток условия — ССЫЛКА на единственный экземпляр эвристики.

Сама эвристика переехала в `problems/dedup_gates.py`: её зовёт не только
разведка, но и боевая команда `manage.py dedup_apply`, а команда не может
тянуть код из `scripts/`. Здесь остался тонкий переходник, чтобы скрипты
разведки (`dedup_phase_b_*.py`) и их тесты продолжали работать как раньше.

Двух копий эвристики в проекте быть не должно: числовой гейт — единственное,
что разводит задачи одного сюжета с разными параметрами, и расхождение копий
означало бы, что разведка и боевой прогон меряют по-разному.
"""
import os
import sys

# Скрипты запускаются как `python scripts/foo.py`: в sys.path попадает папка
# скрипта, а корень репозитория — нет. Добавляем его явно.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from problems.dedup_gates import (  # noqa: E402,F401
    compare_numbers,
    extract_numbers,
    numbers_jaccard as jaccard,
)

__all__ = ['compare_numbers', 'extract_numbers', 'jaccard']
