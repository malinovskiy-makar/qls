"""Прогон страницы проверки экзамена в безголовом Chromium (Python-Playwright).

Запускается ОТДЕЛЬНЫМ процессом из `test_ai_exam_page_browser.py` (так же, как
node-раннеры calc2): sync-Playwright плохо живёт внутри процесса Django.
Печатает один JSON в stdout. Аргумент — путь к html страницы.

Сценарий: карточка 103 («Годится»), у пункта «а» подписанные P и Q, пункт «б»
«не проверяется»; перезагрузка; скачивание разметки.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright  # noqa: E402


def main(page_path):
    url = Path(page_path).resolve().as_uri()
    out = {}
    with sync_playwright() as pw, tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True) as prof:
        ctx = pw.chromium.launch_persistent_context(
            prof, headless=True, accept_downloads=True)
        page = ctx.new_page()
        console, errors, external = [], [], []
        page.on('console', lambda m: console.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: external.append(r.url)
                if not r.url.startswith(('file:', 'data:', 'blob:')) else None)
        page.goto(url)
        page.wait_for_selector('.qx-card')

        page.locator('#qx-name').fill('Проверяющий')
        card = page.locator('.qx-card[data-id="103"]')
        card.locator('button[data-v="ok"]').click()
        first = card.locator('.qx-ask').nth(0)
        first.locator('.qx-val .qx-l').first.fill('P')
        first.locator('.qx-add').click()
        second = first.locator('.qx-val').nth(1)
        second.locator('.qx-l').fill('Q')
        second.locator('.qx-v').fill('12')
        card.locator('.qx-ask').nth(1).locator('input[data-f="skip"]').check()
        out['inputs_disabled_when_skipped'] = card.locator('.qx-ask').nth(1).locator(
            '.qx-val input').first.is_disabled()
        out['remove_disabled_on_single_row'] = card.locator('.qx-ask').nth(1).locator(
            '.qx-rm').first.is_disabled()
        out['remove_enabled_on_two_rows'] = first.locator('.qx-rm').first.is_enabled()
        page.locator('.qx-card[data-id="101"] button[data-v="skip"]').click()

        page.reload()
        page.wait_for_selector('.qx-card')
        card = page.locator('.qx-card[data-id="103"]')
        first = card.locator('.qx-ask').nth(0)
        out['rows_after_reload'] = first.locator('.qx-val').count()
        out['second_after_reload'] = [
            first.locator('.qx-val').nth(1).locator('.qx-l').input_value(),
            first.locator('.qx-val').nth(1).locator('.qx-v').input_value()]
        out['skip_after_reload'] = card.locator('.qx-ask').nth(1).locator(
            'input[data-f="skip"]').is_checked()
        out['verdict_after_reload'] = card.get_attribute('data-verdict')

        with page.expect_download() as dl:
            page.locator('text=Скачать разметку').click()
        target = Path(prof) / 'out.json'
        dl.value.save_as(str(target))
        out['payload'] = json.loads(target.read_text(encoding='utf-8'))
        out['warning'] = page.locator('#qx-warn').inner_text()
        out['katex_count'] = page.locator('.katex').count()
        out['katex_errors'] = page.locator('.katex-error').count()
        out['console_errors'] = console
        out['page_errors'] = errors
        out['external_requests'] = external
        ctx.close()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
