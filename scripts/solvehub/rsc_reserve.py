# -*- coding: utf-8 -*-
"""
РЕЗЕРВНЫЙ способ получить задачу с solvehub.app — через RSC-поток Next.js,
а не через боевой tRPC API (problems.getByHash в fetch_problems.py).

ЗАЧЕМ ЭТОТ ФАЙЛ. В Фазе 0 сначала не было известно про api.prod.solvehub.app —
казалось, что единственный способ достать задачу это распарсить RSC-payload
страницы (запрос с заголовком RSC: 1). Этот разбор был доведён до рабочего
состояния и в Фазе 0 (Проверка A) сверен с tRPC на пяти задачах: наборы полей
идентичны, значения совпадают побитово (кроме двух чисто протокольных мелочей —
см. ниже). Раз tRPC подтверждён как минимум не беднее, он стал основным
способом как более простой и надёжный. Этот модуль — на случай, если
api.prod.solvehub.app когда-нибудь перестанет отвечать или сменит контракт:
тогда есть проверенная и рабочая альтернатива, не с нуля.

НЕ используется автоматически из fetch_problems.py. Если боевой tRPC-путь
откажет посреди массового прогона — правильная реакция остановиться и
разобраться, а не молча смешать два способа получения данных в одном банке
(даже притом что сейчас известных расхождений в содержимом не осталось —
см. ниже; молчаливая подмена метода посреди прогона всё равно плохая идея).

ПРОТОКОЛ (react-server-dom flight wire format), как он был реверс-инжинирен:
  Ответ — поток чанков вида  <id>:<payload>
    id — счётчик в ШЕСТНАДЦАТЕРИЧНОМ виде (встречаются "5b", "5d" и т.п.;
         бывает и ПУСТОЙ id — например ":HL[...]" для preload-хинтов).
    payload бывает:
      - JSON-значение ([...] / {...} / "..."): обычная JSON-строка до конца
        логической строки, внутренние переводы строк уже экранированы как \n.
      - Текстовый чанк:  T<hex-длина>,<сырые UTF-8-байты ровно такой длины>
        Эти байты НЕ JSON-экранированы и могут буквально содержать что угодно,
        включая переводы строк, — поэтому резать по "\n" нельзя, только по
        объявленной длине.
  Объект задачи — в initialData.problems[0] внутри одного из JSON-чанков.
  Некоторые строковые поля этого объекта (замечено на "md") — не сам текст,
  а ссылка-токен "$<id>" на отдельный текстовый чанк; чтобы получить
  настоящее содержимое, ссылку нужно резолвить через словарь чанков.

ИЗВЕСТНОЕ РАСХОЖДЕНИЕ С tRPC (не критичное, см. отчёт сессии Фазы 0):
  - created_date / updated_at здесь приходят с префиксом "$D" (тип-тег
    React Flight для Date) — он тут сознательно не срезается при сыром
    сохранении. Значение то же самое, просто с меткой типа.

ПОЧИНЕНО (было расхождение с tRPC, больше нет). Буквальный "$" в начале
инлайновой JSON-строки (например LaTeX-формула, начинающаяся с "$") протокол
экранирует удвоением: "$$...". Для KaTeX это не косметика: один "$" — формула
в строке, два "$$" — формула отдельным блоком, рендерятся по-разному. Функция
resolve_refs разворачивает такой ведущий "$$" обратно в один "$" (см. её код
ниже). Проверено на всех пяти контрольных задачах Фазы 0 — совпадение с tRPC
побитовое, включая тот же answer_md, где расхождение изначально нашлось.
Фикс покрывает только ВЕДУЩИЙ "$$" в начале строки — это единственный
наблюдавшийся случай; если где-то в родине встретится текст, начинающийся
по смыслу с настоящего блочного "$$" (LaTeX display math), а не с
экранированного одиночного "$", он тоже потеряет один символ. Наблюдений
такого случая не было ни разу — предупреждение на будущее, не наблюдение.

ЛОВУШКА С КОДИРОВКОЙ: сервер не указывает charset в Content-Type ответа
(text/x-component), поэтому `requests` по умолчанию решает, что это
ISO-8859-1, и кириллица превращается в кракозябры при обращении к `.text`.
Здесь это обойдено через `r.content.decode("utf-8")` — байты на деле utf-8.
"""
import json
import re
import time

import requests

