/* Быстрый взгляд на модель (сессия 6, рабочий): node claude/panels_s6/peek.mjs <модель> "<js до замера>" "<js-выражение замера>" [ширина] [движок]
   BASE — сервер (по умолчанию 8099). Печатает JSON результата и ошибки страницы. */
import * as pw from 'playwright';
const [key, pre, expr, W, engine] = process.argv.slice(2);
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const b = await pw[engine || 'chromium'].launch();
const ctx = await b.newContext({ viewport: { width: +(W || 1440), height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.clear(); localStorage.setItem('theme', process_theme()); } catch (e) {} function process_theme(){return 'light';} try { localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} });
const page = await ctx.newPage();
const errs = []; page.on('pageerror', e => errs.push(String(e).slice(0, 300)));
await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
await page.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
await page.waitForTimeout(800);
if (pre) { await page.evaluate(pre); await page.waitForTimeout(800); }
const r = await page.evaluate(expr || '1');
console.log(JSON.stringify(r, null, 1));
if (errs.length) console.log('ОШИБКИ:', errs);
await b.close();
