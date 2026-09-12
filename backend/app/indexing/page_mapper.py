# ========================================
# File: page_mapper.py
# ========================================

from app.models.document import Document
from app.models.document_node import DocumentNode


class PageMapper:

    # Constructor
    def __init__(self, repository):
        self.repository = repository


    # Map page ranges for a document
    def map_document(self, document: Document) -> None:

        print("\n=== PageMapper Started ===")
        print(f"Document ID: {document.id}")
        print(f"Total pages: {document.total_pages}")

        # Get document hierarchy
        nodes = self.repository.get_by_document(document.id)
        print(f"Nodes loaded: {len(nodes)}")

        if not nodes:
            print("No document nodes found. Page mapping stopped.")
            return

        # Clear every previous mapping value before recalculating from scratch.
        # This prevents unanchored nodes, such as tables, from retaining stale
        # inherited page ranges after their parent positions have changed.
        for node in nodes:
            node.start_page = None
            node.start_character = None
            node.end_page = None

        # Build node lookup table
        node_lookup = self._build_node_lookup(nodes)
        print(f"Node lookup created: {len(node_lookup)} entries")

        # Get root nodes
        root_nodes = sorted(
            [
                node
                for node in nodes
                if node.parent_id is None
            ],
            # sort root nodes according to sequence_no
            key=lambda node: node.sequence_no
        )

        print(f"Root nodes found: {len(root_nodes)}")

        # Map hierarchy using DFS
        print("\n--- DFS Page Mapping ---")
        for root_node in root_nodes:
            print(f"Starting root: {root_node.node_type} | {root_node.title or '[no title]'}")
            self._map_branch(
                document=document,
                node=root_node,
                nodes=nodes,
                start_page=1,
                end_page=document.total_pages
            )

        # Map untitled nodes that have searchable identifiers such as (1).
        print("\n--- Identifier Position Mapping ---")
        self._map_identifier_nodes(
            document=document,
            nodes=nodes
        )

        # Calculate start and end page ranges
        print("\n--- Calculating Page Ranges ---")
        self._calculate_page_ranges(
            nodes=nodes,
            node_lookup=node_lookup,
            document=document
        )

        # Save page ranges
        print("\n--- Saving Page Ranges ---")
        self._save_page_ranges(nodes)
        print("=== PageMapper Complete ===\n")


    # Build node lookup table
    def _build_node_lookup(self,nodes: list[DocumentNode]
    ) -> dict:
        print("\n=== NodeLookup Started ===")
        return {
            node.id: node
            # "id-001": DOCUMENT node,
            # "id-003": SECTION node
            for node in nodes
        }


    # Get child nodes
    def _get_children(
        self,
        parent_id: str,
        nodes: list[DocumentNode]
    ) -> list[DocumentNode]:

        return sorted(
            [
                node
                for node in nodes
                if node.parent_id == parent_id
            ],
            key=lambda node: node.sequence_no
        )


    # Find title page within search boundary
    def _find_title_page(
        self,
        title: str,
        pages,
        start_page: int = 1,
        end_page: int | None = None
    ) -> dict[str, int] | None:

        if not title or not title.strip():
            return None

        # Normalize whitespace so a title can still match when the PDF
        # extractor splits it across lines or inserts repeated spaces.
        # Ex, "terms and conditions"
        search_title = " ".join(title.lower().split())

        # PDF extraction can also insert spaces inside words or before
        # punctuation, for example "t empoh" or "tan ,". This compact
        # version provides a fallback comparison that ignores those spaces.
        # Ex, 'termsandconditions'
        compact_search_title = "".join(search_title.split())

        # Keep terminal output readable without changing the real title.
        display_title = title.strip()

        if len(display_title) > 80:
            display_title = f"{display_title[:80]}..."

        search_message = (
            f"Searching: '{display_title}' | "
            f"pages {start_page}-{end_page}"
        )

        for page in pages:

            if page.page_number < start_page:
                continue

            if end_page is not None and page.page_number > end_page:
                continue

            # Normalize the extracted PDF text while remembering where each
            # normalized character came from in the original page text.
            # This lets us search normalized text but still return a usable
            # zero-based character position from the original page.
            normalized_characters = []
            original_positions = []
            whitespace_pending = False

            for original_index, character in enumerate(page.text):

                if character.isspace():
                    if normalized_characters:
                        whitespace_pending = True
                    continue

                if whitespace_pending:
                    normalized_characters.append(" ")
                    original_positions.append(original_index)
                    whitespace_pending = False

                for lowercase_character in character.lower():
                    normalized_characters.append(lowercase_character)
                    original_positions.append(original_index)

            normalized_page_text = "".join(
                normalized_characters
            )

            # Try the readable normalized text first. If it does not match,
            # use the compact version to tolerate PDF extraction artifacts.
            compact_characters = []
            compact_original_positions = []

            for character, original_position in zip(
                normalized_page_text,
                original_positions
            ):
                if character.isspace():
                    continue

                compact_characters.append(character)
                compact_original_positions.append(original_position)

            compact_page_text = "".join(compact_characters)

            # Prefer the normal whitespace-aware match. Use the compact
            # fallback only when PDF extraction inserted unwanted spaces.
            match_index = normalized_page_text.find(search_title)
            match_positions = original_positions

            if match_index == -1:
                match_index = compact_page_text.find(compact_search_title)
                match_positions = compact_original_positions

            if match_index != -1:
                start_character = match_positions[match_index]
                print(
                    f"{search_message} | "
                    f"Found on page {page.page_number} | "
                    f"Start character {start_character}"
                )
                # Named values make the result easier to understand and
                # allow more title-match details to be added later.
                return {
                    "page_number": page.page_number,
                    "start_character": start_character,
                }

        print(f"{search_message} | Not found")
        return None


    # Find an identifier inside an exact parent boundary.
    def _find_identifier_position(
        self,
        identifier: str,
        pages,
        start_page: int,
        start_character: int,
        end_page: int,
        end_character: int
    ) -> dict[str, int] | None:

        # Stop when the node has no usable identifier.
        if not identifier or not identifier.strip():
            return None

        # Normalize identifier whitespace for consistent PDF text matching.
        search_identifier = " ".join(identifier.lower().split())

        # Ignore inserted whitespace if the normal comparison does not match.
        compact_search_identifier = "".join(search_identifier.split())

        # Search only pages that belong to the current parent node.
        for page in pages:

            # Skip pages before the parent boundary.
            if page.page_number < start_page:
                continue

            # Skip pages after the parent boundary.
            if page.page_number > end_page:
                continue

            # Begin at the supplied character on the first boundary page.
            page_start = start_character if page.page_number == start_page else 0

            # Stop at the supplied character on the final boundary page.
            page_end = end_character if page.page_number == end_page else len(page.text)

            # Ignore an empty portion of a boundary page.
            if page_start >= page_end:
                continue

            # Store normalized characters used during the identifier search.
            normalized_characters = []

            # Remember every normalized character's original page position.
            original_positions = []

            # Delay whitespace until another visible character is encountered.
            whitespace_pending = False

            # Inspect only the text located inside the parent boundary.
            for original_index in range(page_start, page_end):

                # Read the current character from the original page text.
                character = page.text[original_index]

                # Collapse consecutive whitespace into one pending space.
                if character.isspace():

                    # Avoid adding whitespace before the first visible character.
                    if normalized_characters:
                        whitespace_pending = True

                    # Continue with the next original page character.
                    continue

                # Add one space before the next visible character when needed.
                if whitespace_pending:
                    normalized_characters.append(" ")
                    original_positions.append(original_index)
                    whitespace_pending = False

                # Store lowercase characters while retaining original positions.
                for lowercase_character in character.lower():
                    normalized_characters.append(lowercase_character)
                    original_positions.append(original_index)

            # Combine normalized characters into searchable page text.
            normalized_page_text = "".join(normalized_characters)

            # Prepare the whitespace-free fallback text and position mapping.
            compact_characters = []
            compact_original_positions = []

            # Remove normalized whitespace while keeping original positions.
            for character, original_position in zip(normalized_page_text, original_positions):

                # Exclude whitespace from the compact fallback.
                if character.isspace():
                    continue

                # Keep the visible character in the compact fallback.
                compact_characters.append(character)

                # Keep the character's corresponding original page position.
                compact_original_positions.append(original_position)

            # Combine the compact fallback characters.
            compact_page_text = "".join(compact_characters)

            # Prefer the normal whitespace-aware identifier match.
            match_index = normalized_page_text.find(search_identifier)

            # Use normal original positions unless compact matching is required.
            match_positions = original_positions

            # Fall back to matching without whitespace when necessary.
            if match_index == -1:
                match_index = compact_page_text.find(compact_search_identifier)
                match_positions = compact_original_positions

            # Return the original PDF position when a match is found.
            if match_index != -1:
                return {
                    "page_number": page.page_number,
                    "start_character": match_positions[match_index],
                }

        # Report that no identifier was found inside the parent boundary.
        return None


    # Return the exclusive physical end boundary of one hierarchy node.
    def _get_node_end_position(
        self,
        node: DocumentNode,
        nodes: list[DocumentNode],
        document: Document
    ) -> tuple[int, int]:

        # Use the document's final character when this node is a root.
        if node.parent_id is None:
            last_page = max(document.pages, key=lambda page: page.page_number)
            return last_page.page_number, len(last_page.text)

        # Load this node's siblings in their declared hierarchy order.
        siblings = self._get_children(parent_id=node.parent_id, nodes=nodes)

        # Locate the current node inside the ordered sibling list.
        node_index = siblings.index(node)

        # The next mapped sibling marks this node's exclusive end boundary.
        for sibling in siblings[node_index + 1:]:
            if sibling.start_page is not None and sibling.start_character is not None:
                return sibling.start_page, sibling.start_character

        # Find the parent when this node is the final mapped sibling.
        parent_node = next(
            parent for parent in nodes if parent.id == node.parent_id
        )

        # The final sibling ends at its parent's exclusive end boundary.
        return self._get_node_end_position(parent_node, nodes, document)


    # Map untitled nodes that have identifiers inside their parent boundaries.
    def _map_identifier_nodes(
        self,
        document: Document,
        nodes: list[DocumentNode]
    ) -> None:

        # Process parents before descendants so child searches have boundaries.
        ordered_parents = sorted(nodes, key=lambda node: node.depth)

        # A subsection cannot be searched safely until its section
        # has already been positioned
        # Process every possible parent
        for parent_node in ordered_parents:

            # Load this parent's children in sequence number order.
            children = self._get_children(parent_id=parent_node.id, nodes=nodes)

            # Skip nodes that do not own any children.
            if not children:
                continue

            # A root begins at the first character of the first PDF page.
            if parent_node.parent_id is None:
              # (page_number, character_position)
                parent_start = (1, 0)

            # A non-root parent requires a known physical start position.
            elif parent_node.start_page is not None and parent_node.start_character is not None:
                parent_start = (parent_node.start_page, parent_node.start_character)

            # Skip descendants whose parent cannot yet be located physically.
            else:
                continue

            # Calculate the exclusive position where this parent ends.
            parent_end = self._get_node_end_position(parent_node, nodes, document)

            # Begin searching children from the start of their parent.
            search_start = parent_start

            # Process siblings in their declared sequence order.
            for child in children:

                # Existing title positions also advance the sibling cursor.
                if child.title and child.title.strip():
                    if child.start_page is not None and child.start_character is not None:
                        search_start = (child.start_page, child.start_character + 1)
                    continue

                # Nodes without titles or identifiers cannot use text matching.
                if not child.identifier or not child.identifier.strip():
                    continue

                # Clear inherited values so this run produces a fresh result.
                child.start_page = None
                child.start_character = None

                # Find this identifier only after the previous sibling and
                # before the current parent's exclusive end boundary.
                identifier_position = self._find_identifier_position(
                    identifier=child.identifier,
                    pages=document.pages,
                    start_page=search_start[0],
                    start_character=search_start[1],
                    end_page=parent_end[0],
                    end_character=parent_end[1]
                )

                # Keep a missing position visible for playground inspection.
                if identifier_position is None:
                    print(
                        f"Identifier not found: {child.node_type} | "
                        f"{child.identifier}"
                    )
                    continue

                # Store the identifier's exact page and character position.
                child.start_page = identifier_position["page_number"]
                child.start_character = identifier_position["start_character"]

                # Begin the next sibling search after this identifier starts.
                search_start = (child.start_page, child.start_character + 1)

                # Print the mapped position for transparent test output.
                print(
                    f"Identifier mapped: {child.node_type} | "
                    f"{child.identifier} | page {child.start_page} | "
                    f"character {child.start_character}"
                )


    # Map hierarchy branch using DFS
    def _map_branch(
        self,
        document: Document,
        node: DocumentNode,
        nodes: list[DocumentNode],
        start_page: int,
        end_page: int | None
        ) -> None:

        print(
            f"Depth {node.depth} | Sequence {node.sequence_no} | "
            f"{node.node_type} | {node.identifier or '[no identifier]'} | "
            f"{node.title or '[no title]'}"
        )

        # Current search boundary
        branch_start_page = start_page

        # Tables use PDF geometry instead of title matching.
        is_table_node = node.node_type.upper() == "TABLE"

        # Leave table positions for the table pipeline.
        if is_table_node:
            print("  Table title search skipped.")

        # Search ordinary titled nodes inside the branch.
        elif node.title and node.title.strip():
            title_position = self._find_title_page(
                title=node.title,
                pages=document.pages,
                start_page=start_page,
                end_page=end_page
            )

            if title_position is not None:
                # Keep both parts of the title location on the in-memory
                # node. start_page identifies the PDF page, while
                # start_character identifies the exact position on it.
                page_number = title_position["page_number"]
                start_character = title_position["start_character"]

                node.start_page = page_number
                node.start_character = start_character

                print(
                    f"  Start position set: page {node.start_page}, "
                    f"character {node.start_character}"
                )
                # Child search starts from parent match
                branch_start_page = page_number

            else:
                print("  No title. Title search skipped.")

        # Get children in sequence
        children = self._get_children(
            parent_id=node.id,
            nodes=nodes
        )

        print(f"  Children found: {len(children)}")

        # Traverse each child branch
        for child in children:
            self._map_branch(
                document=document,
                node=child,
                nodes=nodes,
                start_page=branch_start_page,
                end_page=end_page
            )


    # Calculate page ranges
    def _calculate_page_ranges(
        self,
        nodes: list[DocumentNode],
        node_lookup: dict,
        document: Document
    ) -> None:

        # Root covers the whole document
        for node in nodes:
            if node.parent_id is None:
                node.start_page = node.start_page or 1
                node.end_page = document.total_pages
                print(f"Root range: {node.start_page}-{node.end_page}")

        # Process parents from top to bottom
        ordered_nodes = sorted(nodes, key=lambda node: (node.depth, node.sequence_no))

        for parent_node in ordered_nodes:

            children = self._get_children(
                parent_id=parent_node.id,
                nodes=nodes
            )

            if not children:
                continue

            print(
                f"Parent: {parent_node.node_type} | "
                f"{parent_node.identifier or '[no identifier]'} | "
                f"children: {len(children)}"
            )

            for index, child_node in enumerate(children):

                if child_node.start_page is None:
                    print(
                        f"  Range skipped: {child_node.node_type} | "
                        f"{child_node.identifier or '[no identifier]'} | no start page"
                    )
                    continue

                # Check next sibling
                if index < len(children) - 1:
                    next_child = children[index + 1]

                    if next_child.start_page is not None:
                        # Sibling content can share the same PDF page.
                        # Include the next sibling's start page in the current
                        # range so content before that sibling is not lost.
                        child_node.end_page = max(
                            child_node.start_page,
                            next_child.start_page
                        )
                        print(
                            f"  Range set: {child_node.node_type} | "
                            f"{child_node.identifier or '[no identifier]'} | "
                            f"{child_node.start_page}-{child_node.end_page}"
                        )
                    else:
                        print(
                            f"  End page pending: {child_node.node_type} | "
                            f"next sibling has no start page"
                        )

                    continue

                # Last child inherits parent boundary
                child_node.end_page = parent_node.end_page
                print(
                    f"  Last child range: {child_node.node_type} | "
                    f"{child_node.identifier or '[no identifier]'} | "
                    f"{child_node.start_page}-{child_node.end_page}"
                )

        # Resolve any mapped node still missing an end page
        for node in nodes:

            if node.start_page is None or node.end_page is not None:
                continue

            parent_node = node_lookup.get(node.parent_id)

            if parent_node and parent_node.end_page is not None:
                node.end_page = parent_node.end_page
            else:
                node.end_page = document.total_pages

            print(
                f"Fallback range: {node.node_type} | "
                f"{node.identifier or '[no identifier]'} | "
                f"{node.start_page}-{node.end_page}"
            )

        # Give unanchored nodes their parent's page range.
        # This includes TABLE nodes handled by geometry.
        # Processing by depth resolves parent ranges first.
        # Ordinary titled nodes remain mapping failures.
        for node in ordered_nodes:

            has_title = bool(
                node.title and node.title.strip()
            )
            is_table_node = (
                node.node_type.upper() == "TABLE"
            )

            # Only tables may inherit despite having titles.
            if has_title and not is_table_node:
                continue

            if node.start_page is not None or node.end_page is not None:
                continue

            parent_node = node_lookup.get(node.parent_id)

            if (
                parent_node is None
                or parent_node.start_page is None
                or parent_node.end_page is None
            ):
                print(
                    f"Inherited range skipped: {node.node_type} | "
                    f"{node.identifier or '[no identifier]'} | "
                    f"parent has no complete range"
                )
                continue

            node.start_page = parent_node.start_page
            node.end_page = parent_node.end_page

            print(
                f"Inherited range: {node.node_type} | "
                f"{node.identifier or '[no identifier]'} | "
                f"{node.start_page}-{node.end_page}"
            )


    # Persist page ranges
    def _save_page_ranges(
        self,
        nodes: list[DocumentNode]
    ) -> None:

        for node in nodes:

            if node.start_page is None and node.end_page is None:
                continue

            self.repository.update_page_range(
                node_id=node.id,
                start_page=node.start_page,
                start_character=node.start_character,
                end_page=node.end_page
            )
