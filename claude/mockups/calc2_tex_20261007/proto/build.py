#!/usr/bin/env python3
"""Собрать .tex из папки настоящим pdflatex, снять картинки и сложить
контактные листы «холст на листе | собранный файл | нынешняя выгрузка».

    ./venv313/bin/python claude/mockups/calc2_tex_20261007/proto/build.py ПАПКА [ПАПКА_С_НЫНЕШНЕЙ_ВЫГРУЗКОЙ]

В ПАПКЕ лежат <состояние>.tex и <состояние>.paper.png (их пишет run.mjs).
Пишет: ПАПКА/build/*.pdf, ПАПКА/_build.json («собралось N из N», хвост лога
упавших), ПАПКА/sheet_NN.png. Код возврата 1, если хоть один файл не собрался.

Нужны: pdflatex (ищется в PATH и в /Library/TeX/texbin), для картинок —
pdftoppm (poppler) либо, на macOS, qlmanage или sips. Нет ничего из трёх —
файлы всё равно собираются и считаются, листов просто не будет. Листам
нужен Pillow (он есть в venv313 проекта)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except Exception:                                    # листы необязательны
    Image = None


def find_pdflatex():
    found = shutil.which('pdflatex')
    if found:
        return found
    for guess in ('/Library/TeX/texbin/pdflatex', '/usr/local/texlive/bin/pdflatex', '/usr/bin/pdflatex'):
        if os.path.isfile(guess):
            return guess
    return None


def pdf_to_png(pdf: Path, png: Path) -> bool:
    """Первая страница PDF → PNG. Три способа, от лучшего к запасному."""
    if shutil.which('pdftoppm'):
        stem = png.with_suffix('')
        subprocess.run(['pdftoppm', '-r', '150', '-png', '-f', '1', '-l', '1', '-singlefile', str(pdf), str(stem)], capture_output=True)
        if png.exists():
            return True
    if shutil.which('qlmanage'):                     # macOS: чёткая миниатюра нужного размера
        subprocess.run(['qlmanage', '-t', '-s', '1700', '-o', str(png.parent), str(pdf)], capture_output=True)
        made = png.parent / (pdf.name + '.png')
        if made.exists():
            made.replace(png)
            return True
    if shutil.which('sips'):                         # macOS: страница в 72 dpi, мелко, но видно
        subprocess.run(['sips', '-s', 'format', 'png', str(pdf), '--out', str(png)], capture_output=True)
        if png.exists():
            return True
    return False


def crop(img, pad=14):
    bg = Image.new(img.mode, img.size, (255, 255, 255))
    box = ImageChops.difference(img, bg).getbbox()
    if not box:
        return img
    left, top, right, bottom = box
    return img.crop((max(0, left - pad), max(0, top - pad), min(img.width, right + pad), min(img.height, bottom + pad)))


def load_font(size):
    for name in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                 '/System/Library/Fonts/Supplemental/Arial.ttf', '/Library/Fonts/Arial Unicode.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1]).resolve()
    base = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    binary = find_pdflatex()
    if not binary:
        print('pdflatex не найден: ни в PATH, ни в /Library/TeX/texbin. Сборку проверить нечем.')
        return 3
    keys = [p.name[:-4] for p in sorted(out.glob('*.tex'))]
    bdir = out / 'build'
    bdir.mkdir(exist_ok=True)
    res = {}
    pictures = 0
    for k in keys:
        safe = k.replace('@', '_at_').replace('#', '_n_')
        src = (out / (k + '.tex')).read_text(encoding='utf-8')
        # номер страницы в обрезанную картинку не нужен; сам файл не меняется
        (bdir / (safe + '.tex')).write_text(src.replace('\\begin{document}', '\\begin{document}\n\\pagestyle{empty}', 1), encoding='utf-8')
        try:
            p = subprocess.run([binary, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', safe + '.tex'],
                               cwd=bdir, capture_output=True, text=True, errors='replace', timeout=240)
            ok = (bdir / (safe + '.pdf')).exists() and p.returncode == 0
            stdout = p.stdout
        except subprocess.TimeoutExpired:
            ok, stdout = False, 'pdflatex не уложился в 240 с'
        err = ''
        if not ok:
            logf = bdir / (safe + '.log')
            log = logf.read_text(errors='replace') if logf.exists() else stdout
            i = log.find('\n!')
            err = log[i:i + 500].strip() if i >= 0 else log[-500:]
        elif Image is not None and pdf_to_png(bdir / (safe + '.pdf'), bdir / (safe + '.png')):
            crop(Image.open(bdir / (safe + '.png')).convert('RGB')).save(bdir / (safe + '.crop.png'))
            pictures += 1
        res[k] = {'ok': ok, 'err': err}
        print(('OK   ' if ok else 'FAIL ') + k + (('  ' + err.replace('\n', ' | ')[:300]) if err else ''))
        for ext in ('.aux', '.log'):
            if ok:
                (bdir / (safe + ext)).unlink(missing_ok=True)
    (out / '_build.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    good = sum(1 for v in res.values() if v['ok'])
    print('собралось', good, 'из', len(res))

    if Image is None or not pictures:
        print('картинок нет (нужен Pillow и одно из: pdftoppm, qlmanage, sips): листы пропущены')
        return 0 if good == len(res) else 1
    font, small = load_font(20), load_font(15)
    cw, ch = 620, 470
    cols = ['Холст на листе (бумажный прогон)', 'Собранный файл'] + (['Нынешняя выгрузка'] if base else [])
    rows_per = 4
    for si in range(0, len(keys), rows_per):
        part = keys[si:si + rows_per]
        sheet = Image.new('RGB', (cw * len(cols) + 20, (ch + 46) * len(part) + 40), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        for ci, c in enumerate(cols):
            d.text((10 + ci * cw + 8, 8), c, fill=(60, 60, 60), font=font)
        for ri, k in enumerate(part):
            y0 = 40 + ri * (ch + 46)
            d.text((14, y0), k + ('' if res[k]['ok'] else '   НЕ СОБРАЛСЯ'), fill=(0, 0, 0) if res[k]['ok'] else (200, 0, 0), font=font)
            safe = k.replace('@', '_at_').replace('#', '_n_')
            srcs = [out / (k + '.paper.png'), bdir / (safe + '.crop.png')]
            if base:
                srcs.append(base / (k.split('@')[0] + '.legacy.crop.png'))
            for ci, s in enumerate(srcs):
                if not s.exists():
                    d.text((10 + ci * cw + 20, y0 + 60), 'нет картинки', fill=(200, 0, 0), font=small)
                    continue
                im = Image.open(s).convert('RGB')
                im.thumbnail((cw - 16, ch - 8))
                sheet.paste(im, (10 + ci * cw + 8, y0 + 30))
            d.line([(0, y0 + ch + 40), (sheet.width, y0 + ch + 40)], fill=(220, 220, 220))
        sheet.save(out / ('sheet_%02d.png' % (si // rows_per)))
    print('листов', (len(keys) + rows_per - 1) // rows_per)
    return 0 if good == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
