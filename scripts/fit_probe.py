# -*- coding: utf-8 -*-
"""Влезает ли страница в окно без прокрутки — замер, а не глазомер.

Зачем. «Помещается» — это не про высоту всей страницы, а про то, больше ли
содержимое видимой области. Меряем ровно это: scrollHeight против
clientHeight, плюс горизонтальную прокрутку, плюс высоту каждого крупного
блока — чтобы было видно, на чём именно экономить.

Запуск (сервер поднят):
    python scripts/fit_probe.py
    python scripts/fit_probe.py --url / --sizes 1440x780,1366x620
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

# Консоль Windows по умолчанию cp1251 и падает на «×». Отчёт с числами
# важнее, чем кодировка терминала, поэтому переключаем вывод явно.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # старый Python или необычный поток — не беда
    pass

BASE = "http://127.0.0.1:8002"
USER, PASSWORD = "shot_bot", "shotbot-local-2026"

# ⚠️ ВЫСОТА — ВИДИМАЯ ОБЛАСТЬ, А НЕ ОКНО. У браузера сверху свои панели:
#    на ноутбуке 1440×900 странице достаётся около 780, на 1366×768 — 620.
DEFAULT_SIZES = "1440x780,1366x620"

JS = r"""
() => {
  const de = document.documentElement;
  const rows = [];
  const add = (name, sel) => {
    const el = document.querySelector(sel);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    rows.push({name, h: Math.round(r.height),
               mt: Math.round(parseFloat(cs.marginTop) || 0),
               pt: Math.round(parseFloat(cs.paddingTop) || 0),
               pb: Math.round(parseFloat(cs.paddingBottom) || 0),
               w: Math.round(r.width)});
  };
  ['nav', '.page-wrap', '.home-wrap', '.home-logo', '.home-slogan',
   '.home-search', '.home-stats', '.home-cards', '.home-card',
   '.card-title', '.card-desc'].forEach(s => add(s, s));
  const last = document.querySelector('.home-cards') ||
               document.querySelector('.page-wrap');
  return {
    scrollH: de.scrollHeight, clientH: de.clientHeight,
    scrollW: de.scrollWidth, clientW: de.clientWidth,
    bottom: last ? Math.round(last.getBoundingClientRect().bottom) : null,
    rows,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="/")
    ap.add_argument("--sizes", default=DEFAULT_SIZES)
    ap.add_argument("--themes", default="light")
    ap.add_argument("--anon", action="store_true", help="без входа")
    args = ap.parse_args()

    sizes = []
    for chunk in args.sizes.split(","):
        w, h = chunk.strip().lower().split("x")
        sizes.append((int(w), int(h)))

    bad = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h in sizes:
            ctx = browser.new_context(viewport={"width": w, "height": h},
                                      locale="ru-RU")
            page = ctx.new_page()
            if not args.anon:
                page.goto(f"{BASE}/login/", wait_until="networkidle")
                page.fill("input[name=username]", USER)
                page.fill("input[name=password]", PASSWORD)
                page.click("button[type=submit], input[type=submit]")
                page.wait_for_load_state("networkidle")
            for theme in args.themes.split(","):
                page.add_init_script(
                    "() => document.documentElement.setAttribute("
                    f"'data-theme', '{theme.strip()}')")
                page.goto(BASE + args.url, wait_until="networkidle")
                page.evaluate("t => document.documentElement.setAttribute("
                              "'data-theme', t)", theme.strip())
                page.evaluate("() => document.fonts.ready")
                page.wait_for_timeout(350)
                d = page.evaluate(JS)
                over_v = d["scrollH"] - d["clientH"]
                over_h = d["scrollW"] - d["clientW"]
                mark = "ВЛЕЗАЕТ" if over_v <= 0 else f"НЕ ВЛЕЗАЕТ (+{over_v})"
                hmark = "нет" if over_h <= 0 else f"ЕСТЬ (+{over_h})"
                print(f"\n=== {w}×{h}, тема {theme.strip()} — {mark}; "
                      f"горизонтальная прокрутка: {hmark}")
                print(f"    содержимое {d['scrollH']} px, видимая область "
                      f"{d['clientH']} px, низ карточек на {d['bottom']}")
                for r in d["rows"]:
                    print(f"      {r['name']:<14} высота {r['h']:>4}  "
                          f"сверху отступ {r['mt']:>3}/{r['pt']:>3}  "
                          f"ширина {r['w']:>4}")
                if over_v > 0 or over_h > 0:
                    bad += 1
            ctx.close()
        browser.close()
    print(f"\nразмеров с прокруткой: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
