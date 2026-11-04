/* Общая часть превью моделей (ADR 0141): таблица токенов темы и подключение
   внутристраничной части. Её берут генератор make_previews.mjs и сторож
   свежести в tex/ci_quick.mjs. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ROOT } from '../tex/lib.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const INPAGE_PV = path.join(HERE, 'inpage.js');
export const PREVIEWS_JSON = path.join(ROOT, 'calc2/static/calc2/previews.json');
export const REBUILD = 'node calc2/tests/previews/make_previews.mjs';

/* Светлые значения токенов холста → имя токена. Порядок старшинства при
   совпадении значений: роль кривой, затраты, служебные цвета сцены, группы
   сложения, чернила. Совпадающие значения в тёмной теме у них одинаковы,
   кроме --sum-g1 и --sum-g5 (там разница в пару единиц тона). */
export function tokenTable() {
  const css = fs.readFileSync(path.join(ROOT, 'calc2/static/calc2/calc2.css'), 'utf8');
  const val = {};
  const re = /:root\s*\{([^}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const body = m[1].replace(/\/\*[\s\S]*?\*\//g, '');
    for (const d of body.matchAll(/--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\b/g)) val[d[1]] = d[2].slice(1).toUpperCase();
  }
  const order = [/^curve-/, /^cost-/, /^c-(warn|bad|profit|price)$/, /^sum-g\d$/, /^ink(-soft)?$/];
  const table = {};
  order.forEach(rx => Object.keys(val).filter(k => rx.test(k)).forEach(k => { if (!table[val[k]]) table[val[k]] = k; }));
  return table;
}

export async function addPreviewScript(page) { await page.addScriptTag({ path: INPAGE_PV }); }

