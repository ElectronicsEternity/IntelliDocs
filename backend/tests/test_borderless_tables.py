from io import BytesIO

import pdfplumber

from app.ingestion.pdfplumber_table_extractor import PdfPlumberTableExtractor


def pdf(lines):
    commands = []
    for row, values in enumerate(lines):
        for column, value in enumerate(values):
            commands.append(f'BT /F1 12 Tf 1 0 0 1 {50 + column * 180} {440 - row * 30} Tm ({value}) Tj ET')
    stream = '\n'.join(commands).encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 500] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream']
    data = b'%PDF-1.4\n'
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    return pdfplumber.open(BytesIO(data))


def test_region_borderless_columns_preserve_words_and_geometry():
    with pdf([['Employee', 'Rate'], ['Person A', '100'], ['Person B', '200']]) as document:
        extractor = PdfPlumberTableExtractor(skip_first_page=False)
        assert extractor.extract_page_tables(document.pages[0], 1) == []
        tables = extractor.extract_page_tables(document.pages[0], 1, [(40, 40, 400, 160)])
        assert len(tables) == 1
        assert tables[0].rows == [['Employee', 'Rate'], ['Person A', '100'], ['Person B', '200']]
        assert len(tables[0].cell_bounding_boxes) == 3


def test_single_column_prose_is_not_borderless_table():
    with pdf([['Ordinary paragraph'], ['Another sentence'], ['More content']]) as document:
        tables = PdfPlumberTableExtractor(False).extract_page_tables(document.pages[0], 1, [(40, 40, 400, 160)])
        assert tables == []


def test_cover_skip_is_preserved():
    with pdf([['Employee', 'Rate'], ['Person A', '100'], ['Person B', '200']]) as document:
        assert PdfPlumberTableExtractor().extract_page_tables(document.pages[0], 1, [(40, 40, 400, 160)]) == []
