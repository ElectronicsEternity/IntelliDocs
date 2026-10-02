"""Seed only the verified First Schedule references and replay retrieval for free."""
import argparse
import json
from pathlib import Path
import sys
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.storage.postgres_vector_store import PostgresVectorStore
from app.rag.retriever import Retriever

OWNER = "3a9eaaa6-1dee-4be7-b78c-371e16944a01"
DOCUMENT = "69b2ea9c-594c-47fc-8db8-76a399ab6140"
FOLDER = ROOT / "logs/diagnostics/hierarchy_references_v1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    hierarchy = json.loads((FOLDER / "hierarchy.json").read_text(encoding="utf-8"))
    schedule = next(node for node in hierarchy["children"] if node["identifier"] == "FIRST SCHEDULE")
    # Only explicit printed target citations are seeded. A self-reference and
    # relative paragraph reference in the table do not add useful destinations.
    table = next(node for node in schedule["children"] if node["type"] == "TABLE")
    table_refs = [ref for ref in table["references"] if ref["node_type"] != "SCHEDULE"]
    store = PostgresVectorStore()
    try:
        with store.connection.cursor() as cursor:
            cursor.execute("""
                SELECT n.id, n.parent_id, n.node_type, n.identifier, n.title,
                       n.start_page, n.end_page, n.hierarchy_references
                FROM document_nodes n JOIN documents d ON d.id=n.document_id
                WHERE d.id=%s AND d.user_id=%s AND
                    (n.node_type='SCHEDULE' OR n.id IN (
                        SELECT node_id FROM chunks WHERE id=%s AND document_id=%s))
            """, (DOCUMENT, OWNER, "37898d42-f86a-4155-a550-856acc27f370", DOCUMENT))
            rows = cursor.fetchall()
            first = [row for row in rows if row[2] == "SCHEDULE" and
                     "FIRST SCHEDULE" in (row[3] + " " + row[4]).upper()]
            tables = [row for row in rows if row[2] == "TABLE"]
            assert len(first) == len(tables) == 1, "Ambiguous node ownership; refusing seed"
            assert tables[0][1] == first[0][0], "Table is not under First Schedule"
            assert tables[0][5] == 112 and tables[0][6] == 113
            replacements = [(first[0], schedule["references"]), (tables[0], table_refs)]
            backup = FOLDER / "first_schedule_references_before_seed.json"
            if args.apply:
                # Preserve the original metadata before any mutation; reruns
                # never overwrite the backup with already-seeded data.
                if not backup.exists():
                    backup.write_text(json.dumps([{"node_id": str(row[0]), "references": row[7]}
                                                 for row, _ in replacements], indent=2), encoding="utf-8")
                for row, references in replacements:
                    cursor.execute("""
                        UPDATE document_nodes SET hierarchy_references=%s
                        WHERE id=%s AND document_id=%s AND EXISTS (
                            SELECT 1 FROM documents WHERE id=%s AND user_id=%s)
                    """, (Jsonb(references), row[0], DOCUMENT, DOCUMENT, OWNER))
                    assert cursor.rowcount == 1
                store.commit()
            else:
                print("Read-only replay; no seed changes")

        saved = json.loads((ROOT / "logs/diagnostics/section60a_question_vector.json").read_text(encoding="utf-8"))
        class SavedEmbedder:
            def generate_embedding(self, question):
                assert question == saved["question"]
                return saved["embedding"]
        chunks = Retriever(SavedEmbedder(), store).retrieve(saved["question"], OWNER)
        linked = [chunk for chunk in chunks if "reference_following" in chunk.get("match_types", [])]
        schedule_table = next(chunk for chunk in chunks if chunk["chunk_id"] == "37898d42-f86a-4155-a550-856acc27f370")
        assert any(link["direction"] == "incoming" and link["reference"]["identifier"] == "60A"
                   and link["reference"]["sub_identifier"] == "(3)"
                   for link in schedule_table["reference_links"])
        report = {"question": saved["question"], "api_calls": 0, "chunk_count": len(chunks),
                  "reference_chunk_count": len(linked), "first_schedule_table_included": True,
                  "chunks": chunks}
        (FOLDER / "live_retrieval_replay.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "chunks"}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
