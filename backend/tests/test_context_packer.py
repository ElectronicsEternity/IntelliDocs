"""Prove prompt compaction shares labels, not distinct legal provisions."""
from copy import deepcopy

from app.rag.context_packer import pack_context, provision_text


def chunk(body, *, node="node-a", doc="doc-a", identifier="(a)", path=None):
    path = path or ["Employment Act", "Working hours", identifier]
    return {"chunk_id": node, "node_id": node, "document_id": doc,
            "document_title": "Act", "node_type": "CLAUSE", "identifier": identifier,
            "content_type": "text", "metadata": {"hierarchy_path": path, "page_numbers": [57]},
            "text": "Document: Act\nHierarchy: " + " > ".join(path) + "\n" + body}


def test_shared_labels_preserve_all_citations_and_text_without_mutation():
    chunks = [chunk("First condition."), chunk("Second condition.", node="node-b", identifier="(b)")]
    original = deepcopy(chunks)
    context, audit = pack_context(chunks)
    assert context.count("Source: Act") == 1
    assert context.count("Working hours") == 1
    assert "Identifier: (a)" in context and "Identifier: (b)" in context
    assert "First condition." in context and "Second condition." in context
    assert "Document: Act" not in context
    assert chunks == original
    assert audit["evidence_count"] == 2


def test_exact_same_node_overlap_retains_a_citation_for_each_chunk():
    small, large = chunk("Required break."), chunk("Required break. Additional exception.")
    large["chunk_id"] = "split-2"
    context, audit = pack_context([small, large])
    assert context.count("Required break.") == 1
    assert "Additional exception." in context
    assert "Included verbatim in E2 (same provision)." in context
    assert audit["reused_bodies"] == 1
    assert audit["evidence_mapping"] == [
        {"evidence": "E1", "chunk_id": "node-a", "text_evidence": "E2"},
        {"evidence": "E2", "chunk_id": "split-2", "text_evidence": "E2"},
    ]


def test_ancestor_chunk_is_not_assumed_to_contain_children():
    parent = chunk("Working hours heading", node="parent", identifier="60A", path=["Working hours"])
    child = chunk("Required break", path=["Working hours", "(a)"])
    context, audit = pack_context([parent, child])
    assert "Text: Working hours heading" in context
    assert "Text: Required break" in context
    assert audit["reused_bodies"] == 0


def test_equal_text_in_distinct_provisions_is_not_removed():
    context, audit = pack_context([chunk("Omitted."), chunk("Omitted.", node="node-b", identifier="(b)")])
    assert context.count("Text: Omitted.") == 2
    assert audit["reused_bodies"] == 0


def test_document_ids_isolate_matching_titles_and_nodes():
    context, audit = pack_context([chunk("Required break."), chunk("Required break.", doc="doc-b")])
    assert context.count("Text: Required break.") == 2
    assert "D1: Source: Act" in context and "D2: Source: Act" in context
    assert audit["reused_bodies"] == 0


def test_missing_node_or_document_identity_never_guesses_overlap():
    a, b = chunk("Required break."), chunk("Required break.")
    a.pop("node_id")
    b.pop("node_id")
    assert pack_context([a, b])[1]["reused_bodies"] == 0
    a, b = chunk("Required break."), chunk("Required break.")
    a.pop("document_id")
    b.pop("document_id")
    assert pack_context([a, b])[1]["reused_bodies"] == 0


def test_only_metadata_verified_search_prefixes_are_removed():
    a = chunk("Document: a literal provision line\nHierarchy: a literal provision line")
    assert provision_text(a) == "Document: a literal provision line\nHierarchy: a literal provision line"
    a["text"] = "Document: Another title\nHierarchy: Other\nOriginal provision"
    assert provision_text(a) == a["text"]


def test_table_cells_and_geometry_and_citation_metadata_are_preserved():
    table = chunk("unused")
    table.update(content_type="table", node_type="TABLE", identifier="", node_title="First Schedule")
    table["text"] = "Document: Act. Table number: 2. Pages: 112, 113. Row 1: columns 1-1: RM4,000; columns 2-3: exceeds one-half."
    context, _ = pack_context([table])
    assert "Text: Table number: 2. Pages: 112, 113." in context
    assert "Row 1: columns 1-1: RM4,000; columns 2-3: exceeds one-half." in context
    assert "Node title: First Schedule" in context


def test_shared_reference_legend_preserves_direction_and_endpoint():
    a, b = chunk("First."), chunk("Second.", node="node-b", identifier="(b)")
    link = {"direction": "incoming", "source_node_id": "schedule", "target_node_id": "section",
            "reference": {"node_type": "SECTION", "identifier": "60A", "sub_identifier": "(3)"}}
    a["reference_links"] = [link, link]
    b["reference_links"] = [link]
    context, _ = pack_context([a, b])
    assert context.count("Printed reference connection (incoming): SECTION 60A(3)") == 1
    assert context.count("Printed references: R1") == 2


def test_partial_overlap_without_full_containment_keeps_both_bodies():
    context, audit = pack_context([chunk("First sentence. Shared sentence."),
                                  chunk("Shared sentence. Final sentence.")])
    assert "Text: First sentence. Shared sentence." in context
    assert "Text: Shared sentence. Final sentence." in context
    assert audit["reused_bodies"] == 0
