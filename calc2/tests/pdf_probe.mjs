// Проба серверной сборки PDF: собирает .tex прямо в браузере (buildTex) для
// нескольких сцен и отправляет на /calc2/export/pdf/ тем же путём, что кнопка.
// Печатает по сцене: код ответа, тип содержимого, размер и число строк .tex.
// Запуск: node calc2/tests/pdf_probe.mjs  (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SCENES = (process.env.PDF_SCENES || 'sd,tax,mono,adas,isoquant,m-graph').split(',');

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);
const ready = await page.evaluate(() => typeof buildTex === 'function');
if (!ready) { console.error('SKIP: calc2 не загрузился'); await browser.close(); process.exit(3); }

let bad = 0;
for (const key of SCENES) {
  const r = await page.evaluate(async (k) => {
    pickScene(k);
    await new Promise(res => setTimeout(res, 400));
    const tex = buildTex('Проба ' + k, '');
    const fd = new FormData();
    fd.append('tex', tex);
    fd.append('name', 'probe');
    const tok = document.querySelector('[name=csrfmiddlewaretoken]');
    fd.append('csrfmiddlewaretoken', tok ? tok.value : '');
    const resp = await fetch(CALC2_PDF_URL, { method: 'POST', body: fd });
    const ct = resp.headers.get('content-type') || '';
    let size = 0, msg = '';
    if (resp.ok && ct.includes('pdf')) size = (await resp.blob()).size;
    else msg = (await resp.text()).slice(-260);
    return { status: resp.status, ct, size, msg, lines: tex.split('\n').length, chars: tex.length };
  }, key);
  const ok = r.status === 200 && r.ct.includes('pdf');
  if (!ok) bad++;
  console.log(`${ok ? 'OK  ' : 'FAIL'} ${key.padEnd(10)} код ${r.status}  ${r.ct.slice(0, 24).padEnd(26)} pdf ${String(r.size).padStart(7)} б  .tex ${String(r.lines).padStart(4)} строк / ${r.chars} знаков`);
  if (!ok) console.log('     ' + r.msg.replace(/\n/g, '\n     '));
}
await browser.close();
console.log(bad ? `\nПровалов: ${bad}` : '\nВсе сцены собрались в PDF.');
process.exit(bad ? 1 : 0);
