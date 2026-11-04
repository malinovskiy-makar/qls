#!/usr/bin/env node
/* Снимки макета «Графики — редизайн» (Playwright, без сборки).

   Макет — это файлы `mockup/*.dc.html`. Они открываются в обычном браузере, если рядом лежит `support.js`
   (служебный рантайм холста) и страница отдана по http, а не открыта как файл. Этот скрипт сам поднимает
   маленький сервер над папкой `mockup/`, открывает доску в безголовом Chromium и сохраняет PNG.

   Запуск из корня репозитория (playwright берётся из node_modules репозитория):

     node claude/mockups/calc2_redesign_20261004/tools/shoot_mockup.mjs --board Work --out /tmp/work.png
     node …/shoot_mockup.mjs --main 'screen="work" model="islm" theme="dark"' --out /tmp/islm_dark.png
     node …/shoot_mockup.mjs --main 'screen="work" model="taxes" popover="export"' --size 1280x700 --out /tmp/x.png
     node …/shoot_mockup.mjs --phone 'model="sd" tab="answer"' --scale 2 --out /tmp/phone.png
     node …/shoot_mockup.mjs --all                # пересобрать весь набор reference/ (см. REFERENCE ниже)
     node …/shoot_mockup.mjs --serve              # только сервер: http://127.0.0.1:8790/Work.dc.html

   Ключи: --size ШxВ (по умолчанию из canvas.json или 1440x760), --scale N (плотность пикселей, 1),
          --clip x,y,w,h (вырезать кусок), --wait мс (пауза перед снимком, 1200), --port N (8790),
          --dir путь к папке mockup (по умолчанию ../mockup от этого файла).
   Свойства `Main` и `Phone` — раздел 1 README.md (model, theme, popover, ops, armed, hover-point, kbd, tool, demo…).
   Булево свойство пишется так: self-check="{{yes}}" (а не голым словом).
   Свой браузер: переменная PW_CHROME=/путь/к/chrome (иначе берётся Chromium из Playwright).

   Чтобы снять состояние, до которого нужно ДОЙТИ мышью (наведение, открытое меню, протяжка), поднимите сервер
   ключом --serve и пишите свой сценарий Playwright по образцу функции shot() ниже. */
