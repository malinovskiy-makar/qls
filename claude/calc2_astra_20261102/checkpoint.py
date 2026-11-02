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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage')
    args = parser.parse_args()
    if not re.fullmatch(r'e(?:[1-9]|1[0-3])', args.stage):
        raise SystemExit('Нужен номер собственного этапа e1…e13.')
    if str(ROOT) != '/private/tmp/calc2-astra-local-20261102/calc2-astra-work':
        raise SystemExit('Только изолированная рабочая копия.')
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    out = DEST / (args.stage + '-' + sha[:8])
    out.mkdir(parents=True, exist_ok=False)
    bundle = out / 'work.bundle'
    subprocess.run(['git', 'bundle', 'create', str(bundle), 'HEAD', '^' + BASE], cwd=ROOT, check=True)
    subprocess.run(['git', 'bundle', 'verify', str(bundle)], cwd=ROOT, check=True)
    for name in ('JOURNAL.md', 'PLAN.md', 'PROMPT.md'):
        shutil.copyfile(ROOT / 'claude/calc2_astra_20261102' / name, out / name)
    for adr in sorted((ROOT / 'docs/adr').glob('calc2-astra-20261102-' + args.stage + '-*.md')):
        shutil.copyfile(adr, out / adr.name)
    own = ROOT / '.calc2-astra-local'
    paths = sorted((own / 'logs').glob(args.stage + '-*'))
    paths += [p for p in (own / (args.stage + '-shots'), own / ('mutations-' + args.stage)) if p.exists()]
    with tarfile.open(out / 'evidence.tar.gz', 'w:gz') as tar:
        for p in paths:
            tar.add(p, arcname=str(p.relative_to(own)), recursive=True)
    rows = [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(out.iterdir()) if p.is_file()]
    manifest = {'stage': args.stage, 'head': sha, 'requires_base': BASE,
                'created_utc': datetime.now(timezone.utc).isoformat(), 'files': rows}
    (out / 'SHA256_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    for row in rows:
        if hashlib.sha256((out / row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError('Сохранённые байты не совпали: ' + row['file'])
    print(str(out))


if __name__ == '__main__':
    main()
