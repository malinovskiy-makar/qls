# -*- coding: utf-8 -*-
"""ВсОШ: манифест скачанного — строка на файл, архивы раскрыты, дубли сведены.

Вход — `work\\jobs_*.jsonl` (что хотели скачать, с метаданными источника)
и `work\\results_*.jsonl` (что вышло). Выход — `manifest.jsonl`:
`source, url, sha256, size, stage, season, grades, region_code,
region_name, kind, tour, variant, format, text_layer, pages, dup_of` +
`status` (ok | not_downloaded | not_a_file | archive) и `reason`.

Инвариант: строк манифеста по ссылкам = скачано + не скачалось (с
причиной). Файлы из архивов — отдельные строки с `from_archive`.

Архив раскрывается в СВОЮ папку `_unpacked\\<sha16>\\`; ничего из
скачанного не запускается. Имена в zip без флага UTF-8 — cp866 (edsoo,
kimc). Дубли — по sha256; главная копия — по старшинству источника
(`SOURCE_RANK`), у остальных `dup_of` = url главной копии.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import zipfile
from collections import Counter, defaultdict

from problems.olympiad_audit import vsosh_sources as S

#: Старшинство при дублях: у ЦПМ точнее классы и туры (поля API), ILE —
#: архив ЦПМК (решение 14.10), дальше агрегатор olimpiada.ru и прочие.
SOURCE_RANK = ('cpm', 'ile', 'olimpiada', 'edsoo', 'region', 'rosolymp')

TAR = r'C:\Windows\System32\tar.exe'

_SIGNATURES = (
    (b'%PDF', 'pdf'),
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'doc'),
    (b'Rar!\x1a\x07', 'rar'),
    (b"7z\xbc\xaf\x27\x1c", '7z'),
    (b'\xff\xd8\xff', 'jpg'),
    (b'\x89PNG', 'png'),
    (b'{\\rtf', 'rtf'),
)

ARCHIVES = ('zip', 'rar', '7z')
DOCS = ('pdf', 'doc', 'docx', 'rtf', 'odt', 'jpg', 'png')


def detect_format(path):
    """Формат по сигнатуре, а не по расширению (у edsoo расширения нет)."""
    with open(path, 'rb') as fh:
        head = fh.read(4096)
    for sig, fmt in _SIGNATURES:
        if head.startswith(sig):
            return fmt
    if head.startswith(b'PK'):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return 'zip'
        if 'word/document.xml' in names:
            return 'docx'
        if 'xl/workbook.xml' in names:
            return 'xlsx'
        if 'ppt/presentation.xml' in names:
            return 'pptx'
        if 'content.xml' in names and 'mimetype' in names:
            return 'odt'
        return 'zip'
    low = head[:500].lstrip().lower()
    if low.startswith(b'<!doctype html') or low.startswith(b'<html'):
        return 'html'
    return 'bin'


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def zip_member_name(info):
    """Имя члена zip: без флага UTF-8 (бит 11) zipfile читает cp437 —
    переводим обратно в байты и читаем как cp866 (так пишет русский Windows)."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode('cp437').decode('cp866')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


_JUNK = re.compile(r'(^|/)(__MACOSX|\.DS_Store|Thumbs\.db|desktop\.ini)(/|$)|(^|/)\._', re.I)


def _safe_rel(name):
    parts = [p for p in re.split(r'[\\/]+', name) if p not in ('', '.', '..')]
    return '/'.join(re.sub(r'[<>:"|?*\x00-\x1f]', '_', p) for p in parts)


