/**
 * Контур качества (Q1, 29.10.2026): задача глазами ученика в настоящем Chromium.
 *
 *   node scripts/olympiad_contour_render.js <jobs.json>
 *
 * jobs.json: {jobs: [{pid, url}], out: "результаты.jsonl", html_dir, shot_dir,
 *             shots: [pid…], concurrency, widths: [390, 1280]}
 *
 * На задачу — одна загрузка (runserver с config.settings_quality_ro, служебный
 * просмотр /_quality/problem/<id>/), замер на каждой ширине (окно меняется без
 * перезагрузки, KaTeX от ширины не зависит). Сырой HTML ответа сервера
 * сохраняется (gzip) — по нему Python проверяет R1–R6, не рендеря страницу
 * второй раз. Замеры (B1–B4), только в блоках текста задачи (`.math-content`,
 * `#q-solution`):
 *   scroll      — у страницы горизонтальная прокрутка (scrollWidth > clientWidth);
 *   overflow    — элемент текста задачи вылезает за правый край окна;
 *   katex_err   — `.katex-error`; red — цвет rgb(204, 0, 0) у элемента;
 *   broken_img  — <img> загрузилась с naturalWidth = 0;
 *   wide_table  — таблица шире своего блока текста.
 * Повтор прогона дописывает в out только задачи, которых там ещё нет.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { chromium } = require('playwright');

const MEASURE = () => {
  const de = document.documentElement;
  const vw = de.clientWidth;
  const roots = [...document.querySelectorAll('.math-content, #q-solution')]
    .filter((el) => !el.parentElement.closest('.math-content'));
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  let overflow = [];
  let red = 0;
  let katexErr = 0;
  const brokenImg = [];
  let wideTable = 0;
  for (const root of roots) {
    katexErr += root.querySelectorAll('.katex-error').length;
    for (const el of root.querySelectorAll('[style], .katex-error')) {
      if (getComputedStyle(el).color === 'rgb(204, 0, 0)') red += 1;
    }
    for (const img of root.querySelectorAll('img')) {
      if (img.complete && img.naturalWidth === 0) brokenImg.push(img.getAttribute('src') || '');
    }
    const box = root.getBoundingClientRect();
    for (const t of root.querySelectorAll('table')) {
      // таблица сайта — блок с прокруткой (stol.css): шире блока = её надо листать вбок
      if (visible(t) && (t.getBoundingClientRect().width > box.width + 1 || t.scrollWidth > t.clientWidth + 1)) wideTable += 1;
    }
    if (!visible(root)) continue;
    // вылет за край, который не прячет прокручиваемый предок (таблица, формула-блок).
    // Смотрим ВСЕХ обрезающих предков: у svg внутри формулы свой overflow:hidden,
    // а помещается в окно уже блок формулы над ним (29.10, задача #520).
    const contained = (el) => {
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        if (getComputedStyle(a).overflowX !== 'visible' && a.getBoundingClientRect().right <= vw + 1) return true;
      }
      return false;
    };
    for (const el of root.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width && r.right > vw + 1 && !contained(el)) {
        const cls = typeof el.className === 'string' ? el.className : '';
        overflow.push((el.tagName + (cls ? '.' + cls.split(' ')[0] : '')).slice(0, 60));
        if (overflow.length > 5) break;
      }
    }
  }
  return {
    scroll: de.scrollWidth > vw + 1, scroll_px: de.scrollWidth - vw,
    overflow, katex_err: katexErr, red, broken_img: brokenImg, wide_table: wideTable,
    roots: roots.length,
  };
};

async function one(ctx, job, cfg) {
  const page = await ctx.newPage();
  const rec = { pid: job.pid, url: job.url, widths: {} };
  try {
    await page.setViewportSize({ width: cfg.widths[0], height: 900 });
    const resp = await page.goto(job.url, { waitUntil: 'load', timeout: 60000 });
    rec.status = resp ? resp.status() : 0;
    if (resp && cfg.html_dir) {
      const body = await resp.body();
      fs.writeFileSync(path.join(cfg.html_dir, job.pid + '.html.gz'), zlib.gzipSync(body));
    }
    await page.waitForFunction(() => [...document.images].every((i) => i.complete), null, { timeout: 15000 })
      .catch(() => { rec.img_timeout = true; });
    for (const w of cfg.widths) {
      await page.setViewportSize({ width: w, height: 900 });
      await page.waitForTimeout(60);
      rec.widths[w] = await page.evaluate(MEASURE);
      if (cfg.shots.has(job.pid) && w === cfg.widths[0]) {
        const h = await page.evaluate(() => Math.min(document.documentElement.scrollHeight, 2600));
        await page.screenshot({ path: path.join(cfg.shot_dir, job.pid + '.jpg'), type: 'jpeg', quality: 62,
                                clip: { x: 0, y: 0, width: w, height: h }, fullPage: true });
      }
    }
  } catch (e) {
    rec.error = String(e.message || e).slice(0, 300);
  } finally {
    await page.close();
  }
  return rec;
}

(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  cfg.shots = new Set(cfg.shots || []);
  for (const d of [cfg.html_dir, cfg.shot_dir]) if (d) fs.mkdirSync(d, { recursive: true });
  const done = new Set();
  if (fs.existsSync(cfg.out)) {
    for (const line of fs.readFileSync(cfg.out, 'utf8').split('\n')) {
      if (line.trim()) { const r = JSON.parse(line); if (!r.error) done.add(r.pid); }
    }
  }
  const jobs = cfg.jobs.filter((j) => !done.has(j.pid));
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 1 });
  const outStream = fs.createWriteStream(cfg.out, { flags: 'a' });
  let next = 0, finished = 0;
  const t0 = Date.now();
  async function worker() {
    while (next < jobs.length) {
      const job = jobs[next++];
      const rec = await one(ctx, job, cfg);
      outStream.write(JSON.stringify(rec) + '\n');
      finished += 1;
      if (finished % 200 === 0) {
        console.log(`${finished}/${jobs.length} за ${Math.round((Date.now() - t0) / 1000)} с`);
      }
    }
  }
  await Promise.all(Array.from({ length: cfg.concurrency || 4 }, worker));
  await new Promise((r) => outStream.end(r));
  await browser.close();
  console.log(`готово: ${finished} задач, ${Math.round((Date.now() - t0) / 1000)} с`);
})().catch((e) => { console.error(e); process.exit(1); });
