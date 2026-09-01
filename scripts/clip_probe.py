# -*- coding: utf-8 -*-
"""Обрезанный текст — по экрану, а не по счёту мест в коде.

Прошлая сессия нашла в коде 12 мест с многоточием и 82 с запретом
переноса и НЕ проверила ни одного: список мест в CSS ничего не говорит о
том, обрезано ли что-то на самом деле. `text-overflow: ellipsis` — это
СТРАХОВКА, а не дефект: пока текст помещается, она не срабатывает.

Скрипт открывает страницы и ищет то, что реально не поместилось:
  · содержимое шире коробки при `overflow: hidden` — текст физически
    обрезан или заменён многоточием;
  · строка с `white-space: nowrap`, вылезшая за границы родителя;
  · горизонтальная прокрутка документа.
Проверяет на нескольких ширинах: обрезка живёт на узких экранах.
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
    "catalog_found": "/catalog/?q=спрос",
    "problem": "/catalog/problem/63321/",
    "search_found": "/catalog/smart-search/?q=эластичность спроса",
    "stats": "/profile/stats/",
    "progress": "/student/progress/",
    "game": "/game/",
    "calendar": "/calendar/",
}

JS = r"""
() => {
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    const box = el.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) continue;
    if (!el.offsetParent && el.tagName !== 'BODY') continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden') continue;
    // скрытый слой доступности KaTeX обрезан нарочно, на экране его нет
    if (el.closest('.katex-mathml, [aria-hidden=true]')) continue;
    const text = (el.innerText || '').trim();
    if (!text) continue;

    const hiddenX = cs.overflowX === 'hidden' || cs.overflowX === 'clip';
    const clipped = hiddenX && el.scrollWidth > el.clientWidth + 1;
    // строка без переносов, вылезшая за родителя
    let spill = false;
    if (cs.whiteSpace === 'nowrap' && el.parentElement) {
      const p = el.parentElement.getBoundingClientRect();
      const pcs = getComputedStyle(el.parentElement);
      if (pcs.overflowX !== 'auto' && pcs.overflowX !== 'scroll'
          && box.right > p.right + 1) spill = true;
    }
    if (!clipped && !spill) continue;
    const key = el.tagName + '|' + el.className + '|' + text.slice(0, 30);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      kind: clipped ? 'обрезан' : 'вылез',
      sel: el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className
             ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''),
      lost: Math.round(el.scrollWidth - el.clientWidth),
      text: text.replace(/\s+/g, ' ').slice(0, 60),
    });
  }
  return {
    items: out,
    hscroll: document.documentElement.scrollWidth
             > document.documentElement.clientWidth + 1,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--widths", default="1440,1100,820")
    ap.add_argument("--themes", default="light")
    ap.add_argument("--show", type=int, default=6)
    args = ap.parse_args()

    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or list(PAGES)
    widths = [int(w) for w in args.widths.split(",")]
    themes = [t.strip() for t in args.themes.split(",")]

    total = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": widths[0], "height": 1000},
                                  locale="ru-RU")
        page = ctx.new_page()
        page.goto(f"{BASE}/login/", wait_until="networkidle")
        page.fill("input[name=username]", USER)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("networkidle")

        for name in wanted:
            for theme in themes:
                for width in widths:
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.add_init_script(
                        "() => document.documentElement.setAttribute("
                        f"'data-theme', '{theme}')")
                    try:
                        page.goto(BASE + PAGES[name], wait_until="networkidle",
                                  timeout=30000)
                    except Exception as exc:
                        print(f"{name}@{width}: не открылась — {exc}")
                        continue
                    page.evaluate("() => document.fonts.ready")
                    page.wait_for_timeout(250)
                    r = page.evaluate(JS)
                    items = r["items"]
                    total += len(items)
                    flag = " + ГОРИЗОНТАЛЬНАЯ ПРОКРУТКА" if r["hscroll"] else ""
                    state = f"обрезано {len(items)}" if items else "чисто"
                    print(f"== {name}/{theme}@{width}: {state}{flag}")
                    for it in items[:args.show]:
                        print(f"   {it['kind']} (−{it['lost']}px) "
                              f"{it['sel']}  «{it['text']}»")
        browser.close()
    print(f"\nвсего находок: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
