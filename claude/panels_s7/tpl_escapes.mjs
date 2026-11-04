// Поиск одиночной «\» перед не-буквой в шаблонных строках JS calc2 (А1: `\,` в обратных кавычках теряет «\»).
//   node claude/panels_s7/tpl_escapes.mjs  — печатает находки, код 1, если есть.
import fs from 'fs';
const dir = 'calc2/static/calc2/';
const OK = new Set(['\\', '`', '$', 'n', 't', 'r', 'u', 'x', '0', '\n', "'", '"', 'b', 'f', 'v']);
let found = 0;
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js'))) {
  const s = fs.readFileSync(dir + f, 'utf8');
  let i = 0, line = 1, st = [], prevSig = '';
  const mode = () => st[st.length - 1] || 'code';
  while (i < s.length) {
    const c = s[i], m = mode();
    if (c === '\n') line++;
    if (m === 'code' || m === 'expr') {
      if (c === '/' && s[i + 1] === '/') { while (i < s.length && s[i] !== '\n') i++; continue; }
      if (c === '/' && s[i + 1] === '*') { const j = s.indexOf('*/', i + 2); for (let k = i; k < j; k++) if (s[k] === '\n') line++; i = j + 2; continue; }
      if (c === "'" || c === '"') { st.push(c); i++; continue; }
      if (c === '`') { st.push('`'); i++; continue; }
      if (c === '/' && /[(,=:[!&|?{};+\-*%<>~^]|^$|return$/.test(prevSig)) {
        // регулярное выражение
        i++; let cls = false;
        while (i < s.length) { const d = s[i]; if (d === '\\') { i += 2; continue; } if (d === '[') cls = true; else if (d === ']') cls = false; else if (d === '/' && !cls) break; else if (d === '\n') break; i++; }
        i++; prevSig = 'x'; continue;
      }
      if (m === 'expr' && c === '{') { st.push('expr'); i++; prevSig = '{'; continue; }
      if (m === 'expr' && c === '}') { st.pop(); i++; prevSig = '}'; continue; }
      if (c === '{') st.push('code');
      if (c === '}' && st.length && mode() === 'code') st.pop();
      if (!/\s/.test(c)) prevSig = /[A-Za-z_$0-9]/.test(c) ? (s.slice(Math.max(0, i - 5), i + 1).endsWith('return') ? 'return' : 'w') : c;
      i++; continue;
    }
    if (m === "'" || m === '"') {
      if (c === '\\') { i += 2; continue; }
      if (c === m || c === '\n') { st.pop(); prevSig = 'x'; }
      i++; continue;
    }
    if (m === '`') {
      if (c === '\\') {
        const d = s[i + 1];
        if ((!OK.has(d) && !/[A-Za-z]/.test(d)) || (/[fbtrvn]/.test(d) && /[a-z]{2}/.test(s.slice(i + 2, i + 4)))) { found++; console.log(`${f}:${line}: \\${d}  ${s.slice(Math.max(0, i - 30), i + 20).replace(/\n/g, '⏎')}`); }
        i += 2; continue;
      }
      if (c === '`') { st.pop(); prevSig = 'x'; i++; continue; }
      if (c === '$' && s[i + 1] === '{') { st.push('expr'); i += 2; prevSig = '{'; continue; }
      i++; continue;
    }
    i++;
  }
}
console.log(found ? `находок: ${found}` : 'чисто');
process.exit(found ? 1 : 0);
