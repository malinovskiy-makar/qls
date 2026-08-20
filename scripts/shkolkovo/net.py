# -*- coding: utf-8 -*-
"""
Общий ограничитель темпа для класса запросов «static»
(/api/latex-service/... — используется в fetch_tex.py и fetch_images.py).

Один httpx.AsyncClient на весь прогон (keep-alive, пул соединений).

Два независимых механизма:
  RateLimiter   — токен-бакет, жёсткий потолок запросов/с (не поднимать выше 10).
  AdaptiveGate  — сколько запросов одновременно в полёте; растёт на +2 после
                  500 успешных подряд без единого отказа темпа, при первом же
                  намёке на отказ темпа (429/503/502/таймаут) режется пополам
                  (не ниже 2) и на 10 секунд полностью останавливается приём
                  новых запросов.

Повторы: 5с, 15с, 45с, 120с. После четвёртой неудачи — вызывающий код решает
(обычно failed.json). 404 НЕ повторяется — это отсутствующий файл, а не отказ.
"""
import asyncio
import time

import httpx

from common import USER_AGENT

RETRY_DELAYS = [5, 15, 45, 120]
RATE_INCIDENT_STATUSES = (429, 503, 502)


class RateLimiter:
    """Токен-бакет: не больше `rate` запросов в секунду, без фиксированных пауз."""

    def __init__(self, rate: float):
        self.rate = rate
        self.tokens = rate
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.updated
                self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)

    def set_rate(self, rate: float):
        self.rate = rate


class AdaptiveGate:
    """Сколько запросов одновременно в полёте; умеет расти и резаться на лету."""

    def __init__(self, start: int, max_n: int, min_n: int = 2):
        self.limit = start
        self.max_n = max_n
        self.min_n = min_n
        self.active = 0
        self.paused_until = 0.0
        self.cond = asyncio.Condition()
        self.grow_count = 0
        self.cut_count = 0
        self.max_limit_reached = start

    async def acquire(self):
        async with self.cond:
            while True:
                now = time.monotonic()
                if now < self.paused_until:
                    try:
                        await asyncio.wait_for(self.cond.wait(), timeout=max(0.05, self.paused_until - now))
                    except (asyncio.TimeoutError, TimeoutError):
                        pass
                    continue
                if self.active >= self.limit:
                    await self.cond.wait()
                    continue
                self.active += 1
                return

    async def release(self):
        async with self.cond:
            self.active -= 1
            self.cond.notify_all()

    async def grow(self, by=2, log=print):
        async with self.cond:
            new_limit = min(self.max_n, self.limit + by)
            if new_limit != self.limit:
                self.limit = new_limit
                self.grow_count += 1
                self.max_limit_reached = max(self.max_limit_reached, self.limit)
                log(f"    [темп] разгон: одновременных = {self.limit}")
                self.cond.notify_all()

    def stats(self):
        return {
            "final_limit": self.limit, "max_limit_reached": self.max_limit_reached,
            "grow_count": self.grow_count, "cut_count": self.cut_count,
        }

    async def cut_and_pause(self, pause_s=10, log=print):
        async with self.cond:
            new_limit = max(self.min_n, self.limit // 2)
            log(f"    [темп] отказ темпа: одновременных {self.limit} -> {new_limit}, пауза {pause_s} с")
            self.limit = new_limit
            self.cut_count += 1
            self.paused_until = time.monotonic() + pause_s
            self.cond.notify_all()


class Stats:
    def __init__(self, ramp_after: int, progress_every: int = 500):
        self.total = 0
        self.ok = 0
        self.failed_permanent = 0
        self.not_found = 0
        self.rate_incidents = 0
        self.consecutive_ok = 0
        self.ramp_after = ramp_after
        self.progress_every = progress_every
        self.last_progress_at = 0
        self.start_time = time.monotonic()
        self.lock = asyncio.Lock()

    async def record_ok(self, gate, log=print):
        async with self.lock:
            self.total += 1
            self.ok += 1
            self.consecutive_ok += 1
            do_grow = self.consecutive_ok >= self.ramp_after
            if do_grow:
                self.consecutive_ok = 0
        if do_grow:
            await gate.grow(2, log=log)
        await self._maybe_progress(log)

    async def record_not_found(self, log=print):
        async with self.lock:
            self.total += 1
            self.not_found += 1
        await self._maybe_progress(log)

    async def record_rate_incident(self, gate, log=print):
        async with self.lock:
            self.total += 1
            self.rate_incidents += 1
            self.consecutive_ok = 0
        await gate.cut_and_pause(10, log=log)

    async def record_permanent_failure(self, log=print):
        async with self.lock:
            self.total += 1
            self.failed_permanent += 1
        await self._maybe_progress(log)

    async def _maybe_progress(self, log):
        async with self.lock:
            if self.total - self.last_progress_at < self.progress_every:
                return
            self.last_progress_at = self.total
            elapsed = time.monotonic() - self.start_time
            rps = self.total / elapsed if elapsed > 0 else 0.0
        log(
            f"  [прогресс] {self.total} запросов, {rps:.1f} зап/с, "
            f"ok={self.ok}, 404={self.not_found}, отказов темпа={self.rate_incidents}, "
            f"окончательных неудач={self.failed_permanent}"
        )

    def summary(self):
        elapsed = time.monotonic() - self.start_time
        rps = self.total / elapsed if elapsed > 0 else 0.0
        return {
            "total": self.total, "ok": self.ok, "not_found": self.not_found,
            "rate_incidents": self.rate_incidents, "failed_permanent": self.failed_permanent,
            "elapsed_s": elapsed, "avg_rps": rps,
        }


def make_client() -> httpx.AsyncClient:
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=20)
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        timeout=httpx.Timeout(20.0),
        limits=limits,
    )


class PermanentFailure(Exception):
    """Все повторы исчерпаны (НЕ 404 — тот обрабатывается отдельно вызывающим кодом)."""


async def fetch_static(client, gate: AdaptiveGate, limiter: RateLimiter, stats: Stats, url: str, log=print):
    """
    Возвращает httpx.Response при успехе (200) или при 404 (вызывающий код сам решает,
    считать ли 404 нормальным исходом). Бросает PermanentFailure после исчерпания повторов
    на 429/503/502/таймаут/обрыв соединения.
    """
    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)

        await limiter.acquire()
        await gate.acquire()
        try:
            resp = await client.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            await gate.release()
            last_exc = e
            await stats.record_rate_incident(gate, log=log)
            continue
        await gate.release()

        if resp.status_code == 404:
            await stats.record_not_found(log=log)
            return resp

        if resp.status_code in RATE_INCIDENT_STATUSES:
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
            await stats.record_rate_incident(gate, log=log)
            continue

        if resp.status_code != 200:
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
            await stats.record_rate_incident(gate, log=log)
            continue

        await stats.record_ok(gate, log=log)
        return resp

    await stats.record_permanent_failure(log=log)
    raise PermanentFailure(f"{url}: все повторы исчерпаны ({last_exc})")
