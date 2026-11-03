"""Save the audit-fix result locally, then verify code and artifact recovery."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from claude.calc2_astra_20261102.checkpoint import verify_restore

ACTIVE = Path('/private/tmp/calc2-fixes-active-20261103')
DEST = Path('/Users/makarmalinovskiy/Documents/ChatGPT/Weconomics/calc2-fixes-20261103-final')
EXPORTS = ROOT / '.calc2-astra-local/final-exports/audit-fixes-final-v3-20261103'
BASE = '15bd4a4b6955b3aa59f6abe9f557671e81fac363'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT):
        raise SystemExit('Commit only the owned changes before saving.')
    if subprocess.check_output(['git', 'remote'], cwd=ROOT):
        raise SystemExit('Unexpected remote.')
    pdfs = json.loads((EXPORTS / 'MANIFEST.json').read_text())
    assert pdfs['passed'] == pdfs['total'] == 48
    assert len(list((EXPORTS / 'pdf').glob('*.pdf'))) == 48
    assert len(list((EXPORTS / 'tex').glob('*.tex'))) == 48
    for name, expected in pdfs['runtime_sources_sha256'].items():
        assert digest(ROOT / name) == expected, name
    for row in pdfs['files']:
        assert row['ok'] and row['pages'] == 1
        for ext in ('pdf', 'tex'):
            assert digest(EXPORTS / ext / (row['name'] + '.' + ext)) == row[ext + '_sha256']
    DEST.mkdir(exist_ok=False)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'symbolic-ref', 'HEAD'], cwd=ROOT, text=True).strip()
    bundle = DEST / 'work.bundle'
    subprocess.run(['git', 'bundle', 'create', str(bundle), 'HEAD', branch], cwd=ROOT, check=True)
    subprocess.run(['git', 'bundle', 'verify', str(bundle)], cwd=ROOT, check=True)
    with (DEST / 'changes.patch').open('wb') as stream:
        subprocess.run(['git', 'diff', '--binary', BASE, head], cwd=ROOT, stdout=stream, check=True)
    own = Path(__file__).parent
    for name in ('REPORT.md', 'HANDOFF.md', 'CI_FINDINGS.md', 'JOURNAL.md', 'PLAN.md'):
        shutil.copy2(own / name, DEST / name)
    for name in ('screenshots', 'evidence', 'ci'):
        shutil.copytree(ACTIVE / name, DEST / name)
    for ext, folder in [('pdf', 'PDF'), ('tex', 'TeX'), ('rendered', 'PDF_rendered'), ('qa', 'PDF_QA')]:
        shutil.copytree(EXPORTS / ext, DEST / folder)
    shutil.copy2(EXPORTS / 'MANIFEST.json', DEST / 'PDF_MANIFEST.json')
    shutil.copy2(ACTIVE / 'evidence/SOURCES.json', DEST / 'SOURCES.json')
    if (ACTIVE / 'evidence/NOTION.json').exists():
        shutil.copy2(ACTIVE / 'evidence/NOTION.json', DEST / 'NOTION.json')
    index = ['# 48 PDF и исходников TeX', '',
             '44 модели, два налоговых псевдонима и два специальных состояния.', '',
             '| Модель / состояние | PDF | TeX |', '| --- | --- | --- |']
    for row in pdfs['files']:
        n = row['name']
        index.append(f'| {n} | [PDF](PDF/{n}.pdf) | [TeX](TeX/{n}.tex) |')
    (DEST / 'PDF_INDEX.md').write_text('\n'.join(index) + '\n')
    figures = []
    for image in sorted((DEST / 'screenshots').glob('*.jpg')):
        note = 'Не засчитано: DOM-адаптер не применил ввод к модели.' if image.stem.startswith('input-adapter') else image.stem
        figures.append(f'<figure><a href="screenshots/{image.name}"><img loading="lazy" src="screenshots/{image.name}"></a><figcaption>{html.escape(note)}</figcaption></figure>')
    gallery = ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>Исправления графиков · доказательства</title><style>body{font:16px system-ui;margin:24px;background:#f5f4ef;color:#262620}'
               'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}figure{margin:0;padding:12px;background:white}'
               'img{width:100%;height:420px;object-fit:contain}figcaption{padding-top:10px;overflow-wrap:anywhere}</style>'
               '<h1>Исправления графиков</h1><p>На проверке. M01–M03 и E01–E08; визуальные V01–V05 остаются открытыми.</p>'
               '<p>Нажмите на снимок, чтобы открыть оригинал. Полный итог: REPORT.md; PDF: PDF_INDEX.md.</p><main>'
               + ''.join(figures) + '</main></html>')
    (DEST / 'gallery.html').write_text(gallery)
    (DEST / 'README.md').write_text(
        '# Итоговый комплект исправлений\n\n'
        'Статус: на проверке у Макара. Исправлены M01–M03 и E01–E08; V01–V05 ожидают обсуждения.\n\n'
        '- [Итог](REPORT.md)\n- [Снимки](gallery.html)\n- [48 PDF](PDF_INDEX.md)\n'
        '- [Общий CI и старый долг](CI_FINDINGS.md)\n- [Продолжение и восстановление](HANDOFF.md)\n\n'
        f'Коммит `{head}`. Полная локальная история: work.bundle. GitHub, тренажёр и прод не изменялись.\n')
    verify_restore(bundle, head, DEST)
    rows = [{'file': str(p.relative_to(DEST)), 'bytes': p.stat().st_size, 'sha256': digest(p)}
            for p in sorted(DEST.rglob('*')) if p.is_file()]
    manifest = {'head': head, 'base': BASE, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'runtime_matches_pdf_manifest': True, 'status': 'На проверке', 'files': rows}
    (DEST / 'SHA256_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    for row in rows:
        assert digest(DEST / row['file']) == row['sha256']
    archive = DEST.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DEST.rglob('*')):
            if p.is_file():
                z.write(p, str(Path(DEST.name) / p.relative_to(DEST)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    archive.with_suffix('.zip.sha256').write_text(digest(archive) + '  ' + archive.name + '\n')
    print(json.dumps({'directory': str(DEST), 'head': head, 'files': len(rows) + 1,
                      'zip': str(archive), 'zip_sha256': digest(archive)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
