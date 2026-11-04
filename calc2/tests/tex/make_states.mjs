/* Набор состояний выгрузки .tex (прибор tex_states): собирает states.json.

   Источники (PROMPT.md, фаза 0, п. 1):
     start    — 44 модели на старте;
     step     — шаги базового снимка редизайна, меняющие холст
                (calc2/tests/redesign/baseline/*.json, поле steps: только шаги с
                geometry, без повторов холста — отбор как в proto/replay.mjs);
     gesture  — жесты того же снимка: протяжка ручки и колесо;
     recipe   — рецепты calc2/tests/tex/recipes/*.json (вмешательства,
                непрямые формулы, своё окно и добавленные состояния).
   У каждого состояния имя, модель и способ дойти; набор лежит в git.

   node calc2/tests/tex/make_states.mjs        пересобрать states.json
   node calc2/tests/tex/make_states.mjs --check  код 1, если states.json устарел */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { HERE, RD } from './lib.mjs';

const states = [];
const files = fs.readdirSync(path.join(RD, 'baseline')).filter(x => x.endsWith('.json')).sort();
const keys = files.map(f => f.replace(/\.json$/, ''));
keys.forEach(k => states.push({ id: k + '#start', key: k, src: 'start' }));
for (const f of files) {
  const bl = JSON.parse(fs.readFileSync(path.join(RD, 'baseline', f), 'utf8'));
  const desc = (k) => (bl.controls || []).find(c => c.key === k) || (bl.inventory && bl.inventory[k] ? { key: k } : null);
  const seen = new Set();
  (bl.steps || []).forEach((st, i) => {
    if (!st.geometry) return;                        // шаг холст не менял
    const h = crypto.createHash('sha1').update(JSON.stringify([st.geometry, st.windows || null])).digest('hex');
    if (seen.has(h)) return; seen.add(h);            // такой холст уже есть
    if (st.path.some(k => !desc(k))) return;
    states.push({ id: bl.key + '#' + i, key: bl.key, src: 'step', path: st.path });
  });
  (bl.gestures || []).forEach((g, i) => {
    if (g.error) return;
    if (g.kind === 'drag') states.push({ id: bl.key + '#drag-' + g.handle, key: bl.key, src: 'gesture', gesture: 'drag', handle: g.handle });
    else if (g.kind === 'wheel') states.push({ id: bl.key + '#wheel', key: bl.key, src: 'gesture', gesture: 'wheel' });
  });
}
const seenR = new Map();
for (const f of fs.readdirSync(path.join(HERE, 'recipes')).filter(x => x.endsWith('.json')).sort()) {
  const r = JSON.parse(fs.readFileSync(path.join(HERE, 'recipes', f), 'utf8'));
  Object.keys(r).filter(k => !k.startsWith('_')).forEach(k => Object.keys(r[k]).forEach(v => {
    const id = k + '@' + v;
    if (seenR.has(id)) throw new Error('рецепт ' + id + ' и в ' + seenR.get(id) + ', и в ' + f);
    seenR.set(id, f);
    const val = r[k][v];
    const st = { id, key: k, src: 'recipe', recipe: id, file: f };
    if (val && typeof val === 'object') { if (val.title != null) st.title = val.title; if (val.label != null) st.label = val.label; }
    states.push(st);
  }));
}
const ids = new Set();
states.forEach(s => { if (ids.has(s.id)) throw new Error('повтор имени ' + s.id); ids.add(s.id); });
const text = '[\n' + states.map(s => ' ' + JSON.stringify(s)).join(',\n') + '\n]\n';
const file = path.join(HERE, 'states.json');
const by = {}; states.forEach(s => { by[s.src] = (by[s.src] || 0) + 1; });
console.log('состояний', states.length, JSON.stringify(by));
if (process.argv.includes('--check')) {
  const old = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
  if (old !== text) { console.log('states.json устарел: пересоберите node calc2/tests/tex/make_states.mjs'); process.exit(1); }
  process.exit(0);
}
fs.writeFileSync(file, text);
console.log('→', file);
