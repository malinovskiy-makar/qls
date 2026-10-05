/* БЫСТРЫЙ ПАРИТЕТ (редизайн calc2, фаза 11): то, что идёт в CI.

   Одна страница, 44 ключа подряд, каждый со свежим состоянием
   (resetSceneMemory + pickScene). Для каждого ключа против базового снимка
   старого экрана (calc2/tests/redesign/baseline/<ключ>.json, раздел start):
     1. органы управления на месте: каждый орган старта старого экрана найден
        на новом — сам, по замене из закрытого списка (fates.mjs) или в
        закрытом меню своей карточки; убранные по (л), (м) и заменённые видом
        рабочего места (в, г, д, к) не ищутся — их судьба в PARITY.md;
     2. видимые числа старта равны базовым: каждая строка табло (блок,
        номер, значение) и итоговая функция.
   Подробная сверка (шаги, жесты, геометрия) — snapshot.mjs + compare.mjs,
   вручную: она идёт часами.

   CALC2_BASE_URL=… node calc2/tests/redesign/parity_quick.mjs
   Код 0 — паритет цел; 1 — расхождения; 3 — calc2 не загрузился (провал);
   4 — Playwright не запустился (пропуск теста).                            */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { fateOf } from './fates.mjs';
import * as layerNew from './layer_new.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BL = path.join(HERE, 'baseline');
const INPAGE = fs.readFileSync(path.join(HERE, 'inpage.js'), 'utf8');
const keys = fs.readdirSync(BL).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)).sort();
const t0 = Date.now();

let browser;
try { browser = await chromium.launch(); } catch (e) { console.error('Playwright не запустился: ' + e.message); process.exit(4); }
/* Ширина окна: 1440 (по умолчанию), 1024, 390 — паритет органов проверяется на
   всех трёх (задание редизайна, инварианты). На узких ширинах орган может
   жить в выезжающем «Ответе» или на другой вкладке телефона: «достижим»
   значит «виден сам или после выезда панели / смены вкладки». */
const VW = +(process.env.PQ_WIDTH || 1440), VH = +(process.env.PQ_HEIGHT || 760);
const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, reducedMotion: 'reduce', locale: 'ru-RU',
  isMobile: VW < 760, hasTouch: VW < 760 });
await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
try {
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof math !== 'undefined' && typeof d3 !== 'undefined', null, { timeout: 30000 });
} catch (e) { console.error('calc2 не загрузился: ' + e.message); await browser.close(); process.exit(3); }
await page.addScriptTag({ content: INPAGE });
await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });

