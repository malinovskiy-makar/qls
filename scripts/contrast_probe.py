# -*- coding: utf-8 -*-
"""Замер контраста ПО ЭКРАНУ, а не по токенам.

Зачем отдельно от `test_design_canon`. Проверки канона читают токены и
считают пары, которые в них заложены. Но на экране текст лежит не на
токене, а на том, что реально нарисовано под ним: панель может быть
бирюзовой, а подпись — унаследовать цвет от родителя, который про бирюзу
не знает. Ровно так --text2 (3,31 на бирюзе) и попадает на панель
инструмента: в токенах такой пары нет, потому что её никто не объявлял.

Скрипт обходит ЖИВОЙ DOM, для каждого видимого куска текста поднимается
вверх до первого непрозрачного фона и считает контраст с ним. Прозрачные
фоны накладываются по порядку.

Запуск (сервер поднят):
    python scripts/contrast_probe.py
    python scripts/contrast_probe.py --only catalog --min 4.5
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
USER, PASSWORD = "shot_bot", "shotbot-local-2026"

PAGES = {
    "login": "/login/",
    "home": "/",
    "styleguide": "/teacher/styleguide/",
    "catalog": "/catalog/",
    "catalog_found": "/catalog/?topic=&q=спрос",
    "problem": "/catalog/problem/63321/",
    "search": "/catalog/smart-search/",
    # ⚠️ Пустой экран поиска показывает 16 кусков текста, а найденное —
    #    больше сотни. Мерить надо ОБА: роль --surface-info живёт только
    #    в результатах, и на пустом экране её просто нет.
    "search_found": "/catalog/smart-search/?q=эластичность спроса",
    "stats": "/profile/stats/",
    "game": "/game/",
    "calendar": "/calendar/",
}

# Собственно замер живёт в браузере: только он знает, что реально
# нарисовано под элементом после каскада, наследования и прозрачностей.
JS = r"""
() => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const lin = (v) => {
    v /= 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  // фон под элементом: копим полупрозрачные слои, пока не упрёмся в плотный
  const backdrop = (el) => {
    const stack = [];
    let node = el;
    while (node) {
      const bg = parse(getComputedStyle(node).backgroundColor);
      if (bg && bg.a > 0) {
        stack.push(bg);
        if (bg.a >= 0.999) break;
      }
      node = node.parentElement;
    }
    let base = {r: 255, g: 255, b: 255, a: 1};
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return base;
  };

  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const own = [...el.childNodes]
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join(' ');
    if (!own) continue;
    const box = el.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.opacity === '0') continue;
    // скрытый слой доступности KaTeX — на экране его нет
    if (el.closest('.katex-mathml, [aria-hidden=true]')) continue;
    const fg = parse(cs.color);
    if (!fg || fg.a === 0) continue;
    const bg = backdrop(el);
    const ink = fg.a < 1 ? over(fg, bg) : fg;
    const size = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight, 10) >= 700;
    // крупный текст по WCAG: 24px, или 18.66px полужирный
    const large = size >= 24 || (bold && size >= 18.66);
    out.push({
      text: own.slice(0, 46),
      sel: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'
             ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''),
      ratio: Math.round(ratio(ink, bg) * 100) / 100,
      need: large ? 3.0 : 4.5,
      size: size,
      bg: `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`,
      fg: `rgb(${Math.round(ink.r)},${Math.round(ink.g)},${Math.round(ink.b)})`,
    });
  }
  return out;
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--show", type=int, default=8, help="сколько провалов печатать")
    args = ap.parse_args()

    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or list(PAGES)
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]

    total_fail = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  locale="ru-RU")
        page = ctx.new_page()
        page.goto(f"{BASE}/login/", wait_until="networkidle")
        page.fill("input[name=username]", USER)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("networkidle")

        for name in wanted:
            for theme in themes:
                page.add_init_script(
                    "() => document.documentElement.setAttribute("
                    f"'data-theme', '{theme}')")
                try:
                    page.goto(BASE + PAGES[name], wait_until="networkidle",
                              timeout=30000)
                except Exception as exc:
                    print(f"{name}/{theme}: не открылась — {exc}")
                    continue
                page.evaluate("t => document.documentElement.setAttribute("
                              "'data-theme', t)", theme)
                page.evaluate("() => document.fonts.ready")
                page.wait_for_timeout(250)
                rows = page.evaluate(JS)
                bad = sorted((r for r in rows if r["ratio"] < r["need"]),
                             key=lambda r: r["ratio"])
                total_fail += len(bad)
                mark = "ПРОВАЛЫ" if bad else "чисто"
                print(f"== {name}/{theme}: замерено {len(rows)}, {mark} {len(bad)}")
                for r in bad[:args.show]:
                    print(f"   {r['ratio']:5.2f} (нужно {r['need']}) "
                          f"{r['size']:.0f}px {r['fg']} на {r['bg']}"
                          f"  {r['sel']}  «{r['text']}»")
        browser.close()

    print(f"\nвсего провалов: {total_fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
