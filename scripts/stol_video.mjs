/* Видео сценариев «Стола» для владельца (дневная сессия 18.09.2026).
   node scripts/stol_video.mjs <сценарий> [порт]
   Сценарии: s2 — вход → клик по строке → задача → «Дальше» → «назад» → «назад».
   Выход: reports/stol_20260918/<сценарий>_*.webm */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const NAME = process.argv[2] || 's2';
const BASE = 'http://127.0.0.1:' + (process.argv[3] || '8000');
const OUT = path.join('reports', 'stol_20260918');
const SCENES = {
  s2: async page => {
    await page.goto(BASE + '/catalog/?topic=843', { waitUntil: 'load' });
    await page.waitForTimeout(1500);
    await page.click('#ct-rows .rail-row:nth-child(2)');
    await page.waitForSelector('#stol-center .stm');
    await page.waitForTimeout(2000);
    await page.click('#tb-next');
    await page.waitForTimeout(2200);
    await page.goBack();
    await page.waitForTimeout(1800);
    await page.goBack();
    await page.waitForTimeout(2000);
  },
};

fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                       recordVideo: { dir: OUT, size: { width: 1440, height: 900 } } });
const page = await ctx.newPage();
page.setDefaultTimeout(60000);
await SCENES[NAME](page);
const video = page.video();
await ctx.close();
const file = path.join(OUT, NAME + '_' + (NAME === 's2' ? 'no_reload' : 'map') + '.webm');
fs.renameSync(await video.path(), file);
await browser.close();
console.log('видео: ' + file);
