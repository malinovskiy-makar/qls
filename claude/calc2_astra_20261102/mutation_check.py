"""Э1: реальные временные дефекты кода обязаны делать проверку красной.

Работает только с независимой calc2-astra-work. Перед каждым дефектом и
после восстановления запускает тот же тест. Исходные байты и хеши сохраняет
в локальной папке, finally восстанавливает их даже при ошибке проверки.
Не запускать одновременно с другими проверками или редактированием этих файлов.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / '.calc2-astra-local' / 'mutations-e1'
CASES = [
    ('axis-minus', '70-scenes-math.js',
     ".text(fmt(t).replace(/-/g, '−'));", '.text(fmt(t));',
     'm-transform', 'числа на холсте используют минус U+2212'),
    ('curve-clip', '70-scenes-math.js',
     "p.attr('clip-path', 'url(#' + clipId + ')');", '/* намеренная мутация: обрезка снята */',
     'm-transform', 'каждая кривая обрезается по полю'),
    ('price-tex', '92-ui-kit.js',
     "() => STATE.intervType === 'floor' ? 'P_f' : 'P_c'",
     "() => document.getElementById('pc-letter').textContent",
     'ceil', 'нет исходника или тройного текста цены'),
    ('mrs-corner', '48-scenes-consumer.js',
     "b.mrs === null ? 'не определена' : fmt(b.mrs)",
     "b.mrs === null ? '2' : fmt(b.mrs)",
     'consumer', 'MRS в изломе не определена'),
]


def run(scene, name):
    command = [sys.executable, str(ROOT / 'claude/calc2_astra_20261102/run_local.py'),
               'node', 'calc2/tests/astra_view_probe.mjs', '--scenes', scene,
               '--themes', 'light']
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
    (REPORT / (name + '.log')).write_text(result.stdout + result.stderr)
    return result


def main():
    if ROOT.name != 'calc2-astra-work':
        raise SystemExit('Только изолированная копия calc2-astra-work.')
    REPORT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, file_name, old, new, scene, expected in CASES:
        file = ROOT / 'calc2/static/calc2' / file_name
        original = file.read_bytes()
        original_hash = hashlib.sha256(original).hexdigest()
        (REPORT / (name + '.original')).write_bytes(original)
        clean = run(scene, name + '-before')
        if clean.returncode:
            raise RuntimeError(name + ': исходная проверка не зелёная')
        source = original.decode()
        if old not in source:
            raise RuntimeError(name + ': место мутации не найдено')
        try:
            file.write_text(source.replace(old, new, 1))
            broken = run(scene, name + '-broken')
            caught = broken.returncode == 1 and any(
                line.startswith('FAIL ') and expected in line for line in broken.stdout.splitlines())
            if not caught:
                raise RuntimeError(name + ': проверка не поймала нужный дефект')
        finally:
            file.write_bytes(original)
        restored = hashlib.sha256(file.read_bytes()).hexdigest() == original_hash
        after = run(scene, name + '-after')
        if not restored or after.returncode:
            raise RuntimeError(name + ': восстановление не подтверждено')
        rows.append({'mutation':name, 'caught':True, 'restored':True, 'sha256':original_hash})
        print(name + ': green → expected red → green; bytes restored', flush=True)
        (REPORT / 'results.json').write_text(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
