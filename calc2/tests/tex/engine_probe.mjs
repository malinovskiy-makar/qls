/* Проверка движка в начале выгружаемого .tex (сессия 3, 10.2026; ADR 0144).

   Берёт у живой страницы файл модели (дверь buildTex) и собирает его:
     · pdfLaTeX — собирается, PDF есть;
     · XeLaTeX и LuaLaTeX — сборка останавливается с нашим текстом
       «Соберите этот файл через pdfLaTeX», PDF нет (раньше кириллица под
       ними пропадала молча, а файл «собирался»).
   Движка нет на машине — проверка пропускается и печатает это громко.

   node calc2/tests/tex/engine_probe.mjs [--keys sd,trade]
   Код 0 — всё сошлось; 1 — нет; 3 — pdflatex не найден.                    */
import { chromium } from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const KEYS = (arg('keys', 'sd,trade') || '').split(',').filter(Boolean);
const MSG = 'Соберите этот файл через pdfLaTeX';

const which = (b) => {
  for (const dir of (process.env.PATH || '').split(path.delimiter).concat(['/Library/TeX/texbin'])) {
    const p = path.join(dir, b);
    if (fs.existsSync(p)) return p;
  }
  return null;
};
const PDF = which('pdflatex');
if (!PDF) { console.log('pdflatex не найден'); process.exit(3); }

let bad = 0, total = 0;
const ok = (label, cond, detail) => { total++; if (!cond) bad++; console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : '')); };

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 30000 });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'calc2-engine-'));
for (const key of KEYS) {
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
  await page.waitForTimeout(700);
  const tex = await page.evaluate(() => new Promise(res => afterFonts(() => res(buildTex(SCENE_NAMES[STATE.sceneKey], '')))));
  console.log('\n=== ' + key + ' ===');
  for (const [eng, wantPdf] of [['pdflatex', true], ['xelatex', false], ['lualatex', false]]) {
    const bin = which(eng);
    if (!bin) { console.log('  ПРОПУСК ' + eng + ': движок не установлен на этой машине'); continue; }
    const dir = fs.mkdtempSync(path.join(tmp, eng + '-'));
    fs.writeFileSync(path.join(dir, 'g.tex'), tex);
    const r = spawnSync(bin, ['-interaction=nonstopmode', '-halt-on-error', 'g.tex'], { cwd: dir, encoding: 'utf8', timeout: 180000 });
    const out = (r.stdout || '') + (r.stderr || '');
    const pdf = fs.existsSync(path.join(dir, 'g.pdf'));
    if (wantPdf) ok(eng + ': собирается, PDF есть', r.status === 0 && pdf, 'код ' + r.status + (pdf ? '' : ', PDF нет') + (r.status ? ' | ' + (out.match(/^! .*$/m) || [''])[0] : ''));
    else ok(eng + ': останавливается с «' + MSG + '», PDF нет', r.status !== 0 && !pdf && out.includes(MSG),
      'код ' + r.status + (pdf ? ', PDF есть' : ', PDF нет') + ' | ' + ((out.match(/^! .*$/m) || ['(ошибки нет)'])[0]).slice(0, 90));
  }
}
await browser.close();
fs.rmSync(tmp, { recursive: true, force: true });
console.log(bad ? '\nНЕ СОШЛОСЬ: ' + bad + ' из ' + total : '\nВСЁ СОШЛОСЬ: ' + total + ' проверок');
process.exit(bad ? 1 : 0);
