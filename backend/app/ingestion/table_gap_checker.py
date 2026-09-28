"""Conservative inspection of content outside consecutive table fragments."""
from collections import Counter
import re

from app.config import settings


class TableGapChecker:
    def __init__(self, pages):
        self.pages = pages
        signatures = Counter()
        for page in pages.values():
            signatures.update({self.signature(line) for line in self.lines(page['words'])
                               if self.in_margin(line, page['height'])})
        self.routine = {s for s, count in signatures.items()
                        if count >= settings.TABLE_ROUTINE_HEADER_MIN_PAGES}

    @staticmethod
    def lines(words):
        lines = []
        for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
            if not lines or abs(word['top'] - lines[-1][0]['top']) > 3:
                lines.append([word])
            else:
                lines[-1].append(word)
        return lines

    @staticmethod
    def signature(line):
        text = ' '.join(w['text'] for w in sorted(line, key=lambda w: w['x0'])).casefold()
        return re.sub(r'\b\d+\b', '#', text)

    @staticmethod
    def in_margin(line, height):
        margin = settings.TABLE_ROUTINE_MARGIN_RATIO
        return max(w['bottom'] for w in line) <= height * margin or min(w['top'] for w in line) >= height * (1-margin)

    def clear_region(self, page, top, bottom):
        for line in self.lines(page['words']):
            if not any(w['bottom'] > top + 0.5 and w['top'] < bottom - 0.5 for w in line):
                continue
            text = ' '.join(w['text'] for w in line).strip()
            routine = self.in_margin(line, page['height']) and (
                text.isdecimal() or self.signature(line) in self.routine)
            if not routine:
                return False
        # Unknown image content cannot be treated as blank space.
        return not any(image['bottom'] > top and image['top'] < bottom
                       for image in page.get('images', []))

    def gap_is_clear(self, current, following):
        first = self.pages.get(current.page_number)
        second = self.pages.get(following.page_number)
        if first is None or second is None:
            return False
        return self.clear_region(first, current.bounding_box[3], first['height']) and self.clear_region(second, 0, following.bounding_box[1])