const norm = (s) => String(s == null ? '' : s).replace(/[\s   ​]+/g, '').replace(/[−–]/g, '-');
let bad = 0, checks = 0;
const issues = [];
for (const key of keys) {
  const rec = JSON.parse(fs.readFileSync(path.join(BL, key + '.json'), 'utf8'));
  const e0 = errors.length;
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); if (typeof closePicker === 'function') closePicker(); redrawAll(); }, key);
  await page.waitForFunction(() => window.__RD.settled(), null, { timeout: 6000 }).catch(() => null);
  await page.waitForTimeout(120);
  // 1. Органы старта.
  const wantC = (rec.controls || rec.start.controls || []).filter(c => !c.picker);
  const want = wantC.map(c => c.key);
  /* Глаз кривой: на старом экране номер в ключе «#curve-list>input[n]» считал
     все поля списка (глаз, поле записи), на новом глаз — своя кнопка в
     карточке. Сопоставляем по порядку глаз: k-й глаз старого — k-й новый. */
  const eyes = wantC.filter(c => /^#curve-list>input(\[\d+\])?$/.test(c.key) && c.kind === 'input:checkbox').map(c => c.key);
  const eyeKey = (k) => { const j = eyes.indexOf(k); return j < 0 ? null : '#curve-list>button.fc-eye' + (j ? '[' + j + ']' : ''); };
  const res = await page.evaluate(async (list) => {
    // Выезд панели и смена вкладки видны не в тот же миг: видимость у
    // потомков панели меняется переходом (до 0,2 с).
    const pause = () => new Promise(r => setTimeout(r, 260));
    const out = [];
    for (const k of list) {
      let el = window.__RD.findControl(k.mapped);
      if (!el) {
        // Узкая ширина: выезжающий «Ответ» или вкладки телефона.
        const tabs = [...document.querySelectorAll('#ph-tabs .ph-tab')].filter(b => b.offsetParent !== null);
        for (const t of tabs) { t.click(); await pause(); el = window.__RD.findControl(k.mapped); if (el) break; }
        if (!el && document.querySelector('#btn-answer') && document.querySelector('#btn-answer').offsetParent !== null) {
          document.body.classList.add('ans-open'); await pause(); el = window.__RD.findControl(k.mapped); document.body.classList.remove('ans-open');
        }
        // Телефон: лист «Действия» за «⋯» (README макета, раздел 3).
        const more = document.getElementById('btn-ph-more');
        if (!el && more && more.offsetParent !== null) {
          more.click(); await pause(); el = window.__RD.findControl(k.mapped);
          if (typeof closePop === 'function') closePop();
        }
        if (tabs.length) tabs[0].click();
      }
      // Орган в закрытом меню «…» своей карточки — достижим открытием меню.
      if (!el) { const any = window.__RD.findControlAny(k.mapped); if (any && any.closest('.fc-menu')) el = any; }
      if (!el) out.push(k.orig);
    }
    return out;
  }, want.filter(k => {
    const f = fateOf(k);
    return !(f.fate === 'убран' || (f.fate === 'заменён' && /^[авгдк]$/.test(f.letter)));
  }).map(k => ({ orig: k, mapped: eyeKey(k) || layerNew.mapKey(k.replace(/~\d+$/, '')) })));
  checks += want.length;
  res.forEach(k => { bad++; issues.push(key + ': орган ' + k + ' не найден'); });
  // 2. Числа старта.
  const ans = await page.evaluate(() => window.__RD.answerOld());
  const b1 = new Map((ans.blocks || []).map(b => [b.id, b]));
  (rec.start.answer.blocks || []).forEach(b => {
    const c = b1.get(b.id);
    b.rows.forEach(r => {
      checks++;
      const q = c && c.rows.find(x => String(x.i) === String(r.i));
      if (!q) { bad++; issues.push(key + ': ' + b.id + ' строка «' + r.label + '» не показана'); return; }
      if (norm(q.value) !== norm(r.value)) { bad++; issues.push(key + ': ' + b.id + ' «' + r.label + '» ' + r.value + ' → ' + q.value); }
    });
    (b.final || []).forEach((f, i) => {
      checks++;
      const g = c && (c.final || [])[i];
      if (!g || g.copy !== f.copy) { bad++; issues.push(key + ': итоговая функция «' + f.name + '» разошлась'); }
    });
  });
  // Ошибки страницы, которых не было на старом экране.
  const old = new Set((rec.errors || []).map(e => String(e).replace(/[\d.]+/g, '#')));
  errors.slice(e0).forEach(e => { if (!old.has(String(e).replace(/[\d.]+/g, '#'))) { bad++; issues.push(key + ': ошибка страницы ' + e); } });
}
await browser.close();
const sec = ((Date.now() - t0) / 1000).toFixed(1);
issues.slice(0, 400).forEach(x => console.log('  ✗ ' + x));
console.log((bad ? 'ПАРИТЕТ НАРУШЕН' : 'ПАРИТЕТ ЦЕЛ') + ' (' + VW + '×' + VH + '): ключей ' + keys.length + ', проверок ' + checks + ', расхождений ' + bad + ', ' + sec + ' с');
process.exit(bad ? 1 : 0);
