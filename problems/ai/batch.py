# -*- coding: utf-8 -*-
"""Batch API OpenAI: сборка JSONL, отправка, опрос, скачивание, разбор (Б3).

Готовим сразу под полный прогон обогащения (41 307 задач), но НЕ включаем
в этой сессии: включение — только после замера Б4 (пилот сравнивает
`--mode sync` и `--mode batch` на одной и той же выборке из 100 задач и
смотрит на фактические `cached_tokens` в ответе). Взаимодействие Batch и
кэша промпта нигде в документации OpenAI не описано, и от этого факта
смета всего прогона меняется втрое — гадать нельзя.

⚠️ ЭНДПОЙНТ ТРЕБУЕТ ПРОВЕРКИ ПЕРЕД ВКЛЮЧЕНИЕМ. `providers.OpenAIProvider.
complete()` зовёт `client.responses.create(...)` (Responses API), и `ENDPOINT`
ниже указан как `/v1/responses` по аналогии — этот модуль ни разу не
вызывал реальный Batch API. Сверьте с боевой документацией OpenAI на
момент включения: если Batch API поддерживает для вашей версии SDK только
`/v1/chat/completions`, тело строки JSONL (`body`) и разбор ответа придётся
переписать под chat.completions. Это единственное место в модуле, не
проверенное реальным вызовом, — если структура разойдётся с ожиданием,
не угадывайте, остановитесь.

Жёсткие ограничения (документация OpenAI, сверено 31.08.2026):
    - максимум 50 000 запросов в одном батче;
    - максимум 200 МБ на файл;
    - окно выполнения — 24 часа, другого значения нет;
    - скидка 50 % от обычного тарифа.

⚠️ РЕЖЕМ ПО БАЙТАМ, А НЕ ПО ЧИСЛУ СТРОК. Ядро промпта (~7 100 токенов)
повторяется в КАЖДОЙ строке JSONL — это примерно 17 КБ на строку, и в
200 МБ входит около 12 200 задач, а не 50 000. На 41 307 задач это минимум
четыре файла. Режем с запасом: жёсткий потолок `MAX_BYTES_PER_FILE`
(180 МБ) и `MAX_LINES_PER_FILE` (45 000) — какой раньше сработает.

⚠️ `custom_id` — ID задачи, и только он. По нему результат раскладывается
обратно после скачивания; без него частичный отказ по отдельной строке
нечем привязать к задаче.
"""
import json
import os
import time
from pathlib import Path

MAX_REQUESTS_PER_BATCH = 50000
MAX_BYTES_PER_FILE_HARD = 200 * 1024 * 1024

# Потолок с запасом — см. докстринг модуля.
MAX_BYTES_PER_FILE = 180 * 1024 * 1024
MAX_LINES_PER_FILE = 45000

ENDPOINT = '/v1/responses'
# Второй эндпойнт (Фаза 3, 2026-09-01) — замер на 200 строках проверяет,
# какой из двух Batch API реально принимает и кэширует префикс: сравнение
# делает выбор фактом, а не гаданием по неполной документации OpenAI.
CHAT_ENDPOINT = '/v1/chat/completions'
COMPLETION_WINDOW = '24h'

# Статусы Batch API, при которых батч ещё выполняется — не пора качать
# результат.
IN_PROGRESS_STATUSES = ('validating', 'in_progress', 'finalizing',
                        'cancelling')
# Статусы, при которых батч уже не сдвинется сам: либо готов, либо мёртв.
TERMINAL_STATUSES = ('completed', 'failed', 'expired', 'cancelled')


def build_request(custom_id, model, system_blocks, user_text, schema,
                  max_tokens, reasoning_effort=None):
    """Одна строка будущего JSONL — тело ТОЧНО как у `OpenAIProvider.complete`.

    Раздельные тела на каждый из двух вызовов Б2 (разные ядра, разные
    модели/эффорты) — вызывающий код собирает `custom_id` так, чтобы по
    нему можно было понять, какой это вызов (например `'{id}:1'` /
    `'{id}:2'`), и задачу, и вызов одновременно.
    """
    body = {
        'model': model,
        'max_output_tokens': max_tokens,
        'instructions': '\n\n'.join(system_blocks),
        'input': user_text,
        'text': {'format': {'type': 'json_schema', 'name': 'reply',
                            'strict': True, 'schema': schema}},
    }
    if reasoning_effort is not None:
        body['reasoning'] = {'effort': reasoning_effort}
    return {
        'custom_id': custom_id,
        'method': 'POST',
        'url': ENDPOINT,
        'body': body,
    }


