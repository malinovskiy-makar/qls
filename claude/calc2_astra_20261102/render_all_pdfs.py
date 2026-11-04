"""Отрисовать все сохранённые PDF и собрать обзорные листы для визуальной проверки."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / '.calc2-astra-local/final-exports/all-models-v5'


def main():
    manifest = json.loads((EXPORTS / 'MANIFEST.json').read_text())
    if manifest['passed'] != 48 or any(row['pages'] != 1 for row in manifest['files']):
        raise SystemExit('Ожидались 48 одностраничных PDF.')
    rendered = EXPORTS / 'rendered'
    rendered.mkdir(exist_ok=False)
    qa = EXPORTS / 'qa'
    qa.mkdir()
    # В PDF TeX набирает радикал чуть шире SVG. До правки ATC и 80_MC
    # пересекались на 1,156 pt по горизонтали и 2,738 pt по вертикали.
    bbox_xml = subprocess.check_output(['/opt/homebrew/bin/pdftotext', '-bbox',
                                       str(EXPORTS / 'pdf/mono-nat.pdf'), '-'])
    words = ET.fromstring(bbox_xml).findall('.//{http://www.w3.org/1999/xhtml}word')
    coord_atc = max((w for w in words if w.text == 'ATC'), key=lambda w: float(w.attrib['yMax']))
    coord_80 = max((w for w in words if w.text == '80'), key=lambda w: float(w.attrib['yMax']))
    a, b = coord_atc.attrib, coord_80.attrib
    dx = min(float(a['xMax']), float(b['xMax'])) - max(float(a['xMin']), float(b['xMin']))
    dy = min(float(a['yMax']), float(b['yMax'])) - max(float(a['yMin']), float(b['yMin']))
    if dx > 0 and dy > 0:
        raise RuntimeError(f'Подписи ATC и 80_MC налезают в готовом PDF: {dx}, {dy}')
    (qa / 'PDF_LABEL_CHECK.json').write_text(json.dumps({'model': 'mono-nat', 'atc': a, 'mc80': b,
                                                       'overlap_x_pt': dx, 'overlap_y_pt': dy,
                                                       'passed': True}, indent=2) + '\n')

    def render(row):
        subprocess.run(['/opt/homebrew/bin/pdftoppm', '-png', '-singlefile', '-scale-to', '1800',
                        str(EXPORTS / 'pdf' / (row['name'] + '.pdf')), str(rendered / row['name'])],
                       check=True, capture_output=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(render, manifest['files']))
    rows = []
    for start in range(0, 48, 6):
        sheet = Image.new('RGB', (1400, 1380), '#e6e8eb')
        draw = ImageDraw.Draw(sheet)
        for slot, row in enumerate(manifest['files'][start:start + 6]):
            full = Image.open(rendered / (row['name'] + '.png')).convert('RGB')
            # Только обзорный лист: полная страница сохранена без обрезки.
            # Убираем белое поле и нижний номер страницы, чтобы видеть график крупно.
            region = full.crop((0, 0, full.width, int(full.height * .9)))
            box = ImageChops.difference(region, Image.new('RGB', region.size, 'white')).getbbox()
            if not box:
                raise RuntimeError('Пустая страница: ' + row['name'])
            crop = region.crop((max(0, box[0] - 16), max(0, box[1] - 16),
                                min(region.width, box[2] + 16), min(region.height, box[3] + 16)))
            crop.thumbnail((680, 415))
            x, y = (slot % 2) * 700, (slot // 2) * 460
            draw.text((x + 12, y + 10), row['name'], fill='black', font_size=22)
            sheet.paste(crop, (x + (700 - crop.width) // 2, y + 38))
            rows.append({'name': row['name'], 'full_png': str((rendered / (row['name'] + '.png')).relative_to(EXPORTS)),
                         'overview': f'overview-{start // 6 + 1:02d}.png', 'overview_crop': box})
        sheet.save(qa / f'overview-{start // 6 + 1:02d}.png')
    (qa / 'RENDER_MANIFEST.json').write_text(json.dumps({'rendered_pages': 48, 'files': rows}, indent=2) + '\n')
    print(f'Отрисовано 48 полных страниц, обзорных листов 8: {qa}')


if __name__ == '__main__':
    main()
