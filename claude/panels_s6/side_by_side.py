"""Снимок рядом с макетом: python3 claude/panels_s6/side_by_side.py <снимок.png> <макет.png> <выход.png>"""
import sys
from PIL import Image
a, b = Image.open(sys.argv[1]).convert('RGB'), Image.open(sys.argv[2]).convert('RGB')
h = max(a.height, b.height)
out = Image.new('RGB', (a.width + b.width + 24, h), (128, 128, 128))
out.paste(a, (0, 0)); out.paste(b, (a.width + 24, 0))
out.save(sys.argv[3])