HEADERS = {
    "User-Agent": "Weconomics-import/1.0 (+https://t.me/lengler)",
    "RSC": "1",
    "Accept": "*/*",
}

CHUNK_HEAD = re.compile(r"([0-9a-fA-F]*):")
REF_RE = re.compile(r"^\$([0-9a-fA-F]+)$")


def fetch_raw(hash_):
    url = f"https://solvehub.app/econ/problems/{hash_}"
    r = requests.get(url, headers=HEADERS, timeout=40)
    r.raise_for_status()
    return url, r.status_code, r.content.decode("utf-8")


def parse_chunks(text):
    """Разбирает весь ответ на чанки {id: (type, value)}."""
    chunks = {}
    pos = 0
    n = len(text)
    while pos < n:
        m = CHUNK_HEAD.match(text, pos)
        if not m:
            break
        cid = m.group(1)
        pos = m.end()
        if pos < n and text[pos] == "T":
            m2 = re.match(r"T([0-9a-fA-F]+),", text[pos:])
            if not m2:
                raise ValueError(f"chunk {cid}: не смог разобрать заголовок T-чанка")
            length_bytes = int(m2.group(1), 16)
            payload_start = pos + m2.end()
            remaining_bytes = text[payload_start:].encode("utf-8")
            text_bytes = remaining_bytes[:length_bytes]
            if len(text_bytes) != length_bytes:
                raise ValueError(f"chunk {cid}: не хватает байт ({len(text_bytes)} из {length_bytes})")
            value = text_bytes.decode("utf-8")
            chunks[cid] = ("text", value)
            pos = payload_start + len(value)
            if pos < n and text[pos] == "\n":
                pos += 1
        else:
            newline_idx = text.find("\n", pos)
            if newline_idx == -1:
                newline_idx = n
            raw = text[pos:newline_idx]
            kind = "json" if raw[:1] in "[{\"" else f"other:{raw[:1]!r}"
            chunks[cid] = (kind, raw)
            pos = newline_idx + 1
    return chunks


def extract_balanced_json(text, start_idx):
    assert text[start_idx] == "{", text[start_idx:start_idx + 30]
    depth = 0
    in_string = False
    escape = False
    i = start_idx
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start_idx:i + 1]
        i += 1
    raise ValueError("не нашёл конец объекта — разбалансировано")


def resolve_refs(obj, chunks):
    """Резолвит строковые поля вида "$71" в реальные значения из чанков."""
    if isinstance(obj, dict):
        return {k: resolve_refs(v, chunks) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_refs(v, chunks) for v in obj]
    if isinstance(obj, str):
        m = REF_RE.match(obj)
        if m and m.group(1) in chunks:
            kind, raw = chunks[m.group(1)]
            if kind == "text":
                return raw
            if kind == "json":
                return resolve_refs(json.loads(raw), chunks)
        if obj.startswith("$$"):
            # Буквальный "$" в начале инлайновой JSON-строки экранируется удвоением
            # (иначе его можно спутать с началом ссылки "$<id>"). Настоящая ссылка
            # уже отработана выше через REF_RE, так что если мы здесь — это не
            # ссылка, и "$$" в начале нужно развернуть обратно в один "$".
            return "$" + obj[2:]
        return obj
    return obj


def find_problem_object(chunks):
    """Ищет среди json-чанков тот, что содержит initialData.problems, и вырезает problems[0]."""
    for cid, (kind, raw) in chunks.items():
        if kind == "json" and '"initialData"' in raw and '"problems":[' in raw:
            marker = '"problems":['
            idx = raw.find(marker)
            obj_start = raw.find("{", idx + len(marker))
            if obj_start == -1:
                continue
            problem_raw = extract_balanced_json(raw, obj_start)
            return cid, json.loads(problem_raw)
    return None, None


def fetch_problem_via_rsc(hash_):
    """Публичная точка входа резерва: возвращает объект задачи (как fetch_problem в fetch_problems.py)."""
    _url, _status, text = fetch_raw(hash_)
    chunks = parse_chunks(text)
    _src_cid, problem = find_problem_object(chunks)
    if problem is None:
        raise RuntimeError(f"{hash_}: не нашёл initialData.problems в RSC-потоке")
    return resolve_refs(problem, chunks)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Использование: python rsc_reserve.py <hash>")
        sys.exit(1)
    p = fetch_problem_via_rsc(sys.argv[1])
    print(json.dumps(p, ensure_ascii=False, indent=2))