def build_chat_request(custom_id, model, system_blocks, user_text, schema,
                       max_tokens, reasoning_effort=None):
    """Та же строка JSONL, что `build_request`, но тело — Chat Completions,
    а не Responses API (`CHAT_ENDPOINT`, не `ENDPOINT`). Формат ДВУХ
    эндпойнтов Batch API у OpenAI разный — этой функцией собирается вторая
    половина сравнения из Фазы 3.
    """
    body = {
        'model': model,
        'max_completion_tokens': max_tokens,
        'messages': [
            {'role': 'system', 'content': '\n\n'.join(system_blocks)},
            {'role': 'user', 'content': user_text},
        ],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {'name': 'reply', 'strict': True, 'schema': schema},
        },
    }
    if reasoning_effort is not None:
        body['reasoning_effort'] = reasoning_effort
    return {
        'custom_id': custom_id,
        'method': 'POST',
        'url': CHAT_ENDPOINT,
        'body': body,
    }


def _line_bytes(request):
    return len(json.dumps(request, ensure_ascii=False).encode('utf-8')) + 1


def split_into_files(requests, out_dir, max_bytes=MAX_BYTES_PER_FILE,
                     max_lines=MAX_LINES_PER_FILE, prefix='batch'):
    """Режет поток запросов на файлы JSONL под лимиты Batch API.

    `requests` — итератор словарей от `build_request`. Каждый ОДИНОЧНЫЙ
    запрос обязан помещаться в файл целиком (запрос длиннее лимита — это
    сигнал остановиться и разобраться, а не тихо превысить потолок).

    Возвращает манифест: список словарей `{path, custom_ids, line_count,
    byte_count}`, по одному на файл, в порядке записи.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    index = 1
    fh = None
    custom_ids = []
    byte_count = 0
    line_count = 0
    path = None

    def _close():
        if fh is not None:
            fh.close()
            manifest.append({
                'path': str(path),
                'custom_ids': list(custom_ids),
                'line_count': line_count,
                'byte_count': byte_count,
            })

    for request in requests:
        size = _line_bytes(request)
        if size > max_bytes:
            raise ValueError(
                'Один запрос (custom_id=%r) весит %d байт — больше '
                'лимита файла %d байт. Разбирайтесь с запросом, а не с '
                'резкой.' % (request.get('custom_id'), size, max_bytes))

        needs_new_file = (
            fh is None
            or line_count >= max_lines
            or byte_count + size > max_bytes
        )
        if needs_new_file:
            _close()
            path = out_dir / ('%s_%04d.jsonl' % (prefix, index))
            index += 1
            # newline='' — без этого Windows молча превращает каждый '\n' в
            # '\r\n', и подсчитанные байты (_line_bytes) расходятся с тем,
            # что реально легло на диск.
            fh = open(path, 'w', encoding='utf-8', newline='')
            custom_ids = []
            byte_count = 0
            line_count = 0

        fh.write(json.dumps(request, ensure_ascii=False) + '\n')
        custom_ids.append(request['custom_id'])
        byte_count += size
        line_count += 1

    _close()
    return manifest


def save_manifest(manifest, path):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


def load_manifest(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


# ⚠️ КАЛИБРОВКА РЕАЛЬНЫМ ЗАМЕРОМ (Б4, 31.08.2026), НЕ ДОГАДКА. Крошечный
# файл (1 строка) стал виден Batch API мгновенно. Файл замера Б4 (100
# строк, 7,3 МБ) — только с ТРЕТЬЕЙ попытки, спустя ~10 минут после
# загрузки; первые две (сразу и через ~4 минуты) упали с той же ошибкой
# `Cannot find file …`. Задержка явно растёт с размером файла — почему
# именно так, неизвестно (не описано в документации). Боевые файлы будут
# до 180 МБ (см. докстринг модуля) — во сколько раз дольше ждать там,
# ЭТИМ ЗАМЕРОМ НЕ ПРОВЕРЕНО. Экспоненциальный бэкофф с большим общим
# бюджетом — подстраховка, а не гарантия; для файла на 180 МБ, возможно,
# и её будет мало, и это надо будет проверить отдельно перед боевым
# прогоном, а не полагаться на цифры ниже.
FILE_PROPAGATION_RETRIES = 8
FILE_PROPAGATION_WAIT_SECONDS = 15  # начальная пауза, дальше ×2 на попытку


def submit_pending(client, manifest, manifest_path, endpoint=ENDPOINT):
    """Отправляет файлы манифеста, у которых ещё нет `batch_id`.

    `endpoint` — какой Batch API дёргать (`ENDPOINT` или `CHAT_ENDPOINT`,
    Фаза 3, 2026-09-01): манифест строится под ОДИН эндпойнт целиком, файл
    из `build_chat_request` с эндпойнтом Responses API не отправить.

    ⚠️ ВОЗОБНОВЛЕНИЕ С МЕСТА ОБРЫВА. Манифест сохраняется на диск СРАЗУ
    после каждой успешной отправки — прервали процесс на файле 3 из 5,
    перезапустили: файлы 1–2 не отправляются повторно, потому что у их
    записей уже есть `batch_id`.

    ⚠️ ГОНКА ЗАГРУЗКИ ФАЙЛА — ПОДТВЕРЖДЕНО РЕАЛЬНЫМ ВЫЗОВОМ (замер Б4,
    31.08.2026). `client.files.create(purpose='batch')` возвращает файл со
    статусом `processed` СРАЗУ, но сервис Batch API видит его не мгновенно:
    первая попытка `client.batches.create()` сразу после загрузки упала с
    `invalid_request` / `Cannot find file …, or organization … does not
    have access to it`, хотя `client.files.retrieve()` тем же секундами
    позже уже показывал файл нормально. Ни одного запроса при этом не
    ушло и не оплачено (`request_counts` и `usage` батча — нули), поэтому
    ретрай с паузой безопасен по деньгам. Раньше это место было НЕ
    проверено реальным вызовом (см. докстринг модуля) — теперь проверено.
    """
    for entry in manifest:
        if entry.get('batch_id'):
            continue
        with open(entry['path'], 'rb') as fh:
            uploaded = client.files.create(file=fh, purpose='batch')

        batch = None
        last_error = None
        for attempt in range(FILE_PROPAGATION_RETRIES):
            if attempt:
                time.sleep(FILE_PROPAGATION_WAIT_SECONDS * (2 ** (attempt - 1)))
            try:
                batch = client.batches.create(
                    input_file_id=uploaded.id,
                    endpoint=endpoint,
                    completion_window=COMPLETION_WINDOW,
                )
                break
            except Exception as error:  # см. докстринг — гонка, не ошибка данных
                last_error = error
        if batch is None:
            raise last_error

        entry['input_file_id'] = uploaded.id
        entry['batch_id'] = batch.id
        entry['status'] = batch.status
        save_manifest(manifest, manifest_path)
    return manifest


def refresh_statuses(client, manifest, manifest_path):
    """Опрашивает статус каждого отправленного батча и обновляет манифест."""
    changed = False
    for entry in manifest:
        batch_id = entry.get('batch_id')
        if not batch_id:
            continue
        batch = client.batches.retrieve(batch_id)
        if entry.get('status') != batch.status:
            changed = True
        entry['status'] = batch.status
        entry['output_file_id'] = getattr(batch, 'output_file_id', None)
        entry['error_file_id'] = getattr(batch, 'error_file_id', None)
    if changed:
        save_manifest(manifest, manifest_path)
    return manifest


def all_terminal(manifest):
    return all(entry.get('status') in TERMINAL_STATUSES for entry in manifest)


def download_results(client, manifest, out_dir):
    """Скачивает `output_file_id` (и `error_file_id`, если есть) каждого
    завершённого батча. Уже скачанные файлы (есть в манифесте) не качает
    повторно — тоже часть возобновления с места обрыва.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for entry in manifest:
        if entry.get('status') != 'completed':
            continue
        if entry.get('result_path'):
            downloaded.append(entry['result_path'])
            continue
        output_file_id = entry.get('output_file_id')
        if not output_file_id:
            continue
        content = client.files.content(output_file_id)
        result_path = out_dir / (Path(entry['path']).stem + '.result.jsonl')
        with open(result_path, 'wb') as fh:
            fh.write(content.read() if hasattr(content, 'read')
                     else content.content)
        entry['result_path'] = str(result_path)
        downloaded.append(str(result_path))
    return downloaded


