from app.database.database import Database
from app.indexing.hierarchy_validator import (
    HierarchyValidator,
)
from app.indexing.page_mapper import PageMapper
from app.repositories.document_node_repository import (
    DocumentNodeRepository,
)


# Existing document whose hierarchy is already stored in PostgreSQL.
TEST_DOCUMENT_ID = "40cbd327-0728-4803-b0a4-be7e85e52b8d"


def print_function_start(function_name):
    # Clearly mark where a function test begins in the terminal.
    print("\n" + "=" * 60)
    print(f"START: {function_name}")
    print("=" * 60)


def print_function_end(function_name):
    # Clearly mark where a function test finishes in the terminal.
    print("=" * 60)
    print(f"END: {function_name}")
    print("=" * 60)


def print_branch(mapper, node, nodes, indent=0):
    # Ask PageMapper for this node's children in sequence_no order.
    children = mapper._get_children(
        parent_id=node.id,
        nodes=nodes,
    )

    # Limit only the printed title. The real node title is unchanged.
    display_title = node.title or "[no title]"

    if len(display_title) > 40:
        display_title = f"{display_title[:37]}..."

    print(
        f"{'  ' * indent}"
        f"{node.node_type} | "
        f"depth={node.depth} | "
        f"sequence={node.sequence_no} | "
        f"identifier={node.identifier or '-'} | "
        f"start={node.start_page or '-'}:"
        f"{node.start_character if node.start_character is not None else '-'} | "
        f"end_page={node.end_page or '-'} | "
        f"children={len(children)} | "
        f"title={display_title}"
    )

    # Recursively print each descendant to show the complete hierarchy.
    for child in children:
        print_branch(
            mapper=mapper,
            node=child,
            nodes=nodes,
            indent=indent + 1,
        )


def main():
    # Database -> repository -> PageMapper.
    db = Database()
    repository = DocumentNodeRepository(db)
    mapper = PageMapper(repository)
    validator = HierarchyValidator()

    # Load real DocumentNode records instead of creating fake nodes.
    nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"Nodes loaded: {len(nodes)}")

    if not nodes:
        print("No DocumentNode records found.")
        return

    # TEST 1A: Create an id -> DocumentNode lookup dictionary.
    print_function_start("PageMapper._build_node_lookup()")

    node_lookup = mapper._build_node_lookup(nodes)

    print(f"Lookup entries: {len(node_lookup)}")

    print_function_end("PageMapper._build_node_lookup()")

    # TEST 1B: Check children and print the complete hierarchy.
    print_function_start("PageMapper._get_children()")

    # Root nodes have no parent. Sort them by their sibling sequence.
    root_nodes = sorted(
        [node for node in nodes if node.parent_id is None],
        key=lambda node: node.sequence_no,
    )

    # Get every parent's children through the PageMapper method under test.
    children_by_parent = {}

    for node in nodes:
        children = mapper._get_children(
            parent_id=node.id,
            nodes=nodes,
        )

        children_by_parent[node.id] = children

    # Run the reusable production hierarchy checks.
    result = validator.validate(
        nodes=nodes,
        node_lookup=node_lookup,
        children_by_parent=children_by_parent,
    )

    print(f"Root nodes: {len(root_nodes)}")
    print(
        "Every node is indexed correctly: "
        f"{result.every_node_indexed}"
    )
    print(
        "Hierarchy preserved: "
        f"{result.hierarchy_preserved}"
    )
    print(
        "Sibling order preserved: "
        f"{result.sibling_order_preserved}"
    )
    print(
        "Missing parents: "
        f"{len(result.missing_parent_nodes)}"
    )
    print(
        "Depth violations: "
        f"{len(result.depth_violations)}"
    )
    print(
        "Duplicate sibling sequences: "
        f"{len(result.duplicate_sequence_nodes)}"
    )
    print(f"Hierarchy valid: {result.is_valid}")
    print("\nHierarchy:")

    # TEST 1B: Use _get_children() while printing every branch.
    for root_node in root_nodes:
        print_branch(
            mapper=mapper,
            node=root_node,
            nodes=nodes,
        )

    print_function_end("PageMapper._get_children()")


if __name__ == "__main__":
    main()
