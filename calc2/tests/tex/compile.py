#!/usr/bin/env python3
"""Сборка файлов .tex настоящим pdflatex и контактные листы (прибор tex_compile).

    ./venv313/bin/python calc2/tests/tex/compile.py [ПАПКА] [--jobs 4] [--sheets [ИМЕНА]] [--per 4]

ПАПКА — папка аудита (по умолчанию reports/calc2_tex/audit): в ней tex/<отпечаток>.tex,
audit.jsonl и shots/<состояние>.paper.png. Собирается каждый РАЗНЫЙ файл; прибор
помнит отпечаток текста каждого собранного файла (compile_cache.json в ПАПКЕ) и
заново собирает только новые тексты. Пишет build/<отпечаток>.pdf и картинку
первой страницы, печатает «собралось K из K» и хвост лога упавших.

--sheets — контактные листы «холст на листе | собранный файл» по состояниям со
снимком листа (shots/). Без значения — все такие состояния; иначе список имён
через запятую или маска с * (fnmatch). Листы — в ПАПКА/sheets/, по --per строк.

Код возврата 1, если хоть один файл не собрался; 3 — pdflatex не найден.
Нужен pdflatex (PATH или /Library/TeX/texbin); для картинок — pdftoppm, на macOS
запасные qlmanage и sips; для листов — Pillow (есть в venv313)."""
import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except Exception:                                    # листы необязательны
    Image = None

ROOT = Path(__file__).resolve().parents[3]


def find_pdflatex():
    found = shutil.which('pdflatex')
    if found:
        return found
    for guess in ('/Library/TeX/texbin/pdflatex', '/usr/local/texlive/bin/pdflatex', '/usr/bin/pdflatex'):
        if os.path.isfile(guess):
            return guess
    return None


def server_env():
    """Окружение сборки — как у сервера (calc2/views.py, compile_pdf_pdflatex):
    только PATH и запреты чтения, записи и оболочки, БЕЗ домашней папки. Так
    TeX не находит шрифты, которые сам дорисовал раньше в ~/Library/texlive
    (mktextfm), и файл, который собирается лишь с ними, здесь не соберётся —
    как и на сервере. Замер 08.10: T2A в 5 pt («$33{,}33_{\\text{м}}$»)."""
    path = os.environ.get('PATH', '')
    if '/Library/TeX/texbin' not in path:
        path += ':/Library/TeX/texbin'
    return {'PATH': path, 'openin_any': 'p', 'openout_any': 'p', 'shell_escape': 'f'}


def pdf_to_png(pdf: Path, png: Path) -> bool:
    """Первая страница PDF → PNG. Три способа, от лучшего к запасному."""
    if shutil.which('pdftoppm'):
        subprocess.run(['pdftoppm', '-r', '150', '-png', '-f', '1', '-l', '1', '-singlefile', str(pdf), str(png.with_suffix(''))], capture_output=True)
        if png.exists():
            return True
    if shutil.which('qlmanage'):
        subprocess.run(['qlmanage', '-t', '-s', '1700', '-o', str(png.parent), str(pdf)], capture_output=True)
        made = png.parent / (pdf.name + '.png')
        if made.exists():
            made.replace(png)
            return True
    if shutil.which('sips'):
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
    for name in ('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf',
                 '/Library/Fonts/Arial Unicode.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_one(binary, bdir: Path, sha: str, src: str, want_png: bool):
    tex = bdir / (sha + '.tex')
    # номер страницы в обрезанную картинку не нужен; сам файл не меняется
    tex.write_text(src.replace('\\begin{document}', '\\begin{document}\n\\pagestyle{empty}', 1), encoding='utf-8')
    try:
        p = subprocess.run([binary, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', tex.name],
                           cwd=bdir, capture_output=True, text=True, errors='replace', timeout=240, env=server_env())
        ok = (bdir / (sha + '.pdf')).exists() and p.returncode == 0
        stdout = p.stdout
    except subprocess.TimeoutExpired:
        ok, stdout = False, 'pdflatex не уложился в 240 с'
    err = ''
    if not ok:
        logf = bdir / (sha + '.log')
        log = logf.read_text(errors='replace') if logf.exists() else stdout
        i = log.find('\n!')
        err = log[i:i + 600].strip() if i >= 0 else log[-600:]
    else:
        for ext in ('.aux', '.log'):
            (bdir / (sha + ext)).unlink(missing_ok=True)
        if want_png and Image is not None and pdf_to_png(bdir / (sha + '.pdf'), bdir / (sha + '.png')):
            crop(Image.open(bdir / (sha + '.png')).convert('RGB')).save(bdir / (sha + '.crop.png'))
            (bdir / (sha + '.png')).unlink(missing_ok=True)
    return ok, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder', nargs='?', default=str(ROOT / 'reports' / 'calc2_tex' / 'audit'))
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--sheets', nargs='?', const='*', default=None)
    ap.add_argument('--per', type=int, default=4)
    a = ap.parse_args()
    out = Path(a.folder).resolve()
    binary = find_pdflatex()
    if not binary:
        print('pdflatex не найден: ни в PATH, ни в /Library/TeX/texbin. Сборку проверить нечем.')
        return 3
    tdir = out / 'tex'
    texs = sorted(tdir.glob('*.tex')) if tdir.is_dir() else sorted(out.glob('*.tex'))
    bdir = out / 'build'
    bdir.mkdir(exist_ok=True)
    cache_f = out / 'compile_cache.json'
    cache = json.loads(cache_f.read_text(encoding='utf-8')) if cache_f.exists() else {}
    jobs = []
    names = {}
    for t in texs:
        src = t.read_text(encoding='utf-8')
        h = hashlib.sha1(src.encode('utf-8')).hexdigest()[:16]
        names[t.stem] = h
        if h in cache and (not cache[h]['ok'] or (bdir / (h + '.pdf')).exists()):
            continue
        jobs.append((h, src))
    print('файлов', len(texs), '| разных текстов', len(set(names.values())), '| собирать заново', len({h for h, _ in jobs}))
    want_png = a.sheets is not None
    done = {}
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = {ex.submit(build_one, binary, bdir, h, src, True): h for h, src in {h: s for h, s in jobs}.items()}
        for i, (f, h) in enumerate(futs.items(), 1):
            ok, err = f.result()
            cache[h] = {'ok': ok, 'err': err}
            done[h] = ok
            if not ok:
                print('НЕ СОБРАЛСЯ', h, err.replace('\n', ' | ')[:300])
            if i % 50 == 0:
                print('  собрано', i, 'из', len(futs))
                cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding='utf-8')
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding='utf-8')
    hs = set(names.values())
    good = sum(1 for h in hs if cache.get(h, {}).get('ok'))
    fails = [stem for stem, h in names.items() if not cache.get(h, {}).get('ok')]
    print('собралось', good, 'из', len(hs))
    for stem in fails[:20]:
        print('   НЕ СОБРАЛСЯ', stem, cache.get(names[stem], {}).get('err', '').replace('\n', ' | ')[:240])
    if want_png:
        sheets(out, bdir, names, cache, binary, a.sheets, a.per)
    return 0 if good == len(hs) else 1


