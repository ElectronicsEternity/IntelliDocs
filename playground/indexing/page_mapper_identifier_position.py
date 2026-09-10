# ========================================
# File: page_mapper_identifier_position.py
# ========================================
#
# Purpose
# -------
# Test identifier mapping for real untitled DocumentNode records.
#
# Responsibilities
# ----------------
# - Load the mapped hierarchy from PostgreSQL.
# - Extract the real PDF through the configured parser.
# - Map untitled nodes using identifiers and parent boundaries.
# - Validate identifier text, sibling order, and database safety.
#
# ========================================

# Import Path for locating the test PDF.
from pathlib import Path

# Import the database connection wrapper.
from app.database.database import Database

# Import the production PageMapper being tested.
from app.indexing.page_mapper import PageMapper

# Import reusable production mapping checks.
from app.indexing.page_mapping_validator import (
    PageMappingValidator,
)

# Import the configured PDF parser facade.
from app.ingestion.parser import PDFParser

# Import the repository used to load real hierarchy records.
from app.repositories.document_node_repository import DocumentNodeRepository


# ==========================================================
# Test Configuration
# ==========================================================

# Locate the project root from this Playground file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Select the PDF already connected to the test hierarchy.
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf"
)

# Select the real document hierarchy stored in PostgreSQL.
TEST_DOCUMENT_ID = "40cbd327-0728-4803-b0a4-be7e85e52b8d"


# ==========================================================
# Test Execution
# ==========================================================

