# -*- coding: utf-8 -*-
"""Формулы — тем же разбором, что на сайте (`scripts/olympiad_contour_katex.js`).

Один вызов node на пакет текстов: разбор разделителей и KaTeX живут в JS,
чтобы повторять страницу, а не переписывать её логику на Python.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

SCRIPT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts',
                                       'olympiad_contour_katex.js'))
CHUNK = 20000


def check_texts(texts):
    """[текст] → [{errors, currency, text_in_math, unpaired}] того же порядка."""
    out = []
    for start in range(0, len(texts), CHUNK):
        chunk = list(texts[start:start + CHUNK])
        if not chunk:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, 'in.json'), os.path.join(tmp, 'out.json')
            with open(src, 'w', encoding='utf-8') as handle:
                json.dump(chunk, handle, ensure_ascii=False)
            subprocess.run(['node', SCRIPT, src, dst], check=True, capture_output=True, timeout=1800)
            with open(dst, encoding='utf-8') as handle:
                out.extend(json.load(handle))
    return out
