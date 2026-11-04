"""Prepare system T2A metrics at image build time, never in a user's home.

Debian ships LH sources and CM-Super outlines. The restricted PDF worker has
no HOME and cannot use metrics generated on demand in root's private cache.
Generate the standard Computer Modern T2A families into the system TeX tree.
"""
from pathlib import Path
import re
import shutil
import subprocess


def main():
    maps = Path('/usr/share/texmf/fonts/map/dvips/cm-super')
    definitions = Path('/usr/share/texlive/texmf-dist/tex/latex/cyrillic')
    families = {
        name for filename in ('t2acmr.fd', 't2acmss.fd', 't2acmtt.fd')
        for name in re.findall(r'\{(la[a-z]+)\}', (definitions / filename).read_text())
    }
    fonts = sorted({
        line.split()[0]
        for mapping in maps.glob('*t2a.map')
        for line in mapping.read_text().splitlines()
        if line.strip() and not line.startswith('%')
        and re.sub(r'\d+$', '', line.split()[0]) in families
    })
    if not fonts:
        raise RuntimeError('CM-Super T2A maps are missing')
    target = Path('/usr/local/share/texmf/fonts/tfm/lh/lh-t2a')
    target.mkdir(parents=True, exist_ok=True)
    for name in fonts:
        if (target / (name + '.tfm')).is_file():
            continue
        existing = subprocess.run(['kpsewhich', name + '.tfm'], capture_output=True, text=True)
        if existing.returncode == 0:
            shutil.copyfile(existing.stdout.strip(), target / (name + '.tfm'))
            continue
        result = subprocess.run(
            ['mktextfm', '--destdir', str(target), name],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode or not (target / (name + '.tfm')).is_file():
            raise RuntimeError(f'{name}: {result.stderr[-2000:]}')
    subprocess.run(['mktexlsr'], check=True)
    print(f'System T2A font metrics ready: {len(fonts)}')


if __name__ == '__main__':
    main()
