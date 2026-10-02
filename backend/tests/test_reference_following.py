"""Reference lookup is structural, bidirectional, same-document and one hop."""
from app.rag.reference_graph import ReferenceGraph
from app.indexing.hierarchy_importer import HierarchyImporter


def node(id, type, identifier, parent=None, references=None):
    return {"id": id, "node_type": type, "identifier": identifier,
            "parent_id": parent, "references": references or []}


def ref(identifier, sub=None):
    return {"node_type": "SECTION", "identifier": identifier, "sub_identifier": sub}


def test_reverse_schedule_link_and_forward_subtree():
    graph = ReferenceGraph([node("root", "DOCUMENT", ""),
        node("section", "SECTION", "60A.", "root"),
        node("sub", "SUBSECTION", "(3)", "section"),
        node("clause", "CLAUSE", "(a)", "sub"),
        node("schedule", "SCHEDULE", "FIRST SCHEDULE", "root"),
        node("table", "TABLE", "", "schedule", [ref("60A", "(3)")])])
    incoming, errors = graph.linked_nodes(["clause"])
    assert "table" in incoming and not errors
    assert incoming["table"][0]["direction"] == "incoming"
    outgoing, errors = graph.linked_nodes(["table"])
    assert {"sub", "clause"}.issubset(outgoing) and not errors


def test_subsection_letters_are_not_clause_paths():
    graph = ReferenceGraph([node("section", "SECTION", "60A."),
        node("1", "SUBSECTION", "(1)", "section"),
        node("a", "CLAUSE", "(a)", "1"),
        node("1a", "SUBSECTION", "(1A)", "section"),
        node("source", "SECTION", "7.", references=[ref("60A", "(1A)")])])
    linked, errors = graph.linked_nodes(["source"])
    assert "1a" in linked and "a" not in linked and not errors


def test_missing_and_ambiguous_targets_are_not_guessed():
    graph = ReferenceGraph([node("one", "SECTION", "2."), node("two", "SECTION", "2."),
        node("source", "SECTION", "3.", references=[ref("2"), ref("99")])])
    linked, errors = graph.linked_nodes(["source"])
    assert not linked
    assert {error["reason"] for error in errors} == {"missing", "ambiguous"}


def test_reference_additions_do_not_recursively_follow_more_links():
    graph = ReferenceGraph([node("a", "SECTION", "1", references=[ref("2")]),
                           node("b", "SECTION", "2", references=[ref("3")]),
                           node("c", "SECTION", "3")])
    linked, _ = graph.linked_nodes(["a"])
    assert "b" in linked and "c" not in linked


def test_importer_retains_node_references_for_persistence():
    hierarchy = {"type": "DOCUMENT", "identifier": "", "title": "", "children": [
        {"type": "SECTION", "identifier": "1.", "title": "Scope",
         "references": [ref("2")], "children": []}]}
    importer = HierarchyImporter(None)
    nodes = importer.build_nodes("document", hierarchy)
    assert nodes[1].references == [ref("2")]
    assert nodes[0].references == []


def test_reference_store_scopes_both_queries_and_deduplicates_chunks():
    from app.storage.postgres_vector_store import PostgresVectorStore

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement, parameters):
            assert "d.user_id = %s" in statement
            assert parameters[:2] == ("doc-a", "owner-a")
            self.statement = statement

        def fetchall(self):
            if "n.hierarchy_references" in self.statement:
                return [("section", None, "SECTION", "60A.", []),
                        ("sub", "section", "SUBSECTION", "(3)", []),
                        ("table", None, "TABLE", "", [ref("60A", "(3)")])]
            return [("linked", "doc-a", "table", "table", "Schedule restriction", {},
                     "Akta", "akta.pdf", "TABLE", "", "", 0.0)]

    class Connection:
        def cursor(self):
            return Cursor()

    store = PostgresVectorStore.__new__(PostgresVectorStore)
    store.connection = Connection()
    selected = [{"chunk_id": "original", "document_id": "doc-a", "node_id": "sub"}]
    expanded = store.expand_references(owner_id="owner-a", chunks=selected)
    assert [chunk["chunk_id"] for chunk in expanded] == ["original", "linked"]
    assert expanded[1]["reference_links"][0]["direction"] == "incoming"


def test_repository_persists_json_reference_metadata_with_owner_guard():
    import json
    from app.repositories.document_node_repository import DocumentNodeRepository
    from app.models.document_node import DocumentNode

    class Database:
        def execute(self, statement, parameters):
            assert "hierarchy_references" in statement
            assert "user_id = %s" in statement
            assert len(parameters) == statement.count("%s")
            assert json.loads(parameters[11]) == [ref("2")]
            assert parameters[-2:] == ("doc", "owner")

    document_node = DocumentNode("node", "doc", None, "SECTION", "1", "Scope", 0, 0,
                                 references=[ref("2")])
    DocumentNodeRepository(Database(), "owner").create(document_node)
