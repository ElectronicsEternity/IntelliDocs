"""Resolve printed references locally, within one owned document, one hop only."""
from collections import defaultdict
import re


def base_key(value):
    # Printed prefixes such as PART XII are labels, not part of the base ID.
    value = re.sub(r"^(PART|SECTION|CHAPTER|ARTICLE)\s+", "", value, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", value.lower())


def child_key(value):
    # Keep structural boundaries: subsection (1A) differs from clause (1)(a).
    return re.sub(r"\s+", "", value).lower().rstrip(".")


class ReferenceGraph:
    def __init__(self, nodes):
        self.nodes = {str(node["id"]): node for node in nodes}
        self.children = defaultdict(list)
        for node_id, node in self.nodes.items():
            self.children[str(node["parent_id"])].append(node_id)
        self.index = defaultdict(list)
        for node_id in self.nodes:
            chain = self.ancestors(node_id)
            # Index both whole provisions and every actual descendant path.
            for position, base_id in enumerate(chain):
                base = self.nodes[base_id]
                child_path = "".join(self.nodes[item]["identifier"] for item in chain[position + 1:])
                address = (base["node_type"], base_key(base["identifier"]), child_key(child_path))
                self.index[address].append(node_id)

    def ancestors(self, node_id):
        chain, seen = [], set()
        while node_id in self.nodes and node_id not in seen:
            seen.add(node_id)
            chain.append(node_id)
            node_id = str(self.nodes[node_id]["parent_id"])
        return list(reversed(chain))

    def descendants(self, node_id):
        found, pending = set(), [node_id]
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending.extend(self.children[current])
        return found

    def linked_nodes(self, seed_ids):
        seeds = {str(item) for item in seed_ids if str(item) in self.nodes}
        # Ancestor references govern selected children as well as their parent.
        scope = {item for seed in seeds for item in self.ancestors(seed)}
        additions = defaultdict(list)
        unresolved = []
        for source_id, node in self.nodes.items():
            for reference in node.get("references", []):
                address = (reference["node_type"], base_key(reference["identifier"]),
                           child_key(reference["sub_identifier"] or ""))
                matches = self.index.get(address, [])
                if len(matches) != 1:
                    # Duplicate targets or absent excerpt targets are not guessed.
                    if source_id in scope:
                        unresolved.append({"source_node_id": source_id, "reference": reference,
                                           "reason": "ambiguous" if matches else "missing"})
                    continue
                target_id = matches[0]
                if source_id in scope:
                    # Whole-section references include the target's children.
                    for linked_id in self.descendants(target_id):
                        additions[linked_id].append({"direction": "outgoing", "source_node_id": source_id,
                                                     "target_node_id": target_id, "reference": reference})
                if target_id in scope:
                    # Reverse lookup brings the provision containing the citation.
                    for linked_id in self.descendants(source_id):
                        additions[linked_id].append({"direction": "incoming", "source_node_id": source_id,
                                                     "target_node_id": target_id, "reference": reference})
        # Do not follow references on these additions: this is strictly one hop.
        return dict(additions), unresolved
