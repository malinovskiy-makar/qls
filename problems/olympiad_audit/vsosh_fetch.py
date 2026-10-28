# -*- coding: utf-8 -*-
"""ВсОШ: вежливое скачивание по списку заданий (jobs.jsonl → results.jsonl).

Строка задания: `{"url", "dest", ...метаданные}`; `dest` — путь
относительно корня данных. Результат дописывается строкой СРАЗУ после
каждого файла (`status`: ok | http_<код> | error | html_instead_of_file),
поэтому прерванный прогон продолжается с места: уже `ok` пропускаются.

Пауза — на ХОСТ (ILE: `Crawl-delay: 10`), потоков — несколько на разные
хосты. Повторы на сброс соединения и 5xx — с растущей паузой. Скачанное —
только данные: ничего не распаковывается и не запускается.

Запуск: `python -m problems.olympiad_audit.vsosh_fetch JOBS RESULTS ROOT
[--delay host=sec ...] [--threads N]`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0 Safari/537.36')
RETRY_PAUSES = (3, 10, 30, 60)


def looks_like_html(head: bytes) -> bool:
    h = head[:600].lstrip().lower()
    return h.startswith(b'<!doctype html') or h.startswith(b'<html') or b'<head' in h[:300]


def is_page_url(url):
    """Адрес страницы (не файла): HTML ожидаем, проверка «HTML вместо файла» не нужна."""
    return any(x in url for x in ('/print-all-tasks/', '/z/', '/api/', '/olimp/'))


class HostGate:
    """Пауза между запросами к одному хосту (общая для всех потоков)."""

    def __init__(self, delays, default=0.5):
        self.delays, self.default = delays, default
        self.locks = defaultdict(threading.Lock)
        self.last = defaultdict(float)

    def wait(self, host):
        delay = self.delays.get(host, self.default)
        for key, d in self.delays.items():
            if host.endswith(key):
                delay = d
        with self.locks[host]:
            pause = self.last[host] + delay - time.time()
            if pause > 0:
                time.sleep(pause)
            self.last[host] = time.time()


def fetch_one(job, root, gate, session):
    import requests
    url = job['url']
    dest = os.path.join(root, job['dest'])
    host = urlsplit(url).hostname or ''
    out = {k: v for k, v in job.items()}
    last_err = ''
    for attempt, pause in enumerate((0,) + RETRY_PAUSES):
        if pause:
            time.sleep(pause)
        gate.wait(host)
        try:
            r = session.get(url, timeout=(20, 120), headers={'User-Agent': UA},
                            allow_redirects=True)
        except requests.RequestException as exc:
            last_err = f'{type(exc).__name__}: {str(exc)[:160]}'
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < len(RETRY_PAUSES):
            last_err = f'http_{r.status_code}'
            if r.status_code == 500 and 'vos.olimpiada.ru' in host:
                break  # у ЦПМ 500 = нет папки, повтор не поможет
            continue
        if r.status_code != 200:
            out.update(status=f'http_{r.status_code}', error='', size=len(r.content))
            return out
        body = r.content
        if not is_page_url(url) and looks_like_html(body) and not url.lower().endswith(('.htm', '.html')):
            out.update(status='html_instead_of_file', size=len(body), final_url=r.url)
            return out
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + '.part'
        with open(tmp, 'wb') as fh:
            fh.write(body)
        os.replace(tmp, dest)
        out.update(status='ok', size=len(body), sha256=hashlib.sha256(body).hexdigest(),
                   final_url=r.url, content_type=r.headers.get('Content-Type', ''),
                   fetched_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
        return out
    out.update(status='error', error=last_err)
    return out


def run(jobs_path, results_path, root, delays, threads=3, default_delay=0.5):
    import requests
    done = set()
    if os.path.exists(results_path):
        with open(results_path, encoding='utf-8') as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get('status') in ('ok', 'http_404', 'http_410', 'html_instead_of_file'):
                    done.add(rec['url'])
    with open(jobs_path, encoding='utf-8') as fh:
        jobs = [json.loads(line) for line in fh if line.strip()]
    todo, seen = [], set()
    for j in jobs:
        if j['url'] in done or j['url'] in seen:
            continue
        seen.add(j['url'])
        todo.append(j)
    print(f'заданий {len(jobs)}, уже сделано {len(done)}, к скачиванию {len(todo)}', flush=True)
    gate = HostGate(delays, default_delay)
    lock = threading.Lock()
    session = requests.Session()
    counter = {'n': 0}

    def work(job):
        rec = fetch_one(job, root, gate, session)
        with lock:
            with open(results_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
            counter['n'] += 1
            if counter['n'] % 25 == 0 or rec['status'] != 'ok':
                print(f"[{counter['n']}/{len(todo)}] {rec['status']} {job['url'][:120]}", flush=True)

    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(work, todo))
    print('готово', flush=True)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('jobs')
    p.add_argument('results')
    p.add_argument('root')
    p.add_argument('--delay', action='append', default=[], help='host=seconds')
    p.add_argument('--default-delay', type=float, default=0.5)
    p.add_argument('--threads', type=int, default=3)
    a = p.parse_args(argv)
    delays = {}
    for d in a.delay:
        host, sec = d.split('=')
        delays[host] = float(sec)
    run(a.jobs, a.results, a.root, delays, a.threads, a.default_delay)


if __name__ == '__main__':
    main()