def parse_results(path):
    """Разбирает один скачанный JSONL-файл результатов Batch API.

    ⚠️ ЧАСТИЧНЫЕ ОТКАЗЫ — ПО СТРОКАМ, А НЕ ПО ФАЙЛУ ЦЕЛИКОМ. Один плохой
    JSON или отказ модели по конкретной задаче не должен уронить разбор
    остальных 12 000 строк файла.

    Возвращает словарь `custom_id -> {'data': dict|None, 'error': str|None}`.
    """
    results = {}
    with open(path, encoding='utf-8') as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                row = json.loads(raw_line)
            except ValueError as error:
                results['_parse_error_line_%d' % line_number] = {
                    'data': None, 'error': 'Строка не JSON: %s' % error}
                continue

            custom_id = row.get('custom_id') or '_line_%d' % line_number
            error = row.get('error')
            if error:
                results[custom_id] = {'data': None, 'error': str(error)}
                continue

            response = row.get('response') or {}
            status_code = response.get('status_code')
            body = response.get('body') or {}
            if status_code and status_code != 200:
                results[custom_id] = {
                    'data': None,
                    'error': 'HTTP %s: %s' % (status_code, body),
                }
                continue

            text = _output_text_from_batch_body(body)
            try:
                data = json.loads(text) if text else None
            except ValueError:
                results[custom_id] = {
                    'data': None, 'error': 'Ответ модели — не JSON'}
                continue
            results[custom_id] = {'data': data, 'error': None}
    return results


