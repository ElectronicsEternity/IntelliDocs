"""Geometry-only pdfplumber fallback within explicitly identified table regions.

No domain-specific headings or page numbers. Columns are inferred from header
groups and persistent whitespace gutters; rows remain physical text-line bands.
"""
from app.config import settings


def find_borderless_tables(page, bbox):
    cropped = page.crop(tuple(bbox))
    words = sorted(cropped.extract_words(), key=lambda w: (w['top'], w['x0']))
    lines = []
    for word in words:
        tolerance = max(3, (word['bottom'] - word['top']) * 0.6)
        if not lines or abs(word['top'] - lines[-1][0]['top']) > tolerance:
            lines.append([word])
        else:
            lines[-1].append(word)
    if len(lines) < settings.BORDERLESS_TABLE_MIN_LINES:
        return []
    header = sorted(lines[0], key=lambda w: w['x0'])
    groups = []
    for word in header:
        if not groups or word['x0'] - groups[-1][-1]['x1'] >= settings.BORDERLESS_TABLE_HEADER_GAP:
            groups.append([word])
        else:
            groups[-1].append(word)
    if len(groups) < 2:
        return []
    centers = [(group[0]['x0'] + group[-1]['x1']) / 2 for group in groups]
    columns = [min(w['x0'] for w in words)]
    for left, right in zip(centers, centers[1:]):
        # Reject boundaries cutting source words instead of silently truncating.
        possible = [float(x) for x in range(int(left)+1, int(right))
                    if not any(w['x0'] < x < w['x1'] for w in words)]
        if not possible:
            return []
        runs = []
        for x in possible:
            if not runs or x - runs[-1][-1] > 1:
                runs.append([x])
            else:
                runs[-1].append(x)
        widest = max(runs, key=len)
        columns.append((widest[0] + widest[-1]) / 2)
    columns.append(max(w['x1'] for w in words))
    bands = [min(w['top'] for w in lines[0])]
    for current, following in zip(lines, lines[1:]):
        bands.append((max(w['bottom'] for w in current) + min(w['top'] for w in following)) / 2)
    bands.append(max(w['bottom'] for w in lines[-1]))
    return cropped.find_tables({'vertical_strategy': 'explicit', 'horizontal_strategy': 'explicit',
                                'explicit_vertical_lines': columns, 'explicit_horizontal_lines': bands})
