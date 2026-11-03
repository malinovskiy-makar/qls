// Обрезка математических кривых должна совпадать у SVG и готового TeX.
import * as pw from 'playwright';
import {openPage, openScene} from './tex/lib.mjs';
let total = 0, bad = 0;
for (const engine of (process.env.ENGINES || 'chromium,webkit').split(',')) {
  const browser = await pw[engine].launch();
  const {page} = await openPage(browser);
  for (const scene of ['m-transform', 'm-optimum', 'm-minmax', 'm-tangent']) {
    await openScene(page, scene);
    const result = await page.evaluate(() => {
      const leave = texEnterPaper();
      try {
        const list = texCapture(), tex = texEmit(list, {}).tex;
        const sourceIds = [...document.querySelectorAll('#chart path[clip-path]')]
          .map(el => /#([^)]*)/.exec(el.getAttribute('clip-path'))?.[1]);
        const paths = list.panels.flatMap(p => p.items.filter(it => it.kind === 'path' && it.st)
          .map(it => ({clip: it.clip, box: p.clips[it.clip]})));
        const used = new Set(paths.map(it => it.clip));
        const missing = sourceIds.filter(id => !used.has(id));
        // Проверяем также файл, а не только промежуточную опись.
        const clips = [...tex.matchAll(/\\clip \(axis cs:([^,]+),([^)]+)\) rectangle \(axis cs:([^,]+),([^)]+)\);/g)]
          .map(m => m.slice(1).map(Number));
        const exported = paths.every(it => it.box && clips.some(box => box.every((v, i) => Math.abs(v - it.box[i]) < 1e-3)));
        return {paths: paths.length, missing, exported};
      } finally { leave(); }
    });
    total++;
    const ok = result.paths > 0 && !result.missing.length && result.exported;
    if (!ok) bad++;
    console.log((ok ? 'OK ' : 'FAIL ') + engine + '/' + scene + ' ' + JSON.stringify(result));
  }
  await browser.close();
}
console.log(`TeX clip: ${total - bad}/${total}, ошибок ${bad}`);
process.exitCode = bad ? 1 : 0;