def usage_from_responses_body(body):
    """Счётчики токенов из тела строки результата `/v1/responses` (Фаза 3,
    2026-09-01) — `cached_tokens` сидит ВНУТРИ `input_tokens`, как и в
    синхронном `OpenAIProvider._reply_from`."""
    usage = body.get('usage') or {}
    details = usage.get('input_tokens_details') or {}
    return {
        'input_tokens': usage.get('input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'cached_tokens': details.get('cached_tokens', 0),
    }


def usage_from_chat_body(body):
    """То же самое для `/v1/chat/completions` — другие имена полей
    (`prompt_tokens`/`completion_tokens`/`prompt_tokens_details`)."""
    usage = body.get('usage') or {}
    details = usage.get('prompt_tokens_details') or {}
    return {
        'input_tokens': usage.get('prompt_tokens', 0),
        'output_tokens': usage.get('completion_tokens', 0),
        'cached_tokens': details.get('cached_tokens', 0),
    }


def parse_results_usage(path, usage_fn):
    """`custom_id -> usage` (см. `usage_from_responses_body`/
    `usage_from_chat_body`) для успешных строк файла результатов Batch API.
    Отдельно от `parse_results` — не меняет форму существующего разбора.
    """
    usage_by_id = {}
    with open(path, encoding='utf-8') as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                row = json.loads(raw_line)
            except ValueError:
                continue
            custom_id = row.get('custom_id')
            if not custom_id or row.get('error'):
                continue
            response = row.get('response') or {}
            body = response.get('body') or {}
            usage_by_id[custom_id] = usage_fn(body)
    return usage_by_id


def _output_text_from_batch_body(body):
    """Текст ответа Responses API внутри тела строки Batch-результата."""
    text = body.get('output_text')
    if text:
        return text
    parts = []
    for item in body.get('output') or []:
        for block in item.get('content') or []:
            piece = block.get('text')
            if piece:
                parts.append(piece)
    return ''.join(parts)
