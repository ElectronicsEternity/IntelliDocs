"""Render source PDF excerpts for the table accuracy explanation; no API calls."""
from pathlib import Path
import fitz

BASE = Path(__file__).resolve().parents[2] / 'backups' / '2026-09-17'
OUT = BASE / 'table-accuracy-audit' / 'examples'
OUT.mkdir(exist_ok=True)
cases = [
    ('Akta Kerja 1955 (Akta 265).pdf', 112, (85, 130, 470, 280), 'borderless'),
    ('Akta Kerja 1955 (Akta 265).pdf', 116, (85, 205, 470, 310), 'wrapped-title'),
    ('Akta Kerja 1955 (Akta 265).pdf', 114, (80, 570, 470, 665), 'kedah-page114'),
    ('Akta Kerja 1955 (Akta 265).pdf', 115, (80, 85, 470, 195), 'kedah-page115'),
    ('Akta Kerja 1955 (Akta 265).pdf', 119, (85, 525, 470, 590), 'section22'),
    ('Akta Kerja 1955 (Akta 265).pdf', 122, (85, 605, 470, 665), 'crop-page122'),
    ('56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf', 4, (65, 670, 535, 785), 'rates-page4'),
    ('56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf', 5, (65, 65, 535, 180), 'rates-page5'),
]
for filename, number, rect, name in cases:
    with fitz.open(BASE / 'pdfs' / filename) as doc:
        doc[number - 1].get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(rect)).save(OUT / f'{name}.png')
print(f'Rendered {len(cases)} source excerpts to {OUT}')