# Run the identifier-position mapping test.
def main():

    # Create the database wrapper.
    db = Database()

    # Create the real DocumentNode repository.
    repository = DocumentNodeRepository(db)

    # Create the production PageMapper under test.
    mapper = PageMapper(repository)

    # Create the reusable production validator.
    validator = PageMappingValidator()

    # Load the real hierarchy records from PostgreSQL.
    nodes = repository.get_by_document(TEST_DOCUMENT_ID)

    # Stop clearly when the selected document has no hierarchy.
    if not nodes:
        print("No DocumentNode records found.")
        return

    # Preserve database positions so the test can prove it does not save.
    database_positions_before = {
        node.id: (node.start_page, node.start_character, node.end_page)
        for node in nodes
    }

    # Extract the PDF using the currently configured parser adapter.
    document = PDFParser(PDF_FILE).extract_text(owner_id="dev_user")

    # Build quick page-number access for identifier text verification.
    pages_by_number = {
        page.page_number: page
        for page in document.pages
    }

    # Select only untitled nodes that provide searchable identifiers.
    identifier_nodes = [
        node
        for node in nodes
        if (
            (not node.title or not node.title.strip())
            and node.identifier
            and node.identifier.strip()
        )
    ]

    # Display the test input before mapping begins.
    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes loaded: {len(nodes)}")
    print(f"Untitled identifier nodes: {len(identifier_nodes)}")

    # Select a known titled parent for focused boundary testing.
    example_parent = next(
        node
        for node in nodes
        if node.title == "Nama dan permulaan kuat kuasa"
    )

    # Load its ordered subsection children for focused identifier testing.
    example_children = mapper._get_children(
        parent_id=example_parent.id,
        nodes=nodes
    )

    # Select subsection (1) as the focused identifier example.
    example_child = example_children[0]

    # Require a complete titled-parent position before focused testing.
    if example_parent.start_page is None or example_parent.start_character is None:
        raise ValueError("The focused parent has no complete start position.")

    # Copy narrowed integer values for clear function arguments.
    example_parent_start_page = example_parent.start_page
    example_parent_start_character = example_parent.start_character

    # Mark the beginning of the parent-end-boundary function test.
    print("\n=== _get_node_end_position() Started ===")

    # Ask production PageMapper where the selected section ends.
    example_parent_end = mapper._get_node_end_position(
        node=example_parent,
        nodes=nodes,
        document=document
    )

    # Load the selected section's ordered siblings.
    parent_siblings = mapper._get_children(
        parent_id=example_parent.parent_id,
        nodes=nodes
    )

    # Find the selected section inside its sibling list.
    example_parent_index = parent_siblings.index(example_parent)

    # The next section should supply the selected section's end boundary.
    next_parent_sibling = parent_siblings[example_parent_index + 1]

    # Build the expected end position from the next section's start.
    expected_parent_end = (
        next_parent_sibling.start_page,
        next_parent_sibling.start_character
    )

    # Confirm that production boundary calculation found the expected position.
    parent_end_correct = example_parent_end == expected_parent_end

    # Display the calculated and expected parent boundaries.
    print(f"Parent: {example_parent.title}")
    print(f"Calculated end: {example_parent_end}")
    print(f"Expected end: {expected_parent_end}")
    print(f"Boundary correct: {parent_end_correct}")
    print("=== _get_node_end_position() Ended ===")

    # Mark the beginning of the focused identifier-search function test.
    print("\n=== _find_identifier_position() Started ===")

    # Search for subsection (1) only inside its selected parent section.
    focused_identifier_position = mapper._find_identifier_position(
        identifier=example_child.identifier,
        pages=document.pages,
        start_page=example_parent_start_page,
        start_character=example_parent_start_character,
        end_page=example_parent_end[0],
        end_character=example_parent_end[1]
    )

    # Begin with a failed result until a complete position is verified.
    focused_identifier_correct = False

    # Verify the original PDF text when the identifier was found.
    if focused_identifier_position is not None:

        # Load the page containing the focused identifier.
        focused_page = pages_by_number[focused_identifier_position["page_number"]]

        # Read original text beginning at the returned character position.
        focused_text = focused_page.text[
            focused_identifier_position["start_character"]:
        ]

        # Ignore layout whitespace while comparing the returned identifier.
        focused_identifier_correct = "".join(
            focused_text.lower().split()
        ).startswith("".join(example_child.identifier.lower().split()))

    # Display the focused identifier result.
    print(f"Identifier: {example_child.identifier}")
    print(f"Position: {focused_identifier_position}")
    print(f"Identifier text correct: {focused_identifier_correct}")
    print("=== _find_identifier_position() Ended ===")

    # Mark the beginning of complete untitled-node mapping.
    print("\n=== Identifier Position Mapping Started ===")

    # Map identifier positions only in memory through production PageMapper.
    mapper._map_identifier_nodes(document=document, nodes=nodes)

    # Mark the end of production identifier mapping output.
    print("=== Identifier Position Mapping Ended ===\n")

    # Run reusable position checks through production code.
    result = validator.validate(
        document=document,
        nodes=nodes,
    )

    # Limit summary results to identifier nodes in this test.
    identifier_ids = {node.id for node in identifier_nodes}
    missing_positions = [
        node
        for node in result.missing_anchor_nodes
        if node.id in identifier_ids
    ]
    identifier_mismatches = [
        node
        for node in result.anchor_text_mismatches
        if node.id in identifier_ids
    ]

    # Inspect every identifier-bearing untitled node individually.
    for node in identifier_nodes:

        # Skip positions already reported as incomplete.
        if node.start_page is None or node.start_character is None:
            continue

        # Load the original page containing the mapped identifier.
        page = pages_by_number[node.start_page]

        # Read a short original-text sample beginning at the mapped position.
        text_sample = page.text[node.start_character:node.start_character + 50]

        # Collapse layout whitespace only for readable terminal output.
        display_sample = " ".join(text_sample.split())

        # Display the mapped location and the original text found there.
        print(
            f"{node.node_type} | depth={node.depth} | "
            f"sequence={node.sequence_no} | identifier={node.identifier} | "
            f"start={node.start_page}:{node.start_character} | "
            f"text='{display_sample}'"
        )

    # Select the final subsection to exercise recursive boundary lookup.
    final_example_child = example_children[-1]

    # The final child should recursively inherit its parent's end position.
    recursive_child_end = mapper._get_node_end_position(
        node=final_example_child,
        nodes=nodes,
        document=document
    )

    # Confirm recursive lookup reaches the same section boundary.
    recursive_boundary_correct = recursive_child_end == example_parent_end

    # Select nodes that cannot be anchored through title or identifier text.
    unanchored_nodes = [
        node
        for node in nodes
        if (
            (not node.title or not node.title.strip())
            and (not node.identifier or not node.identifier.strip())
            and node.start_character is None
        )
    ]

    # Reload fresh objects to verify that the test made no database writes.
    nodes_after_test = repository.get_by_document(TEST_DOCUMENT_ID)

    # Capture persisted positions after the in-memory mapping test.
    database_positions_after = {
        node.id: (node.start_page, node.start_character, node.end_page)
        for node in nodes_after_test
    }

    # Compare the before and after snapshots for exact equality.
    database_unchanged = database_positions_after == database_positions_before

    # Display the complete test summary.
    print("\nResults:")
    print(f"Identifier nodes tested: {len(identifier_nodes)}")
    print(f"Identifier positions mapped: {len(identifier_nodes) - len(missing_positions)}")
    print(f"Identifier positions missing: {len(missing_positions)}")
    print(f"Identifier text mismatches: {len(identifier_mismatches)}")
    print(
        "Physical order violations: "
        f"{len(result.order_violations)}"
    )
    print(
        "Parent boundary violations: "
        f"{len(result.parent_position_violations)}"
    )
    print(f"Focused parent boundary correct: {parent_end_correct}")
    print(f"Focused identifier search correct: {focused_identifier_correct}")
    print(f"Recursive final-child boundary correct: {recursive_boundary_correct}")
    print(f"Nodes without title or identifier: {len(unanchored_nodes)}")
    print(f"Database unchanged: {database_unchanged}")


# ==========================================================
# Entry Point
# ==========================================================

# Run this Playground test only when executed directly as a module.
if __name__ == "__main__":
    main()