import { createServer } from 'node:http';
import { readFile, writeFile, unlink, mkdir } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf('--' + name); return i >= 0 ? (args[i + 1] === undefined || args[i + 1].startsWith('--') ? true : args[i + 1]) : dflt; };
const DIR = resolve(opt('dir', join(HERE, '..', 'mockup')));
const REF = resolve(opt('ref', join(HERE, '..', 'reference')));
const PORT = +opt('port', 8790);
const WAIT = +opt('wait', 1200);

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css' };
const server = createServer(async (req, res) => {
  try {
    const name = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'Main.dc.html';
    if (name.includes('..')) { res.writeHead(403); res.end(); return; }
    const body = await readFile(join(DIR, name));
    res.writeHead(200, { 'Content-Type': MIME[extname(name)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch (e) { res.writeHead(404); res.end('нет файла'); }
});

const CANVAS = existsSync(join(DIR, 'canvas.json')) ? JSON.parse(readFileSync(join(DIR, 'canvas.json'), 'utf8')) : { boards: {} };
const boardSize = (name) => { const b = CANVAS.boards[name + '.dc.html']; return b ? [b.w, b.h] : [1440, 760]; };

/* Временная доска: тот же каркас, что у Work.dc.html, со своими атрибутами вставки. */
const tmpBoard = (comp, attrs, w, h) => `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>снимок</title>
<script src="./support.js"></script><script src="./calc-core.js"></script><script src="./calc-data.js"></script><script src="./calc-models.js"></script>
</head><body>
<x-dc>
<helmet>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,400;0,500;0,600;0,700;1,400&amp;family=STIX+Two+Text:ital,wght@0,400;0,500;0,600;1,400;1,500&amp;display=swap">
<style>body{margin:0}</style>
</helmet>
<div style="width: ${w}px; height: ${h}px; overflow: hidden; font-family: Montserrat, -apple-system, 'Segoe UI', sans-serif; color: #2d2d2d; background: #f4eed2">
<dc-import name="${comp}" ${attrs} ${comp === 'Main' && !/\bwidth=/.test(attrs) ? `width="${w}" height="${h}"` : ''} hint-size="${w}px,${h}px"></dc-import>
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":${w},"height":${h}}}'>
class Component extends DCLogic { renderVals() { return { yes: true }; } }
</script>
</body></html>
`;

let browser = null, tmpN = 0;
async function shot({ board, main, phone, size, scale = 1, clip, out, wait = WAIT, act }) {
  const { chromium } = await import('playwright');
  if (!browser) browser = await chromium.launch(process.env.PW_CHROME ? { executablePath: process.env.PW_CHROME } : {});
  let file = board ? board + '.dc.html' : null, tmp = null;
  let [w, h] = size ? size.split('x').map(Number) : (board ? boardSize(board) : (phone !== undefined ? [390, 844] : [1440, 760]));
  if (!file) {
    tmp = `_shot_tmp_${process.pid}_${++tmpN}.dc.html`;
    await writeFile(join(DIR, tmp), tmpBoard(phone !== undefined ? 'Phone' : 'Main', phone !== undefined ? phone : main, w, h));
    file = tmp;
  }
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: +scale });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e).slice(0, 300)));
  try {
    await page.goto(`http://127.0.0.1:${PORT}/${file}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(wait);
    if (act) { await act(page); await page.waitForTimeout(350); }   // состояние, до которого надо дойти мышью или клавиатурой
    await mkdir(dirname(out), { recursive: true });
    const c = clip ? clip.split(',').map(Number) : null;
    await page.screenshot({ path: out, ...(c ? { clip: { x: c[0], y: c[1], width: c[2], height: c[3] } } : {}) });
  } finally {
    await ctx.close();
    if (tmp) await unlink(join(DIR, tmp)).catch(() => {});
  }
  if (errs.length) console.log('  ошибки страницы:', errs.slice(0, 3));
  return errs.length;
}

/* ── Набор reference/: что в какой картинке. Этот же список печатается в reference/INDEX.md ── */
const LIVE = ['sd', 'taxes', 'ceil', 'mono', 'costs', 'm-tangent'];
function referenceSet() {
  const set = [];
  // 1. доски холста как есть (кроме архива отклонённых вариантов)
  Object.keys(CANVAS.boards).map((f) => f.replace('.dc.html', '')).filter((n) => !/^(KeyPointVariants|PwInline)$/.test(n))
    .forEach((n) => set.push({ out: `boards/${n}.png`, board: n, note: CANVAS.boards[n + '.dc.html'].title }));
  // 2. все 42 модели на рабочем экране, светлая тема
  const keys = modelKeys();
  keys.forEach((k) => set.push({ out: `models/${k}.png`, main: `screen="work" model="${k}"`, note: `рабочий экран модели ${k}, светлая тема, 1440×760` + (LIVE.includes(k) ? '' : ' (холст в макете — схема)') }));
  // 3. тёмная тема: живые модели и три схемных
  LIVE.concat(['islm', 'ppf', 'labor']).forEach((k) => set.push({ out: `models_dark/${k}.png`, main: `screen="work" model="${k}" theme="dark"`, note: `то же, тёмная тема` }));
  // 4. ноутбук 1280×700: живые модели
  LIVE.forEach((k) => set.push({ out: `models_1280/${k}.png`, main: `screen="work" model="${k}" width="1280" height="700"`, size: '1280x700', note: 'ширина 1280: колонки 304 и 316' }));
  // 5. состояния рабочего экрана
  const st = [
    ['selfcheck', 'screen="work" model="taxes" self-check="{{yes}}"', '«Сначала сам» включён'],
    ['selfcheck_dark', 'screen="work" model="taxes" self-check="{{yes}}" theme="dark"', '«Сначала сам», тёмная тема'],
    ['iv_subsidy', 'screen="work" model="taxes" ops="iv.instr=sub;iv.rate=20"', 'субсидия 20'],
    ['iv_vat', 'screen="work" model="taxes" ops="iv.kind=vat;iv.pct=20"', 'НДС 20 %: поворот предложения'],
    ['iv_excise', 'screen="work" model="taxes" ops="iv.kind=exc;iv.pct=20"', 'акциз 20 %'],
    ['mono_quota', 'screen="work" model="mono" ops="iv.instr=quota;iv.quota=20"', 'монополия: квота 20'],
    ['iv_buyer', 'screen="work" model="taxes" ops="iv.side=buyer"', 'налог платит покупатель'],
    ['iv_ghost', 'screen="work" model="taxes" ops="iv.ghost=true"', 'галочка «было»'],
    ['ceil_floor', 'screen="work" model="ceil" ops="iv.instr=floor;iv.price=70"', 'пол цены 70'],
    ['mono_tax', 'screen="work" model="mono" ops="iv.instr=tax;iv.ghost=true"', 'монополия: налог и «было»'],
    ['costs_loss', 'screen="work" model="costs" ops="par.P=8"', 'издержки: убыток при P = 8'],
    ['tangent_secant', 'screen="work" model="m-tangent" ops="par.secant=true;par.x0=1.5"', 'производная: секущая'],
    ['sd_qp', 'screen="work" model="sd" ops="fns.D.expr=120 - 2P"', 'спрос в форме Q(P): строка «в расчётах»'],
    ['sd_letter', 'screen="work" model="sd" ops="fns.D.expr=100 - a*Q"', 'буква в формуле стала ползунком'],
    ['sd_hidden', 'screen="work" model="sd" ops="fns.D.visible=false"', 'кривая скрыта глазом: статус в «Ответе»'],
    ['sd_extra', 'screen="work" model="sd" ops="fns.add="', 'своя функция F₁'],
    ['kp_armed', 'screen="work" model="taxes" armed="D"', 'кривая зажжена: ключевые точки с ореолом'],
    ['kp_tip', 'screen="work" model="taxes" armed="D" hover-point="kp:D:2"', 'точка под курсором: капсула с координатами и закрепкой'],
    ['kp_tip_dark', 'screen="work" model="taxes" armed="D" hover-point="kp:D:2" theme="dark"', 'то же, тёмная тема'],
    ['tool_point', 'screen="work" model="sd" tool="point"', 'инструмент «Точка»: плашка режима'],
    ['tool_area', 'screen="work" model="sd" tool="area"', 'инструмент «Площадь»: плашка режима'],
    ['marks', 'screen="work" model="sd" demo="marks"', 'своя точка и площадь на холсте и в списке'],
    ['pw_card', 'screen="work" model="taxes" ops="fns.S.pieces=0.5Q + 10||40/2Q - 50|40|"', 'кусочная функция: запись скобкой в карточке'],
    ['pw_modal', 'screen="work" model="taxes" popover="pw" pop-for="S" ops="fns.S.pieces=0.5Q + 10||40/2Q - 50|40|"', 'окно «Кусочная функция»'],
    ['pw_modal_dark', 'screen="work" model="taxes" theme="dark" popover="pw" pop-for="S" ops="fns.S.pieces=0.5Q + 10||40/2Q - 50|40|"', 'то же, тёмная тема'],
    ['kbd', 'screen="work" model="sd" kbd="sd:D"', 'клавиатура формул в карточке'],
    ['pop_switcher', 'screen="work" model="taxes" popover="switcher"', 'переключатель модели'],
    ['pop_view', 'screen="work" model="taxes" popover="view"', '«Вид графика»'],
    ['pop_share', 'screen="work" model="taxes" popover="share"', '«Поделиться»'],
    ['pop_export', 'screen="work" model="taxes" popover="export"', '«Скачать»'],
    ['pop_help', 'screen="work" model="taxes" popover="help"', '«Как писать формулы»'],
    ['pop_more', 'screen="work" model="sd" popover="more" pop-for="D"', 'меню «…» карточки функции'],
    ['pop_more_extra', 'screen="work" model="sd" ops="fns.add=" popover="more" pop-for="F1"', 'меню «…» своей функции: «Роль кривой», «Удалить функцию»'],
    ['pop_color', 'screen="work" model="sd" popover="color" pop-for="D"', '«Цвет кривой»'],
    ['picker', 'screen="picker"', 'экран выбора модели'],
    ['picker_dark', 'screen="picker" theme="dark"', 'экран выбора, тёмная тема'],
    ['picker_search', 'screen="picker" search="налог"', 'поиск «налог»'],
    ['picker_search_none', 'screen="picker" search="зззз"', 'поиск без находок'],
    ['palette_alt', 'screen="work" model="taxes" palette="alt"', 'другая палитра сайта при той же разметке'],
  ];
  st.forEach(([n, a, note]) => set.push({ out: `states/${n}.png`, main: a, note }));
  // 5а. состояния, до которых надо дойти действием (act выполняется после загрузки доски)
  const work = 'screen="work" model="sd"', taxes = 'screen="work" model="taxes"';
  set.push({ out: 'states/sd_error.png', main: work, note: 'ошибка в формуле: поле красное, текст ошибки, график и ответ держат последнюю верную запись',
    how: 'в поле «Формула: Спрос» набрано «100 - »',
    act: async (pg) => { await pg.fill('input[aria-label="Формула: Спрос"]', '100 - '); } });
  set.push({ out: 'states/fn_focus.png', main: work, note: 'поле формулы в фокусе: при наборе показано ровно набранное',
    how: 'щелчок в поле «Формула: Спрос»',
    act: async (pg) => { await pg.click('input[aria-label="Формула: Спрос"]'); } });
  set.push({ out: 'states/toast_reset.png', main: 'screen="work" model="taxes" ops="iv.rate=45"', note: 'после «Сбросить»: тост с действием «Вернуть»',
    how: 'нажато «Сбросить»',
    act: async (pg) => { await pg.getByRole('button', { name: 'Сбросить' }).click(); } });
  set.push({ out: 'states/undo_enabled.png', main: taxes, note: 'после правки: «Отменить» активна, статус сохранения',
    how: 'в поле «Формула: Спрос» набрано «90 - Q»',
    act: async (pg) => { await pg.fill('input[aria-label="Формула: Спрос"]', '90 - Q'); await pg.keyboard.press('Tab'); } });
  set.push({ out: 'states/selfcheck_verdicts.png', main: 'screen="work" model="taxes" self-check="{{yes}}"', note: '«Сначала сам»: один ответ верный, один нет',
    how: 'в первую ячейку введено 35, во вторую 99, нажато «Проверить»',
    act: async (pg) => {
      const inp = pg.locator('input[aria-label^="Ваш ответ"]');
      await inp.nth(0).fill('35'); await inp.nth(1).fill('99');
      const btn = pg.getByRole('button', { name: 'Проверить' });
      const n = await btn.count(); for (let i = 0; i < Math.min(n, 2); i++) await btn.nth(i).click();
    } });
  set.push({ out: 'states/picker_preview.png', main: 'screen="picker"', note: 'экран выбора: превью модели при наведении на строку',
    how: 'курсор на строке «Стандартная монополия»',
    act: async (pg) => { await pg.getByRole('button', { name: 'Стандартная монополия', exact: true }).first().hover(); } });
  set.push({ out: 'states/kp_pinned.png', main: 'screen="work" model="taxes" armed="D" hover-point="kp:D:2"', note: 'после закрепки: тост, своя точка на холсте и в списке',
    how: 'щелчок по значку закрепки в капсуле',
    act: async (pg) => { await pg.locator('svg g[style*="cursor: pointer"] rect[rx="6"]').first().click({ force: true }); } });
  set.push({ out: 'states/focus_mode.png', main: taxes, note: '«Развернуть график»: колонки спрятаны',
    how: 'нажата кнопка разворота в панели холста',
    act: async (pg) => { await pg.locator('button[aria-label="Развернуть график"]').first().click(); } });
  // 6. крупные планы (плотность 3): ключевая точка, карточка функции, главные числа
  set.push({ out: 'details/kp_capsule_light.png', main: 'screen="work" model="taxes" armed="D" hover-point="kp:D:2"', scale: 3, clip: '560,330,330,230', note: 'капсула и точки крупно, светлая тема' });
  set.push({ out: 'details/kp_capsule_dark.png', main: 'screen="work" model="taxes" armed="D" hover-point="kp:D:2" theme="dark"', scale: 3, clip: '560,330,330,230', note: 'капсула и точки крупно, тёмная тема' });
  set.push({ out: 'details/left_column.png', main: 'screen="work" model="taxes"', scale: 2, clip: '0,104,337,656', note: 'колонка «Условие» крупно' });
  set.push({ out: 'details/right_column.png', main: 'screen="work" model="taxes"', scale: 2, clip: '1091,104,349,656', note: 'колонка «Ответ» крупно' });
  set.push({ out: 'details/header.png', main: 'screen="work" model="taxes"', scale: 2, clip: '0,0,1440,104', note: 'шапка сайта и шапка модели крупно' });
  set.push({ out: 'details/canvas_toolbar.png', main: 'screen="work" model="taxes"', scale: 2, clip: '337,104,754,60', note: 'панель холста крупно' });
  set.push({ out: 'details/pw_record.png', main: 'screen="work" model="taxes" ops="fns.S.pieces=0.5Q + 10||40/2Q - 50|40|"', scale: 3, clip: '0,104,337,420', note: 'запись скобкой в карточке крупно' });
  // 7. телефон
  ['taxes', 'sd', 'mono', 'costs', 'm-tangent', 'islm'].forEach((k) => ['left', 'answer', 'explain'].forEach((t) =>
    set.push({ out: `phone/${k}_${t}.png`, phone: `model="${k}" tab="${t}"`, scale: 2, note: `телефон 390×844, модель ${k}, вкладка ${t}` })));
  set.push({ out: 'phone/taxes_dark.png', phone: 'model="taxes" theme="dark"', scale: 2, note: 'телефон, тёмная тема' });
  set.push({ out: 'phone/kp_capsule.png', phone: 'model="sd" hover-point="kp:D:2"', scale: 2, note: 'телефон: ключевая точка, капсула без закрепки' });
  set.push({ out: 'phone/pw_card.png', phone: 'model="sd" ops="fns.D.pieces=100 - 2Q||20/80 - Q|20|"', scale: 2, note: 'телефон: запись скобкой в карточке' });
  set.push({ out: 'phone/pw_sheet.png', phone: 'model="sd" ops="fns.D.pieces=100 - 2Q||20/80 - Q|20|" pw-for="D"', scale: 2, note: 'телефон: лист «Кусочная функция»' });
  set.push({ out: 'phone/sheet_more.png', phone: 'model="taxes" sheet="more"', scale: 2, note: 'телефон: лист «Действия»' });
  set.push({ out: 'phone/sheet_help.png', phone: 'model="taxes" sheet="help"', scale: 2, note: 'телефон: «Как писать формулы»' });
  return set;
}
function modelKeys() {
  // ключи 42 рабочих моделей — из calc-data.js, в порядке экрана выбора
  const src = readFileSync(join(DIR, 'calc-data.js'), 'utf8');
  const out = [];
  for (const m of src.matchAll(/\{"k":"([a-z0-9-]+)","b":"[^"]+","n":"[^"]+","ds":"[^"]*","soon":(true|false)/g)) if (m[2] === 'false') out.push(m[1]);
  return out;
}

await new Promise((ok) => server.listen(PORT, '127.0.0.1', ok));
try {
  if (opt('serve', false)) {
    console.log(`макет: http://127.0.0.1:${PORT}/Main.dc.html (папка ${DIR}); остановить: Ctrl+C`);
    await new Promise(() => {});
  } else if (opt('all', false)) {
    const set = referenceSet();
    let bad = 0;
    const lines = ['# Эталонные снимки макета', '', 'Пересобрать: `node tools/shoot_mockup.mjs --all`. Каждая строка: файл, как получено состояние, что на картинке.', '', '| Файл | Состояние макета | Что на картинке |', '|---|---|---|'];
    for (const it of set) {
      process.stdout.write(it.out + '\n');
      bad += await shot({ ...it, out: join(REF, it.out) }) ? 1 : 0;
      const how = (it.board ? `доска \`${it.board}.dc.html\`` : (it.phone !== undefined ? `\`Phone\`: \`${it.phone}\`` : `\`Main\`: \`${it.main}\``)) + (it.how ? `; затем: ${it.how}` : '');
      lines.push(`| \`${it.out}\` | ${how}${it.scale ? `, плотность ${it.scale}` : ''}${it.clip ? `, вырез ${it.clip}` : ''} | ${it.note || ''} |`);
    }
    await writeFile(join(REF, 'INDEX.md'), lines.join('\n') + '\n');
    console.log(`готово: ${set.length} снимков, с ошибками страницы: ${bad}`);
  } else {
    const out = opt('out', null);
    if (!out) { console.log('нужен --out путь.png (или --all, или --serve)'); process.exitCode = 2; }
    else {
      const bad = await shot({ board: opt('board', null), main: opt('main', undefined), phone: opt('phone', undefined), size: opt('size', null), scale: opt('scale', 1), clip: opt('clip', null), out: resolve(out) });
      console.log('снимок:', resolve(out), bad ? '(были ошибки страницы)' : '');
    }
  }
} finally {
  if (browser) await browser.close();
  server.close();
}
