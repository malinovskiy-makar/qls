# -*- coding: utf-8 -*-
"""Раннер `test_auth_fit_browser`: меряет прокрутку входа и регистрации.

Отдельным процессом, а не внутри теста: на Windows синхронный Playwright не
уживается с циклом событий тестового процесса. Аргумент — адрес живого сервера.
Печатает `###FIT-JSON###` и строку JSON; браузер не поднялся — код 3.
"""
import json
import sys

from playwright.sync_api import Error, sync_playwright

WINDOWS = ((1440, 778), (1536, 730))


def main(base):
    seen = {}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Error as exc:
            print('браузер не поднялся: %s' % exc)
            return 3
        for width, height in WINDOWS:
            context = browser.new_context(viewport={'width': width, 'height': height})
            context.add_cookies([{'name': 'weco_consent', 'value': 'necessary', 'url': base}])
            page = context.new_page()
            for path in ('/register/', '/login/'):
                page.goto(base + path, wait_until='load')
                page.wait_for_timeout(500)          # анимация появления карточки
                seen['%s %dx%d' % (path, width, height)] = page.evaluate(
                    '() => [document.documentElement.scrollHeight, innerHeight,'
                    ' document.querySelectorAll(".social-btn").length,'
                    ' document.querySelectorAll(".consent").length]')
            context.close()
        browser.close()
    print('###FIT-JSON###')
    print(json.dumps(seen))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
