"""Снимок трёх полей Problem, которые разведочная сессия не имеет права менять.

Считает SHA-256 по отсортированному списку (id, status, duplicate_of_id,
hidden_pending_review). Запускается ДО и ПОСЛЕ сессии; хеши обязаны совпасть.
"""
import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from problems.models import Problem  # noqa: E402


def snapshot() -> dict:
    h = hashlib.sha256()
    n = 0
    for pid, status, dup, hidden in (
        Problem.objects.order_by('id')
        .values_list('id', 'status', 'duplicate_of_id', 'hidden_pending_review')
        .iterator(chunk_size=5000)
    ):
        h.update(f'{pid}|{status}|{dup}|{int(bool(hidden))}\n'.encode())
        n += 1
    return {'rows': n, 'sha256': h.hexdigest()}


if __name__ == '__main__':
    out = snapshot()
    print(json.dumps(out, ensure_ascii=False))
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
