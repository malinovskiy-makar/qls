/* Приборы выгрузки .tex: что выполняется внутри страницы /calc2/.
   Подключается приборами (addScriptTag) после загрузки страницы и, если
   выбран прототип, после него (proto/texproto.js пакета задания).

   Здесь три вещи:
     1) переходник к сборщику: «бумажный прогон → опись → сборка» и дверь
        buildTex(title, label) — у прототипа (TXP) и у сайта одинаково;
     2) замер «выгрузка ничего не трогает»: состояние модели, узлы холста,
        стек «Отменить», localStorage, события calc2:changing и calc2:history;
     3) счёт того, что видно на листе (для сверки с описью и с файлом).

   Ничего в сайте не меняет: только читает и зовёт его функции. */
(function () {
  'use strict';

  /* ── 1. Переходник ─────────────────────────────────────────────────── */
  function engine(kind) {
    if (kind === 'proto') {
      if (typeof TXP !== 'object') throw new Error('прототип не подключён');
      return {
        kind: 'proto',
        enterPaper: () => TXP.enterPaper(),
        capture: () => TXP.capture(),
        emit: (list, o) => TXP.emit(list, o || {}),
        door: (title, label) => TXP.build({ title: title || '', label: label || '' }).tex,
      };
    }
    if (typeof texEnterPaper !== 'function' || typeof texCapture !== 'function' || typeof texEmit !== 'function') {
      throw new Error('на странице нет новой выгрузки (texEnterPaper, texCapture, texEmit)');
    }
    return {
      kind: 'site',
      enterPaper: () => texEnterPaper(),
      capture: () => texCapture(),
      emit: (list, o) => texEmit(list, o || {}),
      door: (title, label) => buildTex(title || '', label || ''),
    };
  }

  /* ── 2. Замеры «ничего не трогает» ─────────────────────────────────── */
  const flat = (o, pre, out) => {
    if (o && typeof o === 'object') Object.keys(o).forEach(k => flat(o[k], pre ? pre + '.' + k : k, out));
    else out[pre] = o;
    return out;
  };
  // У STATE.crosses шум в последнем знаке (численный поиск пересечений): допуск 1e-6.
  function stateFlat() { return flat(collectModelState(), '', {}); }
  function stateDiff(a, b) {
    const diff = [];
    new Set([...Object.keys(a), ...Object.keys(b)]).forEach(k => {
      if (JSON.stringify(a[k]) === JSON.stringify(b[k])) return;
      const num = typeof a[k] === 'number' && typeof b[k] === 'number';
      if (num && Math.abs(a[k] - b[k]) <= 1e-6 * Math.max(1, Math.abs(a[k]))) return;
      diff.push(k + ': ' + JSON.stringify(a[k]) + ' → ' + JSON.stringify(b[k]));
    });
    return diff;
  }
  function domSnap() {
    const rows = [];
    document.getElementById('chart').querySelectorAll('*').forEach(e => {
      const a = {}; for (const at of e.attributes) a[at.name] = at.value;
      rows.push([e.tagName, a, e.children.length ? '' : (e.textContent || '')]);
    });
    return rows;
  }
  // Узлы холста те же: теги, атрибуты, тексты; числа в атрибутах — с точностью до 0,5 px.
  function domCompare(d0, d1) {
    const num = /-?\d+\.?\d*(?:e-?\d+)?/g;
    if (d0.length !== d1.length) return { same: false, maxDelta: null, why: 'узлов ' + d0.length + ' → ' + d1.length };
    let maxDelta = 0;
    for (let i = 0; i < d0.length; i++) {
      const [g0, a0, x0] = d0[i], [g1, a1, x1] = d1[i];
      if (g0 !== g1 || x0 !== x1 || Object.keys(a0).length !== Object.keys(a1).length) return { same: false, maxDelta, why: 'узел ' + i + ' ' + g0 + ' ' + JSON.stringify(x0).slice(0, 40) + ' → ' + g1 + ' ' + JSON.stringify(x1).slice(0, 40) };
      for (const k of Object.keys(a0)) {
        if (a0[k] === a1[k]) continue;
        const n0 = (String(a0[k]).match(num) || []).map(Number), n1 = (String(a1[k]).match(num) || []).map(Number);
        if (String(a0[k]).replace(num, '#') !== String(a1[k]).replace(num, '#') || n0.length !== n1.length) return { same: false, maxDelta, why: 'узел ' + i + ' ' + g0 + ' атрибут ' + k };
        n0.forEach((q, j) => { maxDelta = Math.max(maxDelta, Math.abs(q - n1[j])); });
      }
    }
    return { same: maxDelta <= 0.5, maxDelta, why: maxDelta > 0.5 ? 'сдвиг ' + maxDelta.toFixed(3) + ' px' : '' };
  }
  function histSnap() {
    let undo = null, redo = null;
    try { const h = (typeof _hist === 'object' && STATE.sceneKey) ? _hist[modelKeyOf()] : null; undo = h ? h.undo.length : 0; redo = h ? h.redo.length : 0; } catch (e) {}
    const ls = {};
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); ls[k] = localStorage.getItem(k); } } catch (e) {}
    return { undo, redo, ls: JSON.stringify(ls) };
  }
  const EVENTS = ['calc2:changing', 'calc2:history'];
  function listen() {
    const got = { 'calc2:changing': 0, 'calc2:history': 0 };
    const fns = EVENTS.map(n => { const f = () => { got[n]++; }; window.addEventListener(n, f); return [n, f]; });
    return { got, stop: () => fns.forEach(([n, f]) => window.removeEventListener(n, f)) };
  }

  /* ── 3. Что видно на листе ─────────────────────────────────────────── */
  /* Счёт идёт по холсту на бумажном прогоне, независимо от описи: что
     человек увидит на листе. Служебное (data-service, data-skip-export) и
     невидимое не считается. */
  function visibleOnSheet() {
    const chart = document.getElementById('chart');
    const Wc = +chart.getAttribute('width') || chart.clientWidth, Hc = +chart.getAttribute('height') || chart.clientHeight;
    const out = { texts: 0, lines: 0, axisLines: 0, gridLines: 0, dots: 0, legendRows: 0, paths: 0, rects: 0 };
    const hidden = (el) => {
      // кружок своей точки — сама точка, хоть его и тянут мышью (как в описи выгрузки)
      const own = el.tagName === 'circle' && el.parentNode && el.parentNode.classList && el.parentNode.classList.contains('marks');
      for (let n = el; n && n !== chart && !own; n = n.parentNode) {
        if (n.getAttribute && (n.getAttribute('data-service') || n.getAttribute('data-skip-export'))) return true;
      }
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return true;
      let o = 1; for (let n = el; n && n !== chart && n.nodeType === 1; n = n.parentNode) { const v = parseFloat(getComputedStyle(n).opacity); if (isFinite(v)) o *= v; }
      if (o < 0.02) return true;
      const r = el.getBoundingClientRect();
      if (!(r.width > 0.5 || r.height > 0.5)) return true;
      // подпись, срезанная окном обрезки своей группы (по центру рамки), не видна — как в описи выгрузки
      if (el.tagName === 'text') {
        let cp = null;
        for (let n = el; n && n !== chart && !cp; n = n.parentNode) {
          const a = n.getAttribute && n.getAttribute('clip-path'), m = a && /url\(["']?#([^)"']+)/.exec(a);
          if (m) cp = m[1];
        }
        const rr = cp && chart.querySelector('clipPath#' + CSS.escape(cp) + ' rect');
        if (rr) {
          const b = el.getBBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2;
          const x = +rr.getAttribute('x'), y = +rr.getAttribute('y'), w = +rr.getAttribute('width'), h = +rr.getAttribute('height');
          if (cx < x || cx > x + w || cy < y || cy > y + h) return true;
        }
      }
      // целиком за краем холста: на экране его срезает сам SVG
      return r.right < box.left - 0.5 || r.left > box.right + 0.5 || r.bottom < box.top - 0.5 || r.top > box.bottom + 0.5;
    };
    const box = chart.getBoundingClientRect();
    const legend = chart.querySelector('g.legend');
    chart.querySelectorAll('text').forEach(t => {
      if (t.closest('defs') || hidden(t)) return;
      if (!(t.textContent || '').replace(/​/g, '').trim()) return;
      if (legend && legend.contains(t)) { out.legendRows++; return; }
      const bb = t.getBBox(); if (bb.x + bb.width < 0 || bb.x > Wc || bb.y + bb.height < 0 || bb.y > Hc) return;
      out.texts++;
    });
    chart.querySelectorAll('line').forEach(l => {
      if (l.closest('defs') || (legend && legend.contains(l)) || hidden(l)) return;
      if (l.closest('g.grid')) { out.gridLines++; return; }
      if (l.getAttribute('marker-end')) { out.axisLines++; return; }
      out.lines++;
    });
    chart.querySelectorAll('circle').forEach(c => { if (!c.closest('defs') && !(legend && legend.contains(c)) && !hidden(c)) out.dots++; });
    chart.querySelectorAll('path').forEach(p => { if (!p.closest('defs') && !(legend && legend.contains(p)) && !hidden(p)) out.paths++; });
    chart.querySelectorAll('rect').forEach(r => { if (!r.closest('defs') && !r.closest('clipPath') && !(legend && legend.contains(r)) && !hidden(r)) out.rects++; });
    /* «Сначала сам»: число, спрятанное на холсте, не должно жить в разметке
       подписи (data-raw) — из неё выгрузка берёт текст. Сравниваются цифры
       разметки и видимого текста (подстрочные цифры видимого — как обычные). */
    out.selfLeak = 0;
    if (typeof selfMasked === 'function' && selfMasked()) {
      const SUB = { '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9' };
      const digits = (x) => (String(x).replace(/[₀-₉]/g, c => SUB[c]).match(/\d/g) || []).join('');
      chart.querySelectorAll('text[data-raw]').forEach(t => {
        if (hidden(t)) return;
        const k = t.cloneNode(true); k.querySelectorAll('title,desc').forEach(n => n.remove());
        if (digits(t.getAttribute('data-raw')) !== digits(k.textContent)) out.selfLeak++;
      });
    }
    return out;
  }

  /* ── Сводный замер одного состояния ─────────────────────────────────── */
  /* opts: { engine, title, label, shot } — shot: остановиться на листе и
     дождаться снимка (prev → сделать снимок снаружи → resume). Для простоты
     снимок делает прибор между двумя вызовами: auditBegin() и auditEnd(). */
  let pending = null;
  /* Экран в неподвижной точке: две перерисовки подряд (поля холста
     досчитываются вторым кадром). Прибор после этого ждёт затишья истории
     (300 мс), и только потом зовёт auditBegin: иначе таймер истории от
     собственных перерисовок прибора сработал бы посреди замера. */
  function prepare() { redrawAll(); redrawAll(); return true; }
  function auditBegin(opts) {
    const E = engine(opts.engine);
    pending = { E, opts, s0: stateFlat(), d0: domSnap(), h0: histSnap() };
    pending.ev = listen();
    const t0 = performance.now();
    pending.leave = E.enterPaper();
    pending.tPaper = performance.now() - t0;
    /* Опись снимается в той же задаче браузера, что и прогон, как у двери:
       между ними прибор не уступает ход (снимок листа — после описи), иначе
       таймеры страницы успели бы сдвинуть подписи и файл разошёлся бы с дверью. */
    try { pending.seen = visibleOnSheet(); pending.list = E.capture(); }
    catch (e) { pending.leave(); pending.ev.stop(); pending = null; throw e; }
    pending.tCap = performance.now() - t0 - pending.tPaper;
    return { ok: true };
  }
  function auditEnd() {
    const P = pending; pending = null;
    if (!P) throw new Error('auditEnd без auditBegin');
    const { E, opts } = P;
    const list = P.list;
    P.leave();
    const t1 = performance.now();
    const res = E.emit(list, { title: opts.title || '', label: opts.label || '' });
    const tEmit = performance.now() - t1;
    // настоящая дверь: то, что получает кнопка «Скачать»
    const t2 = performance.now();
    const door = E.door(opts.title || '', opts.label || '');
    const tDoor = performance.now() - t2;
    const door2 = E.door(opts.title || '', opts.label || '');
    P.ev.stop();
    // формулы файла и пробные точки движка (сверка настоящим pgfmath), тексты подписей
    const formulas = [], labels = [];
    (list.panels || []).forEach(p => (p.items || []).forEach(it => {
      if (it.kind === 'path') {
        const r = it.rec;
        if (r && r.ok && r.pgf && r.probe) formulas.push({ pgf: r.pgf, v: r.axis === 'y' ? 't' : 'x', probe: r.probe, span: r.span });
        const a = it.area;
        if (a && a.ok) ['lo', 'hi'].forEach(s => { if (a[s] && a[s].pgf && a[s].probe) formulas.push({ pgf: a[s].pgf, v: 'x', probe: a[s].probe, span: a.span }); });
      }
      if (it.kind === 'text') labels.push({ raw: it.raw, tex: it.tex });
    }));
    (list.panels || []).forEach(p => {
      const ax = p.ax || {};
      (ax.xt || []).concat(ax.yt || []).forEach(t => { if (t.raw) labels.push({ raw: t.raw, tex: t.tex }); });
      [ax.xName, ax.yName].forEach(t => { if (t) labels.push({ raw: t.raw, tex: t.tex }); });
      if (p.legend) p.legend.rows.forEach(r => labels.push({ raw: r.raw, tex: r.tex }));
    });
    // разбор путей: что ушло запасным путём и почему (для отчёта)
    const fallback = [];
    (list.panels || []).forEach(p => (p.items || []).forEach(it => {
      if (it.kind !== 'path') return;
      const isCurve = !!it.st && !it.fl, isArea = !!it.fl;
      const bad = (it.rec && !it.rec.ok) || (it.area && !it.area.ok);
      const noRec = !it.rec && !it.area && !it.nodes;
      const numeric = it.nodes && it.nodes.kind === 'numeric';
      if (bad || (noRec && isCurve) || (noRec && isArea && it.shape === 'sampled') || numeric || (it.nodes && it.nodes.kind === 'poly')) {
        fallback.push({ panel: p.id, what: isArea ? 'область' : 'кривая', name: (it.rec && it.rec.name) || (it.nodes && it.nodes.name) || it.legend || '', cls: it.pcls || it.cls || '',
          kind: bad ? 'не сошлась' : numeric ? 'узлы расчёта' : (it.nodes ? 'ломаная' : (it.shape === 'poly' ? 'без записи: ломаная' : 'без записи: отсчёты')),
          why: (it.rec && it.rec.why) || (it.area && it.area.why) || (it.nodes && it.nodes.why) || '', n: it.pts ? it.pts.length : 0 });
      }
    }));
    const settleAfter = { s1: stateFlat(), d1: domSnap() };
    return {
      tex: res.tex, stats: res.stats, warn: list.warn || [], size: [list.W, list.H],
      doorSame: door === res.tex, repeatSame: door === door2,
      ms: { paper: Math.round(P.tPaper), capture: Math.round(P.tCap), emit: Math.round(tEmit), door: Math.round(tDoor) },
      seen: P.seen, formulas, labels, fallback,
      stateDiff: stateDiff(P.s0, settleAfter.s1).slice(0, 12),
      dom: domCompare(P.d0, settleAfter.d1),
      events: Object.assign({}, P.ev.got), h0: P.h0,
      self: !!(typeof SELF === 'object' && SELF.on && !SELF.all),
      list: opts.keepList ? JSON.parse(JSON.stringify(list, (k, v) => (typeof v === 'function' ? undefined : v))) : null,
    };
  }
  // История и хранилище — после затишья (дребезг истории 300 мс): вызывается прибором позже.
  function histAfter(h0) {
    const h1 = histSnap();
    return { undo: [h0.undo, h1.undo], redo: [h0.redo, h1.redo], lsSame: h0.ls === h1.ls };
  }

  window.__TXA = { engine, prepare, auditBegin, auditEnd, histAfter, histSnap, stateFlat, stateDiff, domSnap, domCompare, visibleOnSheet, listen };
})();
