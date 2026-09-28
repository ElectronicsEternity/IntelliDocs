"""Opt-in boundary experiment; no profiling, chunking, or embedding calls."""
from collections import defaultdict
import re

from app.indexing.page_mapper import PageMapper


class CandidatePageMapper(PageMapper):
    """Resolve only positions forced by text matches and hierarchy order.

    Multiple equally valid locations stay unresolved, except the first titled
    HEADING directly below the DOCUMENT root, which uses its earliest match.
    Existing database positions
    are never used as hints. Tables retain the existing geometry-owned behavior.
    """

    @staticmethod
    def _matches(anchor, pages, identifier=False):
        needle = ' '.join(anchor.lower().split())
        if not needle:
            return []
        found = set()
        for page in pages:
            chars, positions = [], []
            pending = False
            for index, char in enumerate(page.text):
                if char.isspace():
                    pending = bool(chars)
                    continue
                if pending:
                    chars.append(' ')
                    positions.append(index)
                    pending = False
                for lower in char.lower():
                    chars.append(lower)
                    positions.append(index)
            normal = ''.join(chars)
            compact_pairs = [(c, p) for c, p in zip(chars, positions) if not c.isspace()]
            variants = [(normal, positions, needle),
                        (''.join(c for c, _ in compact_pairs),
                         [p for _, p in compact_pairs], ''.join(needle.split()))]
            # Collect both variants: a clean contents match must not suppress
            # an extraction-artifact match elsewhere on the same page.
            for text, offsets, search in variants:
                for match in re.finditer('(?=' + re.escape(search) + ')', text):
                    start, end = match.start(), match.start() + len(search)
                    original = offsets[start]
                    if identifier:
                        # Avoid 4. matching inside 14., and (1) inside (10).
                        before = page.text[original - 1] if original else ''
                        after_index = offsets[end - 1] + 1
                        after = page.text[after_index:after_index + 1]
                        if before.isalnum() or (search[-1].isalnum() and after.isalnum()):
                            continue
                    found.add((page.page_number, original))
        return sorted(found)

    @staticmethod
    def _ordered(nodes):
        by_parent = defaultdict(list)
        lookup = {n.id: n for n in nodes}
        if len(lookup) != len(nodes):
            raise ValueError('Duplicate hierarchy node IDs.')
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in lookup:
                raise ValueError('Missing hierarchy parent.')
            by_parent[node.parent_id].append(node)
        for siblings in by_parent.values():
            if len({n.sequence_no for n in siblings}) != len(siblings):
                raise ValueError('Ambiguous sibling sequence numbers.')
            siblings.sort(key=lambda n: n.sequence_no)
        ordered, visited = [], set()

        def visit(node):
            if node.id in visited:
                raise ValueError('Cyclic hierarchy.')
            visited.add(node.id)
            ordered.append(node)
            for child in by_parent[node.id]:
                visit(child)
        for root in by_parent[None]:
            visit(root)
        if len(visited) != len(nodes):
            raise ValueError('Cyclic or disconnected hierarchy.')
        return ordered, by_parent, lookup

    def map_document(self, document, page_hints=None):
        nodes = self.repository.get_by_document(document.id)
        ordered, children, lookup = self._ordered(nodes)
        if not document.pages:
            raise ValueError('Cannot map an empty document.')
        first = min(document.pages, key=lambda p: p.page_number)
        last = max(document.pages, key=lambda p: p.page_number)
        document_end = (last.page_number, len(last.text))
        domains, reasons = {}, {}
        for node in ordered:
            node.start_page = node.start_character = node.end_page = None
            if node.node_type.upper() == 'TABLE':
                continue
            anchor = (node.title or '').strip() or (node.identifier or '').strip()
            if anchor:
                search_pages = document.pages
                if page_hints is not None:
                    hint = page_hints.get(node.id)
                    search_pages = [p for p in document.pages
                                    if type(hint) is int and p.page_number == hint]
                domains[node.id] = [p for p in self._matches(
                    anchor, search_pages, identifier=not bool((node.title or '').strip()))
                    if p < document_end]
                if not domains[node.id]:
                    reasons[node.id] = 'text not found'
        initial_counts = {key: len(value) for key, value in domains.items()}
        title_anchor = None
        roots = children[None]
        if len(roots) == 1 and roots[0].node_type.upper() == 'DOCUMENT':
            root_children = children[roots[0].id]
            if root_children:
                first_child = root_children[0]
                if (first_child.node_type.upper() == 'HEADING'
                        and (first_child.title or '').strip()
                        and domains.get(first_child.id)):
                    domains[first_child.id] = domains[first_child.id][:1]
                    title_anchor = {'id': first_child.id, 'title': first_child.title,
                                    'position': domains[first_child.id][0],
                                    'rule': 'earliest document-title occurrence'}
        # Arc consistency across DFS order enforces parent-before-descendant,
        # preceding-subtree-before-next-sibling, and strictly distinct anchors.
        # Missing/conflicting nodes are deferred rather than halting other work.
        changed = True
        while changed:
            changed = False
            active = [n for n in ordered if domains.get(n.id)]
            for left, right in zip(active, active[1:]):
                a, b = domains[left.id], domains[right.id]
                supported_a = [p for p in a if p < b[-1]]
                supported_b = [p for p in b if p > a[0]]
                if not supported_a or not supported_b:
                    domains[left.id] = domains[right.id] = []
                    reasons[left.id] = reasons[right.id] = 'conflicting hierarchy order'
                    changed = True
                    break
                if supported_a != a or supported_b != b:
                    domains[left.id], domains[right.id] = supported_a, supported_b
                    changed = True
        for node in ordered:
            candidates = domains.get(node.id, [])
            if len(candidates) == 1:
                node.start_page, node.start_character = candidates[0]
            elif candidates:
                reasons[node.id] = 'multiple hierarchy-consistent locations'

        def position(node):
            if node.start_page is None or node.start_character is None:
                return None
            return node.start_page, node.start_character

        def end(node):
            siblings = children[node.parent_id]
            for sibling in siblings[siblings.index(node) + 1:]:
                if position(sibling) is not None:
                    return position(sibling)
            return end(lookup[node.parent_id]) if node.parent_id is not None else document_end

        # Descendants of unresolved searchable parents must not be accepted
        # using an unknown parent range, even if they have a unique text match.
        for node in ordered:
            parent = lookup.get(node.parent_id)
            if parent is not None and parent.id in reasons:
                node.start_page = node.start_character = None
                reasons[node.id] = 'parent unresolved'
            if node.id not in domains and node.node_type.upper() != 'TABLE':
                node.start_page = parent.start_page if parent else first.page_number
            start = position(node)
            if start is not None:
                boundary = end(node)
                if boundary <= start:
                    node.start_page = node.start_character = None
                    reasons[node.id] = 'empty or reversed boundary'
                else:
                    node.end_page = boundary[0]
            elif node.id not in domains and parent and parent.end_page is not None:
                node.start_page, node.end_page = parent.start_page, parent.end_page
            elif node.id not in domains and parent is None:
                node.end_page = last.page_number
        # Structural parents need ranges before table inheritance.
        for node in ordered:
            if node.id not in domains and node.end_page is None and node.id not in reasons:
                node.end_page = end(node)[0]
        for node in ordered:
            if node.node_type.upper() == 'TABLE':
                parent = lookup.get(node.parent_id)
                if parent and parent.id not in reasons:
                    node.start_page, node.end_page = parent.start_page, parent.end_page
        self.last_report = {
            'document_title_anchor': title_anchor,
            'resolved': sum(position(n) is not None for n in ordered if n.id in domains),
            'unresolved': [{'id': n.id, 'title': n.title, 'identifier': n.identifier,
                            'reason': reasons[n.id], 'initial_candidates': initial_counts.get(n.id, 0),
                            'remaining_candidates': domains.get(n.id, [])}
                           for n in ordered if n.id in reasons],
        }
        # Persist NULLs as well: stale old boundaries must not survive deferral.
        for node in nodes:
            self.repository.update_page_range(node_id=node.id, start_page=node.start_page,
                start_character=node.start_character, end_page=node.end_page)
        return self.last_report
