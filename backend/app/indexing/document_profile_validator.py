# ========================================
# File: document_profile_validator.py
# ========================================
#
# Purpose
# -------
# Validate raw hierarchy JSON before import.
#
# Responsibilities
# ----------------
# - Enforce the profiler JSON contract.
# - Verify root and descendant node rules.
# - Detect duplicate and flattened siblings.
# - Return exact errors for profiler retries.
#
# ========================================

from dataclasses import dataclass


# ==========================================================
# Allowed Structure
# ==========================================================

# Limit OpenAI output to node types understood by IntelliDocs.
ALLOWED_NODE_TYPES = {
    "DOCUMENT",
    "PART",
    "CHAPTER",
    "ARTICLE",
    "SECTION",
    "SUBSECTION",
    "CLAUSE",
    "HEADING",
    "SUBHEADING",
    "SCHEDULE",
    "TABLE",
    "APPENDIX",
    "FORM",
}

# Identify labels that should normally own lower content.
NESTING_LABEL_TYPES = {
    "HEADING",
    "SUBHEADING",
}

# Identify nodes that represent document provisions.
CONTENT_TYPES = {
    "ARTICLE",
    "SECTION",
    "SUBSECTION",
    "CLAUSE",
}


# ==========================================================
# Validation Result
# ==========================================================

@dataclass(frozen=True)
class DocumentProfileValidationResult:

    # Keep every detected problem for correction and review.
    errors: tuple[str, ...]

    # Provide one simple overall pass-or-fail value.
    @property
    def is_valid(self) -> bool:

        # No recorded errors means the profile is valid.
        return not self.errors


# ==========================================================
# Validation Error
# ==========================================================

class DocumentProfileValidationError(ValueError):

    # Store all errors from the final rejected attempt.
    def __init__(self, errors: tuple[str, ...]):

        # Preserve individual errors for programmatic use.
        self.errors = errors

        # Begin one readable exception message.
        message = "Invalid document profile:\n- "

        # Place every validation error on its own line.
        message += "\n- ".join(errors)

        # Initialize the standard Python ValueError message.
        super().__init__(message)


# ==========================================================
# Document Profile Validator
# ==========================================================

