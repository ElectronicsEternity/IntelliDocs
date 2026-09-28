"""Page-hinted, opening-confirmed DFS mapper used by live ingestion."""
import re

from app.indexing.candidate_page_mapper import CandidatePageMapper


class ForwardDFSPageMapper(CandidatePageMapper):
    @staticmethod
    def identifier_confirms(node, page, start):
        """Require the identifier in the opening or adjacent printed heading.

        Never accept an unrelated identifier elsewhere on the claimed page.
        Whitespace/line wraps may separate heading and identifier, not body text.
        """
        identifier = (node.identifier or '').strip()
        if not identifier:
            return True
        compact = lambda text: ''.join(text.lower().split())
        suffix = compact(page.text[start:])
        label = compact(identifier)
        match = ForwardDFSPageMapper.first_match(identifier, page, start, identifier=True)
        if match and match[1] == start:
            return True
        title = compact(node.title or '')
        if not title or not suffix.startswith(title):
            return False
        # Heading followed directly by its provision number.
        if suffix[len(title):].startswith(label):
            return True
        # Identifier printed as part of the heading itself.
        if match:
            prefix = compact(page.text[start:match[1]])
            if len(prefix) + len(label) <= len(title) and title[len(prefix):].startswith(label):
                return True
        # Identifier immediately precedes the heading (e.g. PART XIV).
        pattern = r'(?<!\w)' + r'\s*'.join(re.escape(c) for c in identifier if not c.isspace()) + r'\s*$'
        return re.search(pattern, page.text[:start], re.IGNORECASE) is not None

    @staticmethod
    def first_match(anchor, page, minimum=0, identifier=False):
        """Return the earliest normalized match after the cursor, not all matches."""
        chars, offsets = [], []
        pending = False
        for index, char in enumerate(page.text):
            if char.isspace():
                pending = bool(chars)
                continue
            if pending:
                chars.append(' ')
                offsets.append(index)
                pending = False
            for lower in char.lower():
                chars.append(lower)
                offsets.append(index)
        needle = ' '.join(anchor.lower().split())
        if not needle:
            return None
        compact = [(c, p) for c, p in zip(chars, offsets) if not c.isspace()]
        variants = [(''.join(chars), offsets, needle),
                    (''.join(c for c, _ in compact), [p for _, p in compact], ''.join(needle.split()))]
        first = None
        for text, positions, search in variants:
            low = next((i for i, p in enumerate(positions) if p >= minimum), len(positions))
            while True:
                match = text.find(search, low)
                if match < 0:
                    break
                original = positions[match]
                after = positions[match + len(search) - 1] + 1
                before_char = page.text[original - 1] if original else ''
                after_char = page.text[after:after + 1]
                if not identifier or not (before_char.isalnum() or (search[-1].isalnum() and after_char.isalnum())):
                    first = original if first is None else min(first, original)
                    break
                low = match + 1
        return None if first is None else (page.page_number, first)

    def map_document(self, document, page_hints, opening_texts=None):
        nodes = self.repository.get_by_document(document.id)
        ordered, children, lookup = self._ordered(nodes)
        if not document.pages:
            raise ValueError('Cannot map an empty document.')
        pages = {p.page_number: p for p in document.pages}
        last = max(document.pages, key=lambda p: p.page_number)
        cursor = None
        failures = []
        anchors = []
        for node in ordered:
            previous_cursor = cursor
            node.start_page = node.start_character = node.end_page = None
            opening = (opening_texts or {}).get(node.id)
            anchor = opening.strip() if isinstance(opening, str) and opening.strip() else ((node.title or '').strip() or (node.identifier or '').strip())
            if node.node_type.upper() == 'TABLE' or not anchor:
                continue
            anchors.append(node)
            hint = page_hints.get(node.id)
            reason = None
            if type(hint) is not int or hint not in pages:
                reason = 'invalid or missing page hint'
            elif cursor and hint < cursor[0]:
                reason = 'page hint precedes forward cursor'
            else:
                minimum = cursor[1] + 1 if cursor and hint == cursor[0] else 0
                page = pages[hint]
                title = (node.title or '').strip()
                match = self.first_match(title or anchor, page, minimum, identifier=not bool(title or opening))
                if match is None:
                    reason = 'text not found after cursor on claimed page'
                elif title and opening:
                    opening_match = self.first_match(opening, page, minimum)
                    if opening_match:
                        # A repeated title alone is not a confirmed opening. Check
                        # the title at the first full opening-text candidate.
                        match = self.first_match(title, page, opening_match[1])
                    # Both excerpts must describe the same opening. An identifier
                    # printed immediately before the title is part of that opening.
                    compact = lambda text: ''.join(text.lower().split())
                    same_start = opening_match == match
                    identifier_prefix = False
                    if opening_match and match and opening_match[1] < match[1]:
                        prefix = compact(page.text[opening_match[1]:match[1]])
                        identifier_prefix = bool(node.identifier) and prefix == compact(node.identifier)
                    if not (same_start or identifier_prefix):
                        reason = 'title and opening text do not confirm the same location'
                    else:
                        node.start_page, node.start_character = cursor = opening_match
                else:
                    node.start_page, node.start_character = cursor = match
            if not reason and node.start_character is not None and not self.identifier_confirms(node, pages[hint], node.start_character):
                # A PART title may repeat its first SECTION title. Advance past
                # unconfirmed text, accepting only the first combined valid match.
                candidate = node.start_character
                confirmed = None
                while True:
                    next_match = self.first_match(anchor, pages[hint], candidate + 1)
                    if next_match is None:
                        break
                    candidate = next_match[1]
                    title_match = self.first_match(title, pages[hint], candidate) if title else next_match
                    title_agrees = title_match == next_match
                    if title_match and title_match[1] > candidate:
                        title_agrees = ''.join(pages[hint].text[candidate:title_match[1]].lower().split()) == ''.join((node.identifier or '').lower().split())
                    if title_agrees and self.identifier_confirms(node, pages[hint], candidate):
                        confirmed = next_match
                        break
                if confirmed:
                    node.start_page, node.start_character = cursor = confirmed
                else:
                    reason = 'identifier does not confirm the title/opening location'
                    node.start_page = node.start_character = None
                    # Rejected matches must not advance the search cursor.
                    cursor = previous_cursor
            if reason:
                failures.append({'id': node.id, 'title': node.title, 'identifier': node.identifier, 'reason': reason})

        # Ranges are calculated after searching; they do not constrain searches.
        def end(node):
            siblings = children[node.parent_id]
            for sibling in siblings[siblings.index(node) + 1:]:
                if sibling.start_character is not None:
                    return sibling.start_page
            return end(lookup[node.parent_id]) if node.parent_id is not None else last.page_number

        for node in ordered:
            if node.start_character is not None:
                node.end_page = end(node)
            elif node not in anchors:
                parent = lookup.get(node.parent_id)
                node.start_page = parent.start_page if parent else min(pages)
                node.end_page = parent.end_page if parent else last.page_number
        self.last_report = {'resolved': sum(n.start_character is not None for n in anchors),
                            'unresolved': failures, 'method': 'first title match confirmed by opening text at the same location on claimed page after forward DFS cursor; no parent search filter'}
        for node in nodes:
            self.repository.update_page_range(node_id=node.id, start_page=node.start_page,
                                              start_character=node.start_character, end_page=node.end_page)
        return self.last_report
