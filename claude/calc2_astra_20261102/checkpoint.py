"""Сохранить только собственный этап: локальные коммиты и результаты проверок."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '4e87a8db02647f297d5cf1a1eb776e62928071cd'
DEST = Path('/Users/makarmalinovskiy/Documents/ChatGPT/Weconomics/calc2-astra-checkpoints')


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_restore(bundle, sha, out):
    destination = Path('/private/tmp') / ('calc2-astra-final-verify-' + sha[:12])
    if destination.exists():
        raise RuntimeError('Папка проверки уже существует: ' + str(destination))
    with (out / 'RESTORE_VERIFICATION.log').open('w') as log:
        subprocess.run(['git', 'clone', str(bundle), str(destination)],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(['git', 'remote', 'remove', 'origin'], cwd=destination, check=True)
        restored = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=destination, text=True).strip()
        if restored != sha:
            raise RuntimeError('HEAD восстановленной копии не совпал.')
        subprocess.run(['git', 'fsck', '--full', '--no-reflogs'], cwd=destination,
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=destination, text=True)
        if status:
            raise RuntimeError('Восстановленная копия не чиста: ' + status)
    result = {'head': restored, 'path': str(destination), 'full_clone': True,
              'fsck': 'passed', 'clean_worktree': True, 'remote_removed': True}
    (out / 'RESTORE_VERIFICATION.json').write_text(json.dumps(result, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage')
    args = parser.parse_args()
    if not re.fullmatch(r'e(?:[1-9]|1[0-3])|final', args.stage):
        raise SystemExit('Нужен номер собственного этапа e1…e13 или final.')
    if str(ROOT) != '/private/tmp/calc2-astra-local-20261102/calc2-astra-work':
        raise SystemExit('Только изолированная рабочая копия.')
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True):
        raise SystemExit('Перед сохранением нужно закоммитить все собственные изменения.')
    out = DEST / (args.stage + '-' + sha[:8])
    out.mkdir(parents=True, exist_ok=False)
    bundle = out / 'work.bundle'
    # Финальный комплект восстанавливается самостоятельно, без старой копии A2.
    branch = subprocess.check_output(['git', 'symbolic-ref', 'HEAD'], cwd=ROOT, text=True).strip()
    refs = ['HEAD', branch] if args.stage == 'final' else ['HEAD', '^' + BASE]
    subprocess.run(['git', 'bundle', 'create', str(bundle), *refs], cwd=ROOT, check=True)
    subprocess.run(['git', 'bundle', 'verify', str(bundle)], cwd=ROOT, check=True)
    for name in ('JOURNAL.md', 'PLAN.md', 'PROMPT.md'):
        shutil.copyfile(ROOT / 'claude/calc2_astra_20261102' / name, out / name)
    if args.stage == 'final':
        for name in ('REPORT.md', 'HANDOFF.md', 'CI_FINDINGS.md', 'SOURCE_MANIFEST.json'):
            shutil.copyfile(ROOT / 'claude/calc2_astra_20261102' / name, out / name)
    for adr in sorted((ROOT / 'docs/adr').glob('calc2-astra-20261102-' + args.stage + '-*.md')):
        shutil.copyfile(adr, out / adr.name)
    own = ROOT / '.calc2-astra-local'
    paths = sorted((own / 'logs').glob(args.stage + '-*'))
    paths += [p for p in (own / (args.stage + '-shots'), own / ('mutations-' + args.stage)) if p.exists()]
    if args.stage == 'final':
        # Полный журнал всех этапов, включая исходные красные прогоны.
        paths = [own / 'logs']
        paths += sorted(own.glob('e*-shots')) + sorted(own.glob('mutations-e*'))
        paths += [p for p in (own / 'audit', own / 'shots', own / 'final-exports') if p.exists()]
        paths += sorted(own.glob('final-labelshake-*.png'))
        paths += sorted(own.glob('final-*-shots'))
        paths += sorted(own.glob('final-*-diagnostic.mjs'))
        exports = own / 'final-exports/all-models-v5'
        pdf_manifest = json.loads((exports / 'MANIFEST.json').read_text())
        if pdf_manifest['passed'] != 48 or len(list((exports / 'pdf').glob('*.pdf'))) != 48:
            raise RuntimeError('Нет полного комплекта 48 PDF.')
        if len(pdf_manifest['files']) != 48 or len(list((exports / 'tex').glob('*.tex'))) != 48:
            raise RuntimeError('Число исходников TeX или записей манифеста не равно 48.')
        for row in pdf_manifest['files']:
            if not row['ok'] or row['pages'] != 1:
                raise RuntimeError('Неверный результат сборки PDF: ' + row['name'])
            for extension in ('pdf', 'tex'):
                path = exports / extension / (row['name'] + '.' + extension)
                if sha256_file(path) != row[extension + '_sha256']:
                    raise RuntimeError('Файл изменился после сборки: ' + str(path))
        for name, expected in pdf_manifest['runtime_sources_sha256'].items():
            if sha256_file(ROOT / name) != expected:
                raise RuntimeError('Код изменился после сборки PDF: ' + name)
        review = json.loads((exports / 'qa/VISUAL_REVIEW.json').read_text())
        if review['pages'] != 48 or review['remaining_export_defects_observed']:
            raise RuntimeError('Визуальная проверка PDF не завершена.')
        shutil.copytree(exports / 'pdf', out / 'PDF')
        shutil.copytree(exports / 'tex', out / 'TeX')
        shutil.copyfile(exports / 'MANIFEST.json', out / 'PDF_MANIFEST.json')
        shutil.copytree(exports / 'qa', out / 'PDF_QA')
        index = ['# Все 48 PDF', '',
                 '46 стартов моделей (включая два налоговых псевдонима) и два специальных состояния.', '',
                 '| Модель | PDF | Исходник |', '| --- | --- | --- |']
        for tex in sorted((exports / 'tex').glob('*.tex')):
            match = re.search(r'^% Модель: (.+)', tex.read_text(), re.M)
            title = match.group(1).rstrip('.') if match else tex.stem
            index.append(f'| {title} | [{tex.stem}](PDF/{tex.stem}.pdf) | [TeX](TeX/{tex.name}) |')
        (out / 'PDF_INDEX.md').write_text('\n'.join(index) + '\n')
        (out / 'README.md').write_text(
            '# Итоговый комплект графиков\n\n'
            'Все 13 этапов сохранены локально. Тренажёр и прод не изменялись.\n\n'
            '- [Итог и сценарии приёмки](REPORT.md)\n'
            '- [Открыть список 48 PDF](PDF_INDEX.md)\n'
            '- [Как продолжить и восстановить код](HANDOFF.md)\n'
            '- [Незелёные общепроектные проверки](CI_FINDINGS.md)\n\n'
            f'Итоговый коммит: `{sha}`. Полная история кода: `work.bundle`.\n'
            'Логи всех этапов и снимки: `evidence.tar.gz`. Контрольные суммы всех файлов '
            'и протокол восстановления лежат рядом. Общий CI не объявлен зелёным; '
            'приёмка владельца и разрешение на выкатку остаются впереди.\n')
        shutil.copytree(ROOT / 'claude/calc2_astra_20261102/source', out / 'source')
        sources = json.loads((out / 'SOURCE_MANIFEST.json').read_text())
        for name, meta in sources['files'].items():
            if sha256_file(out / 'source' / name) != meta['sha256']:
                raise RuntimeError('Изменён восстановленный источник Claude: ' + name)
        adr_dir = out / 'ADR'
        adr_dir.mkdir()
        for adr in sorted((ROOT / 'docs/adr').glob('calc2-astra-20261102-*.md')):
            shutil.copyfile(adr, adr_dir / adr.name)
    with tarfile.open(out / 'evidence.tar.gz', 'w:gz') as tar:
        for p in paths:
            tar.add(p, arcname=str(p.relative_to(own)), recursive=True,
                    filter=lambda info: None if info.name == 'logs/server.log' else info)
    if args.stage == 'final':
        verify_restore(bundle, sha, out)
    rows = [{'file': str(p.relative_to(out)), 'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
            for p in sorted(out.rglob('*')) if p.is_file()]
    manifest = {'stage': args.stage, 'head': sha, 'base': BASE,
                'requires_base': None if args.stage == 'final' else BASE,
                'created_utc': datetime.now(timezone.utc).isoformat(), 'files': rows}
    (out / 'SHA256_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    for row in rows:
        if sha256_file(out / row['file']) != row['sha256']:
            raise RuntimeError('Сохранённые байты не совпали: ' + row['file'])
    print(str(out))


if __name__ == '__main__':
    main()