def sheets(out, bdir, names, cache, binary, mask, per):
    if Image is None:
        print('листы пропущены: нет Pillow')
        return
    rows = {}
    log = out / 'audit.jsonl'
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get('sha'):
                    rows[r['id']] = r
    safe = lambda i: ''.join(c if (c.isalnum() or c in '_.-') else '_' for c in i.replace('@', '_at_').replace('#', '_n_'))
    pick = [i for i in sorted(rows) if (out / 'shots' / (safe(i) + '.paper.png')).exists()]
    if mask and mask != '*':
        pats = mask.split(',')
        pick = [i for i in pick if any(fnmatch.fnmatch(i, p) for p in pats)]
    sdir = out / 'sheets'
    sdir.mkdir(exist_ok=True)
    font, small = load_font(20), load_font(15)
    cw, ch = 620, 470
    made = 0
    for si in range(0, len(pick), per):
        part = pick[si:si + per]
        sheet = Image.new('RGB', (cw * 2 + 20, (ch + 46) * len(part) + 40), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        for ci, c in enumerate(['Холст на листе (бумажный прогон)', 'Собранный файл (pdflatex)']):
            d.text((10 + ci * cw + 8, 8), c, fill=(60, 60, 60), font=font)
        for ri, sid in enumerate(part):
            y0 = 40 + ri * (ch + 46)
            tex_file = out / 'tex' / (rows[sid]['sha'] + '.tex')
            h = names.get(rows[sid]['sha'])
            ok = bool(h and cache.get(h, {}).get('ok'))
            d.text((14, y0), sid + ('' if ok else '   НЕ СОБРАЛСЯ'), fill=(0, 0, 0) if ok else (200, 0, 0), font=font)
            if ok and not (bdir / (h + '.crop.png')).exists() and (bdir / (h + '.pdf')).exists():
                if pdf_to_png(bdir / (h + '.pdf'), bdir / (h + '.png')):
                    crop(Image.open(bdir / (h + '.png')).convert('RGB')).save(bdir / (h + '.crop.png'))
            srcs = [out / 'shots' / (safe(sid) + '.paper.png'), bdir / ((h or 'x') + '.crop.png')]
            for ci, s in enumerate(srcs):
                if not s.exists():
                    d.text((10 + ci * cw + 20, y0 + 60), 'нет картинки', fill=(200, 0, 0), font=small)
                    continue
                im = Image.open(s).convert('RGB')
                im.thumbnail((cw - 16, ch - 8))
                sheet.paste(im, (10 + ci * cw + 8, y0 + 30))
            d.line([(0, y0 + ch + 40), (sheet.width, y0 + ch + 40)], fill=(220, 220, 220))
        sheet.save(sdir / ('sheet_%03d.png' % (si // per)))
        made += 1
    print('листов', made, '→', sdir)


if __name__ == '__main__':
    sys.exit(main())