def extract_archive(path, out_dir, fmt=None):
    """Раскрыть архив в `out_dir` (только запись файлов, без запуска).

    Возвращает список (rel_path_в_архиве, abs_path). Мусор macOS — мимо."""
    fmt = fmt or detect_format(path)
    os.makedirs(out_dir, exist_ok=True)
    out = []
    if fmt == 'zip':
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = zip_member_name(info)
                if _JUNK.search(name):
                    continue
                rel = _safe_rel(name)
                if not rel:
                    continue
                dest = os.path.join(out_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(info) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
                out.append((rel, dest))
        return out
    if fmt == '7z':
        import py7zr
        with py7zr.SevenZipFile(path) as z:
            z.extractall(out_dir)
    elif fmt == 'rar':
        subprocess.run([TAR, '-xf', path, '-C', out_dir], check=False,
                       capture_output=True, timeout=600)
    for root, _dirs, files in os.walk(out_dir):
        for f in files:
            dest = os.path.join(root, f)
            rel = os.path.relpath(dest, out_dir).replace('\\', '/')
            if _JUNK.search(rel):
                continue
            out.append((rel, dest))
    return out


_NAME_GRADE = re.compile(
    r'(?<![\d])(\d{1,2})(?:\s*[-_–]\s*(\d{1,2}))?\s*[-_ ]?(?:класс|кл|klass|kl|cl|class)', re.I)
_NAME_GRADE2 = re.compile(r'(?:^|[-_ ])(?:econ|ekon|эконом\w*)[-_ ](\d{1,2})(?:[-_](\d{1,2}))?(?=[-_ .])', re.I)


def grades_from_name(name):
    """Класс из имени файла (запасной путь — для членов архивов без подписи)."""
    base = os.path.basename(name)
    for rx in (_NAME_GRADE, _NAME_GRADE2):
        m = rx.search(base)
        if m:
            a, b = int(m.group(1)), m.group(2)
            if 5 <= a <= 11:
                if b and 5 <= int(b) <= 11 and int(b) != a:
                    lo, hi = sorted((a, int(b)))
                    return f'{lo}-{hi}'
                return str(a)
    return ''


_NAME_KIND = (
    (re.compile(r'критер|krit|criter', re.I), 'criteria'),
    (re.compile(r'(^|[-_ ])(ans|otv|ответ|answers?|key|ключ)', re.I), 'answers'),
    (re.compile(r'решени|reshen|solut|resh', re.I), 'solutions'),
    (re.compile(r'метод|требован|mr_|рекоменд|бланк|blank|протокол|рейтинг|presentation|презент', re.I), 'methodical'),
    (re.compile(r'задан|задач|zadan|zadach|tasks?|тест|test|эссе|essay', re.I), 'tasks'),
)


_SOL_AND_CRIT = re.compile(r'решени\w*\s+и\s+критер|resh\w*_i_krit', re.I)


def kind_from_name(name):
    """Тип по имени члена архива: сначала имя файла, затем папки снизу вверх
    («критерии РЭ …/Решения 9 класс.pdf» → solutions; «задания …/10 класс
    2 тур.pdf» → tasks). «Решения и критерии» — solutions (решение с
    критериями ложится к своей задаче так же)."""
    parts = [p for p in re.split(r'[\\/]+', str(name)) if p]
    for part in reversed(parts):
        if _SOL_AND_CRIT.search(part):
            return 'solutions'
        for rx, kind in _NAME_KIND:
            if rx.search(part):
                return kind
    return ''


_NAME_TOUR = re.compile(r'(?<!\d)([12])[\s_-]*тур|тур[\s_-]*([12])(?!\d)|tur[\s_-]*([12])|([12])[\s_-]*tur', re.I)


def tour_from_name(name):
    """«10 класс 2 тур.pdf», «zadaniya_10_klass_1_tur» → «2», «1»; «1_i_2_tur» → ''."""
    base = os.path.basename(str(name))
    if re.search(r'1[\s_]*(?:и|i|,)[\s_]*2[\s_]*(?:тур|tur)', base, re.I):
        return ''
    m = _NAME_TOUR.search(base)
    return next((g for g in m.groups() if g), '') if m else ''


def pdf_info(path):
    """(страниц, есть ли текстовый слой) — слой: ≥200 символов на файл."""
    import fitz
    try:
        with fitz.open(path) as doc:
            chars = sum(len(p.get_text().strip()) for p in doc)
            return doc.page_count, chars >= 200
    except Exception:
        return 0, False


def _source_group(source):
    return 'region' if source.startswith('region') else source


def load_runs(work_dir, names):
    """jobs_<name>.jsonl + results_<name>.jsonl → строки (последний результат по url)."""
    rows = []
    for name in names:
        jobs_path = os.path.join(work_dir, f'jobs_{name}.jsonl')
        res_path = os.path.join(work_dir, f'results_{name}.jsonl')
        if not os.path.isfile(jobs_path):
            continue
        results = {}
        if os.path.isfile(res_path):
            for line in open(res_path, encoding='utf-8'):
                if line.strip():
                    rec = json.loads(line)
                    prev = results.get(rec['url'])
                    if prev is None or prev.get('status') != 'ok':
                        results[rec['url']] = rec
        seen = set()
        for line in open(jobs_path, encoding='utf-8'):
            if not line.strip():
                continue
            job = json.loads(line)
            if job['url'] in seen:
                continue
            seen.add(job['url'])
            res = results.get(job['url'])
            row = dict(job)
            row['run'] = name
            if res is None:
                row['status'], row['reason'] = 'not_downloaded', 'не запускалось / прервано'
            elif res.get('status') == 'ok':
                row.update(status='ok', sha256=res['sha256'], size=res['size'])
            else:
                row['status'] = 'not_downloaded'
                row['reason'] = res.get('status', '') + (' ' + res.get('error', '') if res.get('error') else '')
            rows.append(row)
    return rows


_VIDEO_HOSTS = ('rutube.ru', 'youtube', 'youtu.be', 'mts-link', 'vk.com/video', 'vkvideo')


def is_video_link(url):
    return any(h in url for h in _VIDEO_HOSTS)


def not_a_file_reason(row):
    """Ссылка, которая не файл заданий: видео, «Источник <сайт>» у ЦПМ."""
    url = row['url']
    if is_video_link(url):
        return 'видеоразбор (ссылка на видео, не файл)'
    if row.get('source') == 'cpm' and '/upload/' not in url:
        return 'ссылка на внешний сайт («Источник …»), не файл'
    return ''


#: Чужой предмет внутри «экономического» архива (edsoo «ЗЭ 2021/22» — экология).
_OTHER_SUBJECT = re.compile(r'эколог|ekolog|ecolog', re.I)


def build(data_root, work_dir, run_names, unpack=True, log=print):
    """Собрать манифест. Возвращает список строк (файлы + члены архивов)."""
    rows = load_runs(work_dir, run_names)
    out = []
    for row in rows:
        reason = not_a_file_reason(row)
        if reason:
            row['status'], row['reason'] = 'not_a_file', reason
            row['kind'] = 'video' if 'видео' in reason else 'link'
        if row['status'] != 'ok':
            out.append(row)
            continue
        path = os.path.join(data_root, row['dest'])
        fmt = detect_format(path)
        row['format'] = fmt
        row['path'] = row['dest']
        if fmt in ARCHIVES:
            row['status'] = 'archive'
            out.append(row)
            if not unpack:
                continue
            udir = os.path.join(os.path.dirname(path), '_unpacked', row['sha256'][:16])
            try:
                members = extract_archive(path, udir, fmt)
            except Exception as exc:  # битый архив — строка с причиной
                row['reason'] = f'не раскрылся: {type(exc).__name__}: {exc}'[:200]
                continue
            row['members'] = len(members)
            for rel, abs_path in members:
                m = {k: v for k, v in row.items() if k not in ('members', 'reason', 'dest', 'path')}
                m.update(from_archive=row['url'], member=rel, url=row['url'] + '#' + rel,
                         path=os.path.relpath(abs_path, data_root).replace('\\', '/'),
                         status='ok', size=os.path.getsize(abs_path), sha256=sha256_file(abs_path),
                         label=(row.get('label') or '') + ' / ' + rel)
                mfmt = detect_format(abs_path)
                m['format'] = mfmt
                g = grades_from_name(rel)
                k = kind_from_name(rel)
                notes = list(row.get('notes') or [])
                if g:
                    m['grades'] = g
                if k:
                    m['kind'] = k
                    if row.get('kind') == 'methodical' and k == 'tasks':
                        m['kind'] = 'methodical'
                t = tour_from_name(rel)
                if t:
                    m['tour'] = t
                if g or k:
                    notes.append('класс_и_тип_из_имени_в_архиве')
                m['notes'] = notes
                if _OTHER_SUBJECT.search(rel):
                    m['status'], m['reason'] = 'excluded', 'другой предмет (экология) в архиве edsoo'
                if mfmt in ARCHIVES and m['status'] == 'ok':   # вложенный — один уровень
                    m['status'] = 'archive'
                    out.append(m)
                    sub = os.path.join(udir, '_nested', m['sha256'][:16])
                    try:
                        for rel2, abs2 in extract_archive(abs_path, sub, mfmt):
                            n = dict(m, member=rel + '/' + rel2, url=m['url'] + '/' + rel2,
                                     path=os.path.relpath(abs2, data_root).replace('\\', '/'),
                                     status='ok', size=os.path.getsize(abs2), sha256=sha256_file(abs2),
                                     format=detect_format(abs2))
                            n['grades'] = grades_from_name(rel2) or m.get('grades', '')
                            n['kind'] = kind_from_name(rel2) or m.get('kind', '')
                            out.append(n)
                    except Exception as exc:
                        m['reason'] = f'вложенный не раскрылся: {exc}'[:200]
                    continue
                out.append(m)
            continue
        out.append(row)
    mark_duplicates(out)
    for r in out:
        if r.get('status') == 'ok' and r.get('format') == 'pdf' and not r.get('dup_of'):
            r['pages'], r['text_layer'] = pdf_info(os.path.join(data_root, r['path']))
    return out


def mark_duplicates(rows):
    """`dup_of` = url главной копии с тем же sha256 (старшинство источника,
    затем файл вне архива старше члена архива, затем порядок)."""
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        if r.get('status') in ('ok', 'archive') and r.get('sha256'):
            groups[r['sha256']].append(i)
    for idxs in groups.values():
        def rank(i):
            r = rows[i]
            g = _source_group(r.get('source', ''))
            return (SOURCE_RANK.index(g) if g in SOURCE_RANK else 99,
                    1 if r.get('from_archive') else 0, i)
        idxs.sort(key=rank)
        head = rows[idxs[0]]
        head['dup_of'] = ''
        head['copies'] = [rows[i]['source'] for i in idxs[1:]]
        for i in idxs[1:]:
            rows[i]['dup_of'] = head['url']
    return rows


def invariants(rows):
    """Числа для отчёта: ссылки = скачано + не скачалось; уникальных sha."""
    links = [r for r in rows if not r.get('from_archive')]
    ok = sum(1 for r in links if r['status'] in ('ok', 'archive'))
    bad = sum(1 for r in links if r['status'] in ('not_downloaded', 'not_a_file'))
    unique = len({r['sha256'] for r in rows if r.get('sha256') and r['status'] == 'ok'})
    return {'links': len(links), 'downloaded': ok, 'not_downloaded': bad,
            'balanced': len(links) == ok + bad,
            'archive_members': sum(1 for r in rows if r.get('from_archive')),
            'unique_sha256_files': unique,
            'by_status': dict(Counter(r['status'] for r in rows))}
