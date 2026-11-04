// M01–M03 изменили производные данные, но не стартовые входы моделей.
// Старые JSON сохраняем. Новые поля сверяем с аналитикой, а не принимаем
// любое отличие от снимка. Остальные поля STATE проверяет session_probe.
export function auditStartCheck(key, state, previous) {
  const near = (a, b) => Number.isFinite(a) && Math.abs(a - b) < 1e-6;
  if (key === 'laffer') {
    const r = state.macroRes, points = r?.pts;
    // D=100-Q, S=Q: Q=(100-t)/2, T=t(100-t)/2, максимум (50,1250).
    return { fields: ['macroRes'], ok: r?.kind === 'laffer'
      && near(r.stop, 100) && near(r.tMax, 100)
      && near(r.best?.t, 50) && near(r.best?.Q, 25) && near(r.best?.rev, 1250)
      && Array.isArray(points) && points.length > 2
      && near(points[0][0], 0) && near(points.at(-1)[0], 100)
      && points.every(([t, revenue], i) => t >= 0 && t <= 100
        && (!i || t >= points[i - 1][0]) && near(revenue, t * (100 - t) / 2)) };
  }
  if (key === 'm-constraint') {
    const r = state.mathRes, fit = state.consFit;
    const expectedFit = { xMin: -4.1, xMax: 14.1, yMin: -4.1, yMax: 14.1 };
    const sameFit = f => f && Object.keys(f).length === 4
      && Object.entries(expectedFit).every(([k, v]) => near(f[k], v));
    const points = r?.conPts, branches = r?.conBranches;
    // sqrt(xy) при x+y=10: максимум 5 в (5,5). M02 хранит всю
    // связанную прямую в расширенном окне, включая отрицательные координаты.
    return { fields: ['consFit', 'mathRes', 'mathXmin', 'mathXmax', 'mathYmin', 'mathYmax'],
      ok: sameFit(fit) && sameFit(r?.fit)
      && Object.entries(expectedFit).every(([k, v]) => near(state['math' + k[0].toUpperCase() + k.slice(1).toLowerCase()], v))
      && r?.wantMax === true && r.touchesEdge === false
      && near(r.opt?.a, 5) && near(r.opt?.b, 5) && near(r.opt?.value, 5)
      && Array.isArray(points) && points.length > 2
      && Array.isArray(branches) && branches.length === 1
      && JSON.stringify(branches[0]) === JSON.stringify(points)
      && near(points[0][0], -4.1) && near(points.at(-1)[0], 14.1)
      && points.every(([x, y]) => near(x + y, 10) && x >= -4.1 && x <= 14.1 && y >= -4.1 && y <= 14.1) };
  }
  if (key === 'tradeprice') {
    const actual = { ...state.tradeBData };
    delete actual.atBoundary;
    // M01/E01 добавляет признак граничной цены. sqrt(1*2) строго внутри
    // [1,2]; все прежние результаты, включая каждую точку, неизменны.
    return { fields: ['tradeBData'], ok: state.tradeBData?.atBoundary === false
      && JSON.stringify(actual) === JSON.stringify(previous.tradeBData) };
  }
  return null;
}
