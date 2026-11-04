/* Мёртвый ли ползунок буквы (сессия 6, В5; Notion …8187…): сдвиг буквы-параметра не меняет ни «Ответ», ни ОДИН узел
   холста (все узлы SVG и все их атрибуты, не только пути), ни .tex.
   node claude/panels_s6/dead_axis_probe.mjs <модель> <буква> [значения…]   (BASE — сервер, по умолчанию 8099)
   Печатает замер и выходит с кодом 0, если НИЧЕГО не изменилось ни при одном значении. */
import { chromium } from 'playwright';
const [key, letter, ...vals] = process.argv.slice(2);
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.clear(); localStorage.setItem('theme', 'light'); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} });
const p = await ctx.newPage();
const errs = []; p.on('pageerror', e => errs.push(String(e)));
await p.goto(BASE + '/calc2/'); await p.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
await p.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });
await p.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
await p.waitForTimeout(900);
const snap = () => p.evaluate(() => {
  const tx = (e) => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim(); };
  const col = document.querySelector('#params-panel .side-inner');
  const nodes = [...document.querySelectorAll('#chart *')].map(n => n.tagName + '{' + [...n.attributes].map(a => a.name + '=' + a.value).sort().join(';') + '}' + (n.childElementCount ? '' : (n.textContent || '').trim()));
  let tex = ''; try { tex = buildTex('x', 'y'); } catch (e) { tex = 'ОШИБКА ' + e; }
  return { answer: tx(col), nodes, tex: String(tex) };
});
const s0 = await snap();
const has = await p.evaluate((n) => !!(STATE.params && STATE.params[n]), letter);
const out = { model: key, letter, hasParam: has, nodes: s0.nodes.length, texLen: s0.tex.length, steps: [] };
let changed = false;
for (const v of (vals.length ? vals : ['7', '-5', '3.3'])) {
  // Как человек: дорожка ползунка буквы (чип .pchip-param с этой буквой), событие input; нет дорожки — значение напрямую.
  const how = await p.evaluate(([n, v]) => {
    const chip = [...document.querySelectorAll('.pchip-param')].find(c => (c.textContent || '').replace(/\s+/g, '').startsWith(n + '='));
    const sl = chip && chip.querySelector('input[type=range]');
    if (sl) { if (+v < +sl.min) sl.min = v; if (+v > +sl.max) sl.max = v; sl.value = v; sl.dispatchEvent(new Event('input', { bubbles: true })); sl.dispatchEvent(new Event('change', { bubbles: true })); return 'дорожка → STATE ' + STATE.params[n].value; }
    STATE.params[n].value = +v; redrawAll(); return 'напрямую';
  }, [letter, v]);
  await p.waitForTimeout(700);
  const s1 = await snap();
  const dn = s0.nodes.length !== s1.nodes.length ? 'число узлов ' + s0.nodes.length + ' → ' + s1.nodes.length : s0.nodes.map((x, i) => x === s1.nodes[i] ? null : i).filter(x => x != null).length;
  const step = { value: v, how, answerSame: s0.answer === s1.answer, nodesDiff: dn, texSame: s0.tex === s1.tex };
  if (!step.answerSame || step.nodesDiff !== 0 || !step.texSame) changed = true;
  out.steps.push(step);
}
out.errors = errs;
out.verdict = changed ? 'ЖИВОЙ: что-то меняется' : 'МЁРТВ: ничего не меняется';
console.log(JSON.stringify(out, null, 1));
await b.close();
process.exit(changed ? 1 : 0);
