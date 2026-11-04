// Реальный модуль истории; часы и эффекты DOM/хранилища изолированы.
// Проверяем действия с известными интервалами, а не скорость машины CI.
import fs from 'node:fs';
import vm from 'node:vm';
let now = 0;
const listeners = {};
const ctx = vm.createContext({
  console, Date: { now: () => now }, STATE: { sceneKey: 'taxes', tax: 20 },
  document: { querySelector: () => null, addEventListener: (type, fn) => { listeners[type] = fn; } },
  window: {}, setTimeout: () => 0, clearTimeout: () => {},
  modelKeyOf: () => 'taxes',
});
vm.runInContext(`function collectModelState() { return {key:'taxes',state:{tax:STATE.tax},form:{}}; }`, ctx);
vm.runInContext(fs.readFileSync('calc2/static/calc2/91-session.js', 'utf8'), ctx);
vm.runInContext('autosaveModel=()=>{};dropShareHash=()=>{};dropFromParam=()=>{};', ctx);
const run = code => vm.runInContext(code, ctx);
const rows = [];
const check = (name, value, expected) => rows.push({ name, actual: value, expected, ok: value === expected });
for (const source of ['explicit', 'trusted-input']) {
  const act = (at, tax, label = 'tax-slider') => {
    now = at;
    if (source === 'explicit') run(`historyMark(${JSON.stringify(label)})`);
    else listeners.input({ isTrusted: true, target: { closest: () => ({ id: label }) } });
    run(`STATE.tax=${tax}`);
  };
  const commit = at => { now = at; run('historyCheck()'); };
  const count = () => run('histOf().undo.length');
  run('historyClearAll();STATE.tax=20;historyBaseline();');
  act(1000, 21); commit(1500);
  check(source + ': первый шаг', count(), 1);
  // Два следующих ввода через 505 мс; второй промежуточный снимок ещё
  // не записан из-за перерисовки. От записи к записи прошло 1040 мс.
  act(1505, 22); act(2010, 23); commit(2540);
  check(source + ': непрерывная серия при задержанной записи', count(), 1);
  check(source + ': отмена вернёт исходное значение', run('histOf().undo[0].state.tax'), 20);
  check(source + ': сохранено последнее значение серии', run('histOf().last.state.tax'), 23);
  act(4000, 24); commit(4500);
  check(source + ': пауза больше 900 мс', count(), 2);
  act(4900, 25); commit(6000);
  check(source + ': ровно 900 мс — отдельный шаг', count(), 3);
  act(6100, 26, 'other-control'); commit(6600);
  check(source + ': другой орган — отдельный шаг', count(), 4);
  act(7000, 26, 'other-control'); commit(7400); // ввод без изменения
  act(10000, 27, 'other-control'); commit(10500);
  check(source + ': старое пустое действие не склеивает новую правку', count(), 5);
}
console.log(JSON.stringify({ passed: rows.filter(r => r.ok).length, total: rows.length, failures: rows.filter(r => !r.ok) }));
process.exitCode = rows.every(r => r.ok) ? 0 : 1;