class DocumentProfileValidator:

    # Validate one parsed profiler response.
    def validate(
        self,
        hierarchy: object,
        expected_language: str | None = None,
        expected_page_count: int | None = None,
        require_mapping_metadata: bool = False,
    ) -> DocumentProfileValidationResult:

        # Collect every issue instead of stopping at the first.
        errors = []

        # isinstance check the root must be a JSON object
        # not a list or text.
        if not isinstance(hierarchy, dict):

            # Record the root-type problem.
            errors.append(
                "The root JSON value must be an object."
            )

            # Stop because descendant inspection needs a
            # dictionary.
            return DocumentProfileValidationResult(
                errors=tuple(errors),
            )

        # Recursively validate the root and every descendant.
        self._inspect_node(
            node=hierarchy,
            path="DOCUMENT",
            is_root=True,
            errors=errors,
        )

        # Require one DOCUMENT node at the top of the tree.
        if hierarchy.get("type") != "DOCUMENT":
            errors.append(
                "The root node type must be DOCUMENT."
            )

        # The root represents the file and has no identifier.
        if hierarchy.get("identifier") != "":
            errors.append(
                "The DOCUMENT identifier must be empty."
            )

        # The document title is stored outside this root node.
        if hierarchy.get("title") != "":
            errors.append(
                "The DOCUMENT title must be empty."
            )

        # Read the first structural level below DOCUMENT.
        children = hierarchy.get("children")

        # A useful hierarchy cannot contain only a root.
        if isinstance(children, list) and not children:
            errors.append(
                "The DOCUMENT node must contain children."
            )

        # Compare language only when the caller provides one.
        if expected_language is not None:

            # Read the language supplied by the profiler.
            language = hierarchy.get("language")

            # Reject a value changed from parser detection.
            if language != expected_language:
                errors.append(
                    "The root language must match the "
                    "detected document language."
                )

        if require_mapping_metadata:
            self._check_mapping_metadata(
                hierarchy=hierarchy,
                expected_page_count=expected_page_count,
                errors=errors,
            )

        # Return all errors and useful inspection statistics.
        return DocumentProfileValidationResult(
            errors=tuple(errors),
        )

    def _check_mapping_metadata(
        self,
        hierarchy: dict,
        expected_page_count: int | None,
        errors: list[str],
    ) -> None:
        """Validate exact physical-page hints and complete page coverage."""
        node_start_pages: list[int] = []

        def inspect(node: object, path: str, parent_page: int | None) -> None:
            if not isinstance(node, dict):
                return

            if "start_page" not in node:
                errors.append(f"{path} is missing field: start_page.")
                start_page = None
            else:
                start_page = node.get("start_page")
                if type(start_page) is not int:
                    errors.append(f"{path}.start_page must be an integer PAGE_LABEL.")
                    start_page = None
                elif expected_page_count is not None and not 1 <= start_page <= expected_page_count:
                    errors.append(
                        f"{path}.start_page {start_page} is outside PAGE_LABEL 1..{expected_page_count}."
                    )

            if start_page is not None:
                node_start_pages.append(start_page)
                if parent_page is not None and start_page < parent_page:
                    errors.append(
                        f"{path}.start_page {start_page} precedes its parent page {parent_page}."
                    )

            if "opening_text" not in node:
                errors.append(f"{path} is missing field: opening_text.")
            else:
                opening_text = node.get("opening_text")
                if opening_text is not None and not isinstance(opening_text, str):
                    errors.append(f"{path}.opening_text must be text or null.")
                if node.get("type") in {"DOCUMENT", "TABLE"} and opening_text is not None:
                    errors.append(f"{path}.opening_text must be null for {node.get('type')} nodes.")

            children = node.get("children")
            if not isinstance(children, list):
                return

            previous_page: int | None = None
            for index, child in enumerate(children):
                child_path = f"{path}.children[{index}]"
                child_page = child.get("start_page") if isinstance(child, dict) else None
                if type(child_page) is int:
                    if previous_page is not None and child_page < previous_page:
                        errors.append(
                            f"{child_path}.start_page {child_page} precedes previous sibling page {previous_page}."
                        )
                    previous_page = child_page
                inspect(child, child_path, start_page if start_page is not None else parent_page)

        inspect(hierarchy, "DOCUMENT", None)

        if hierarchy.get("start_page") != 1:
            errors.append("The DOCUMENT start_page must be PAGE_LABEL 1.")

        coverage = hierarchy.get("page_coverage")
        if not isinstance(coverage, list):
            errors.append("DOCUMENT.page_coverage must be an array.")
            return
        if expected_page_count is None:
            return

        labels: list[int] = []
        classifications: dict[int, str] = {}
        allowed = {"new_nodes_start_here", "no_new_nodes_start_here"}
        for index, record in enumerate(coverage):
            if not isinstance(record, dict):
                errors.append(f"DOCUMENT.page_coverage[{index}] must be an object.")
                continue
            label = record.get("page_label")
            classification = record.get("classification")
            if type(label) is not int:
                errors.append(f"DOCUMENT.page_coverage[{index}].page_label must be an integer.")
                continue
            labels.append(label)
            if classification not in allowed:
                errors.append(
                    f"DOCUMENT.page_coverage[{index}].classification is invalid."
                )
                continue
            classifications[label] = classification

        expected_labels = list(range(1, expected_page_count + 1))
        if labels != expected_labels:
            errors.append(
                "DOCUMENT.page_coverage must contain PAGE_LABEL 1 through "
                f"{expected_page_count} exactly once in ascending order."
            )

        pages_with_nodes = set(node_start_pages)
        for label in expected_labels:
            classification = classifications.get(label)
            expected_classification = (
                "new_nodes_start_here"
                if label in pages_with_nodes
                else "no_new_nodes_start_here"
            )
            if classification is not None and classification != expected_classification:
                errors.append(
                    f"PAGE_LABEL {label} classification must be {expected_classification}."
                )

    # Inspect one node and all descendants recursively.
    def _inspect_node(
        self,
        node: object,
        path: str,
        is_root: bool,
        errors: list[str],
    ) -> None:

        # Every child must use the same JSON object shape.
        if not isinstance(node, dict):
            errors.append(f"{path} must be an object.")
            return

        # Define the fields required on every hierarchy node.
        required_fields = {
            "type",
            "identifier",
            "title",
            "children",
        }
        # Calculate which required fields are absent.
        missing_fields = sorted(
            required_fields - node.keys()
        )

        # Report all missing fields in one readable error.
        if missing_fields:

            # Join field names for the error message.
            fields = ", ".join(missing_fields)
            errors.append(
                f"{path} is missing fields: {fields}."
            )

        # Read values once for the checks below.
        node_type = node.get("type")
        identifier = node.get("identifier")
        title = node.get("title")
        children = node.get("children")

        # Node type must be text before membership checking.
        if not isinstance(node_type, str):
            errors.append(f"{path}.type must be text.")
        # Reject node types unsupported by IntelliDocs.
        elif node_type not in ALLOWED_NODE_TYPES:
            errors.append(
                f"{path} uses invalid type {node_type!r}."
            )
        # DOCUMENT can appear only once at the root.
        elif not is_root and node_type == "DOCUMENT":
            errors.append(
                f"{path} cannot contain another DOCUMENT."
            )

        # Use an empty string when no identifier exists.
        if not isinstance(identifier, str):
            errors.append(
                f"{path}.identifier must be text."
            )

        # Use an empty string when no title exists.
        if not isinstance(title, str):
            errors.append(f"{path}.title must be text.")

        # Non-table nodes need text for later page mapping.
        if (
            not is_root
            and node_type != "TABLE"
            and isinstance(identifier, str)
            and isinstance(title, str)
            and not identifier.strip()
            and not title.strip()
        ):
            errors.append(
                f"{path} needs an identifier or title."
            )

        # Children must always be represented by a JSON array.
        if not isinstance(children, list):
            errors.append(
                f"{path}.children must be an array."
            )
            # Recursion cannot continue without a list.
            return

        # Check relationships between this node's children.
        self._check_sibling_structure(
            children=children,
            path=path,
            errors=errors,
        )

        # Inspect children in their supplied document order.
        for index, child in enumerate(children):

            # Build a precise location for validation errors.
            child_path = f"{path}.children[{index}]"

            # A heading nested under a heading is a subheading.
            nested_heading = (
                node_type == "HEADING"
                and isinstance(child, dict)
                and child.get("type") == "HEADING"
            )

            # Reject the incorrect repeated heading type.
            if nested_heading:
                errors.append(
                    f"{child_path} must use SUBHEADING "
                    "when nested beneath HEADING."
                )

            # Recursively validate this complete child branch.
            self._inspect_node(
                node=child,
                path=child_path,
                is_root=False,
                errors=errors,
            )

    # Detect duplicate or flattened sibling collections.
    def _check_sibling_structure(
        self,
        children: list,
        path: str,
        errors: list[str],
    ) -> None:

        # Remember meaningful siblings already encountered.
        signatures = set()

        # Collect sibling types for flattening detection.
        child_types = set()

        # Inspect every direct child at this one level.
        for index, child in enumerate(children):

            # Detailed shape errors are handled by recursion.
            if not isinstance(child, dict):
                continue

            # Read values used to identify this sibling.
            child_type = child.get("type")
            identifier = child.get("identifier")
            title = child.get("title")

            # Keep valid type text for level comparison.
            if isinstance(child_type, str):
                child_types.add(child_type)

            # Skip duplicate checks until values are text.
            if (
                not isinstance(child_type, str)
                or not isinstance(identifier, str)
                or not isinstance(title, str)
            ):
                continue

            # Unnamed tables cannot be compared meaningfully.
            if not identifier.strip() and not title.strip():
                continue

            # Combine the values that identify one sibling.
            signature = (
                child_type,
                identifier.strip(),
                title.strip(),
            )

            # Repeated printed labels can identify distinct provisions. Only
            # reject matching labels/titles when their opening excerpts agree.
            # Missing/blank openings are inconclusive and do not block ingestion.
            opening = child.get("opening_text")
            if not isinstance(opening, str) or not opening.strip():
                continue
            signature += (" ".join(opening.split()),)

            # The same meaningful sibling must not repeat.
            if signature in signatures:
                errors.append(
                    f"{path}.children[{index}] duplicates "
                    "an earlier sibling."
                )
                continue

            # Remember this sibling for later comparisons.
            signatures.add(signature)

        # Check whether a nesting label exists at this level.
        has_nesting_label = bool(
            child_types & NESTING_LABEL_TYPES
        )
        # Check whether provision content shares this level.
        has_content = bool(child_types & CONTENT_TYPES)

        # Mixed labels and content indicate likely flattening.
        if has_nesting_label and has_content:
            errors.append(
                f"{path} mixes container and content "
                "nodes at one level; the hierarchy may "
                "have been flattened."
            )
