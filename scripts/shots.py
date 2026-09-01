# -*- coding: utf-8 -*-
"""Снимки экранов сайта в обеих темах — глазами, а не расчётом.

Зачем. Расчёт контраста может сойтись, а экран выйти плохим: шрифт не
доехал, все блоки одного цвета, текст обрезан. Единственная проверка,
которая это ловит, — посмотреть на картинку. Скрипт снимает набор
страниц в светлой и тёмной теме и складывает в reports/shots/<дата>/.

Запуск (сервер должен быть уже поднят):
    python scripts/shots.py --tag before
    python scripts/shots.py --tag after --only login,styleguide

Тема переключается атрибутом data-theme на <html> — тем же способом,
что и кнопка на сайте, поэтому снимок показывает ровно то, что увидит
человек, а не отдельный режим «для тестов».
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
ROOT = Path(__file__).resolve().parent.parent

# Логин отдельного бота, заведённого в локальной копии базы. Пароли
# боевых аккаунтов сюда не попадают и попасть не могут: база локальная.
USER = "shot_bot"
PASSWORD = "shotbot-local-2026"

# Страницы: имя → путь. {pid} подставляется id живой задачи.
PAGES = {
    "login": "/login/",
    "home": "/",
    "styleguide": "/teacher/styleguide/",
    "catalog": "/catalog/",
    "problem": "/catalog/problem/{pid}/",
    "search": "/catalog/smart-search/",
    "stats": "/profile/stats/",
    "game": "/game/",
    "calendar": "/calendar/",
    "calc2": "/calc2/",
    "calc2work": "/calc2/",
}

# Страницы, которые снимаются БЕЗ входа (иначе редиректит на кабинет).
ANONYMOUS = {"login"}

# ⚠️ ГОСТЬ ВИДИТ ДРУГУЮ ШАПКУ. У вошедшего там имя и «Выйти», у гостя —
#    кнопка «Войти». Снимок под ботом её не показывает вовсе, а именно её
#    и просили посмотреть. Флаг --anon снимает страницы без входа.

# ⚠️ РАБОЧИЙ ЭКРАН КАЛЬКУЛЯТОРА СВОИМ АДРЕСОМ НЕ ОТКРЫВАЕТСЯ. У /calc2/ один
#    маршрут, сцену выбирают щелчками: сначала блок, потом модель. Без этих
#    двух щелчков снимок показывает окно выбора, а не холст с кривыми — то
#    есть ровно НЕ ТО, что нужно проверять при правках фона и шрифта.
AFTER_LOAD = {
    "calc2work": [
        "#picker-blocks button >> nth=1",          # блок «Совершенная конкуренция»
        ".picker-group.open .scard:not(.soon) >> nth=0",   # первая рабочая модель
    ],
}


def theme_script(theme: str) -> str:
    """Ставит тему до отрисовки — так же, как анти-мигание в _tokens."""
    return (
        "() => {"
        f"  document.documentElement.setAttribute('data-theme', '{theme}');"
        f"  try {{ localStorage.setItem('theme', '{theme}'); }} catch (e) {{}}"
        "}"
    )


def probe_fonts(page):
    """Чем браузер РЕАЛЬНО рисует текст. Не «что написано в CSS»."""
    return page.evaluate(
        """() => {
          const seen = (sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const cs = getComputedStyle(el);
            return {
              family: cs.fontFamily,
              size: cs.fontSize,
              weight: cs.fontWeight,
              lh: cs.lineHeight,
            };
          };
          return {
            varFontUi: getComputedStyle(document.documentElement)
                         .getPropertyValue('--font-ui').trim(),
            loaded400: document.fonts.check('16px Montserrat'),
            loaded700: document.fonts.check('700 16px Montserrat'),
            italic:    document.fonts.check('italic 16px Montserrat'),
            faces: [...document.fonts].map(f =>
                     `${f.family} ${f.style} ${f.weight} ${f.status}`),
            body:   seen('body'),
            h1:     seen('h1'),
            button: seen('button, .btn, input[type=submit]'),
            link:   seen('a'),
          };
        }"""
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="shot", help="подпапка: before / after / ...")
    ap.add_argument("--only", default="", help="через запятую: login,catalog")
    ap.add_argument("--pid", default="", help="id задачи для /catalog/problem/")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--full", action="store_true", help="снимать страницу целиком")
    ap.add_argument("--anon", action="store_true", help="снимать гостем, без входа")
    args = ap.parse_args()

    pid = args.pid or "63321"
    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or list(PAGES)

    stamp = dt.datetime.now().strftime("%Y%m%d")
    out = ROOT / "reports" / "shots" / f"{stamp}_{args.tag}"
    out.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=2,
            locale="ru-RU",
        )
        page = ctx.new_page()

        # Вход один раз на весь прогон.
        if args.anon:
            print("снимаем гостем: вход пропущен")
        try:
            if args.anon:
                raise RuntimeError("--anon")
            page.goto(f"{BASE}/login/", wait_until="networkidle")
            page.fill("input[name=username]", USER)
            page.fill("input[name=password]", PASSWORD)
            page.click("button[type=submit], input[type=submit]")
            page.wait_for_load_state("networkidle")
            print(f"вход: {page.url}")
        except Exception as exc:  # форма могла смениться — снимем анонимно
            if not args.anon:
                print(f"ВХОД НЕ УДАЛСЯ: {exc}")

        for name in wanted:
            if name not in PAGES:
                print(f"пропуск: неизвестная страница {name}")
                continue
            url = BASE + PAGES[name].format(pid=pid)
            for theme in ("light", "dark"):
                page.add_init_script(theme_script(theme))
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception as exc:
                    print(f"  {name}/{theme}: НЕ ОТКРЫЛАСЬ — {exc}")
                    continue
                page.evaluate(theme_script(theme))
                # шрифтам дают доехать: снимок до загрузки покажет запасной
                page.evaluate("() => document.fonts.ready")
                page.wait_for_timeout(400)
                for step in AFTER_LOAD.get(name, []):
                    try:
                        page.click(step, timeout=8000)
                        page.wait_for_timeout(900)
                    except Exception as exc:
                        print(f"  {name}/{theme}: шаг «{step}» не сработал — {exc}")
                if name in AFTER_LOAD:
                    page.wait_for_timeout(900)
                shot = out / f"{name}_{theme}.png"
                page.screenshot(path=str(shot), full_page=args.full)
                if theme == "light":
                    report[name] = {
                        "url": page.url,
                        "status_title": page.title(),
                        "fonts": probe_fonts(page),
                    }
                print(f"  {name}/{theme} -> {shot.name}")

        browser.close()

    (out / "probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nготово: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
