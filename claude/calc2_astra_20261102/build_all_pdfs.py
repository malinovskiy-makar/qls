"""Сохранить все 48 реальных TeX/PDF из финального обхода калькулятора."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def runtime_fingerprints():
    names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'calc2/static',
                                    'calc2/templates', 'calc2/templatetags', 'calc2/views.py'], cwd=ROOT)
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names.decode().split('\0') if name}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='all-models-v5')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]+', args.label):
        raise SystemExit('Недопустимое имя комплекта.')
    if (ROOT / '.env').exists() or os.environ.get('DJANGO_SETTINGS_MODULE') != 'claude.calc2_astra_20261102.settings_local':
        raise SystemExit('Запускать только через собственный run_local.py python.')
    out = ROOT / '.calc2-astra-local/final-exports' / args.label
    texdir = out / 'tex'
    texdir.mkdir(parents=True, exist_ok=False)
    pdfdir = out / 'pdf'
    pdfdir.mkdir()
    env = dict(os.environ, OUT=str(texdir))
    with (out / 'export.log').open('w') as stream:
        code = subprocess.call([shutil.which('node'), 'calc2/tests/tex/ci_quick.mjs'],
                               cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if code:
        raise SystemExit(f'Обход TeX завершился с кодом {code}; см. export.log.')
    files = sorted(texdir.glob('*.tex'))
    if len(files) != 48:
        raise SystemExit(f'Ожидалось 48 файлов, получено {len(files)}.')
    import django
    django.setup()
    from calc2.templatetags.calc2_static import calc2_static_version
    from calc2.views import compile_pdf_pdflatex

    def build(file):
        source = file.read_bytes()
        pdf, error = compile_pdf_pdflatex(source.decode('utf-8'))
        if not pdf or not pdf.startswith(b'%PDF'):
            (out / (file.stem + '.error.txt')).write_text(error or 'Пустой PDF')
            return {'name': file.stem, 'ok': False}
        target = pdfdir / (file.stem + '.pdf')
        target.write_bytes(pdf)
        info = subprocess.check_output(['/opt/homebrew/bin/pdfinfo', str(target)], text=True)
        pages = int(re.search(r'^Pages:\s+(\d+)', info, re.M).group(1))
        return {'name': file.stem, 'ok': True, 'pages': pages, 'bytes': len(pdf),
                'tex_sha256': hashlib.sha256(source).hexdigest(),
                'pdf_sha256': hashlib.sha256(pdf).hexdigest()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(build, files))
    result = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'worktree_dirty_at_generation': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
              'runtime_sources_sha256': runtime_fingerprints(),
              'static_version': calc2_static_version(), 'files': rows,
              'passed': sum(r['ok'] for r in rows), 'total': len(rows)}
    (out / 'MANIFEST.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'directory': str(out), 'passed': result['passed'], 'total': len(rows),
                      'pages': sum(r.get('pages', 0) for r in rows)}, ensure_ascii=False), flush=True)
    return int(result['passed'] != 48)


if __name__ == '__main__':
    sys.exit(main())
