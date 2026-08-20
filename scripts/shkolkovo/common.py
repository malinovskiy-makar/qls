# -*- coding: utf-8 -*-
"""
Общее для всех скриптов сессии выгрузки Школково.

Все данные — вне репозитория, путь меняется в одном месте.
"""
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(r"C:\Users\shipu\weconomics-data\shkolkovo")
RAW_DIR = DATA_DIR / "raw"
TEX_DIR = DATA_DIR / "tex"
PROBLEMS_DIR = DATA_DIR / "problems"
IMAGES_DIR = DATA_DIR / "images"
SAMPLES_DIR = DATA_DIR / "samples"

INDEX_FILE = DATA_DIR / "index.json"
THEMES_FILE = DATA_DIR / "themes.json"
DEPENDENCIES_FILE = DATA_DIR / "dependencies_global.json"
FAILED_TEX_FILE = DATA_DIR / "failed.json"
FAILED_IMAGES_FILE = DATA_DIR / "failed_images.json"
IMAGE_MAP_FILE = DATA_DIR / "image_map.json"

PHASE1_STATS_FILE = DATA_DIR / "phase_stats_1_collect_index.json"
PHASE2_STATS_FILE = DATA_DIR / "phase_stats_2_fetch_tex.json"
PHASE3_STATS_FILE = DATA_DIR / "phase_stats_3_fetch_images.json"

SITE = "https://3.shkolkovo.online"
LATEX_BASE = f"{SITE}/api/latex-service/v1/GetSession"

USER_AGENT = "Weconomics-import/1.0 (+https://t.me/lengler)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def ensure_dirs():
    for d in (DATA_DIR, RAW_DIR, TEX_DIR, PROBLEMS_DIR, IMAGES_DIR, SAMPLES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- три проверки качества .tex (Фаза 2) ---

MOJIBAKE_MARKERS = ("Ð", "Ñ", "Ã")
REPLACEMENT_CHAR = "\ufffd"


def check1_is_latex(raw: str) -> bool:
    """Проверка 1: это вообще LaTeX, а не страница WAF."""
    return ("\\documentclass" in raw) or ("\\begin{document}" in raw)


def check2_is_complete(raw: str) -> bool:
    """Проверка 2: файл не оборван — есть и begin, и end{document}."""
    return ("\\begin{document}" in raw) and ("\\end{document}" in raw)


def check3_encoding_ok(raw: str) -> bool:
    """Проверка 3: кодировка цела — нет U+FFFD и нет типичных кракозябр перед кириллицей."""
    if REPLACEMENT_CHAR in raw:
        return False
    for marker in MOJIBAKE_MARKERS:
        idx = raw.find(marker)
        if idx != -1:
            # ищем маркер, за которым (в пределах пары символов) идёт что-то похожее
            # на второй байт неправильно декодированной UTF-8 кириллицы —
            # практически всегда это тоже символ вне обычного ASCII-диапазона.
            tail = raw[idx: idx + 3]
            if any(ord(ch) > 127 for ch in tail[1:]):
                return False
    return True


def validate_tex(raw: str):
    """Возвращает (ok1, ok2, ok3). ok1=False -> аварийная остановка вызывающим кодом."""
    return check1_is_latex(raw), check2_is_complete(raw), check3_encoding_ok(raw)


def extract_body(raw: str):
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", raw, re.S)
    if not m:
        return None
    return m.group(1).strip()


class FatalStop(Exception):
    """Аварийная остановка прогона — не retry, не failed.json."""
