from pathlib import Path
from statistics import mean, median

from app.database.database import Database
from app.indexing.node_scope_extractor import NodeScopeExtractor
from app.indexing.node_scope_token_counter import NodeScopeTokenCounter
from app.ingestion.parser import PDFParser
from app.rag.tokenizer import Tokenizer
from app.repositories.document_node_repository import DocumentNodeRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf"
)

TEST_DOCUMENT_ID = "40cbd327-0728-4803-b0a4-be7e85e52b8d"


def main():
    db = Database()
    repository = DocumentNodeRepository(db)
    scope_extractor = NodeScopeExtractor()
    tokenizer = Tokenizer()
    token_counter = NodeScopeTokenCounter(tokenizer)

    # Load the real mapped nodes and real PDF text.
    nodes = repository.get_by_document(TEST_DOCUMENT_ID)

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Save current database values so the test can detect any changes.
    database_values_before = {
        node.id: (node.start_page, node.start_character, node.end_page)
        for node in nodes
    }

    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id="dev_user")

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes loaded: {len(nodes)}")
    print("\n=== Node Scope Token Counting Started ===")

    # Extract non-overlapping text owned by every titled node.
    scopes = scope_extractor.extract_node_scopes(document, nodes)
    counted_scopes = token_counter.count_scope_tokens(scopes)

    scope_token_counts = [scope["token_count"] for scope in counted_scopes]
    scopes_with_no_tokens = []

    # The playground now inspects results returned by production code.
    for index, scope in enumerate(counted_scopes):
        token_count = scope["token_count"]

        # A real titled scope should always contain at least one token.
        if token_count == 0:
            scopes_with_no_tokens.append(scope)

        display_title = scope["title"] or scope["identifier"]

        # Limit only the terminal display; the real title remains unchanged.
        if len(display_title) > 80:
            display_title = f"{display_title[:80]}..."

        print(
            f"Scope {index + 1} | {scope['node_type']} | "
            f"depth={scope['depth']} | sequence={scope['sequence_no']} | "
            f"identifier={scope['identifier'] or '-'} | "
            f"start={scope['start_page']}:{scope['start_character']} | "
            f"end={scope['end_page']}:{scope['end_character']} | "
            f"tokens={token_count} | anchor={display_title}"
        )

    print("=== Node Scope Token Counting Ended ===\n")

    print("Results:")
    print(f"Scopes counted: {len(scope_token_counts)}")
    print(f"Scopes with zero tokens: {len(scopes_with_no_tokens)}")

    if scope_token_counts:
        print(f"Minimum tokens: {min(scope_token_counts)}")
        print(f"Average tokens: {mean(scope_token_counts):.2f}")
        print(f"Median tokens: {median(scope_token_counts):.2f}")
        print(f"Maximum tokens: {max(scope_token_counts)}")
        print(f"Total scope tokens: {sum(scope_token_counts)}")
        print(f"Sorted token counts: {sorted(scope_token_counts)}")

    # Reload nodes and compare them with the values captured before the test.
    nodes_after_test = repository.get_by_document(TEST_DOCUMENT_ID)
    database_values_after = {
        node.id: (node.start_page, node.start_character, node.end_page)
        for node in nodes_after_test
    }

    database_unchanged = database_values_after == database_values_before
    print(f"Database unchanged: {database_unchanged}")


if __name__ == "__main__":
    main()
