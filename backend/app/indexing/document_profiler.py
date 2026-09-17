
# ========================================
# File: document_profiler.py
# ========================================
#
# Purpose
# -------
# Generate and validate document hierarchy profiles.
#
# Responsibilities
# ----------------
# - Request hierarchy JSON from OpenAI.
# - Validate every raw response before import.
# - Save every response and validation result.
# - Retry rejected responses with exact errors.
#
# ========================================

import json

from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.constants import DOCUMENT_PROFILER_MODEL
from app.services.usage.ai_usage import tracked_ai_call
from app.indexing.document_profile_validator import (
    DocumentProfileValidationError,
    DocumentProfileValidator,
)


# ==========================================================
# Configuration
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES_FOLDER = (
    PROJECT_ROOT / "documents" / "Profiles"
)
MAX_PROFILE_ATTEMPTS = 3


# ==========================================================
# Document Profiler
# ==========================================================

class DocumentProfiler:

    # Create the OpenAI client and raw-profile validator.
    def __init__(self):

        # Use the configured project API key.
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )
        # Reuse one validator for every response attempt.
        self.validator = DocumentProfileValidator()

    # Generate one validated hierarchy with limited retries.
    def generate_hierarchy(
        self,
        document_text: str,
        document_language: str,
        document_id: str,
        owner_id: str,
    ) -> dict:

        # Build the full initial instruction once.
        base_prompt = self._build_prompt(
            document_text=document_text,
            document_language=document_language
        )
        # No rejected output exists before the first request.
        previous_output = None

        # No correction errors exist before the first request.
        previous_errors = ()

        # Permit one original request and two corrections.
        for attempt in range(1, MAX_PROFILE_ATTEMPTS + 1):

            # Use the original profiler prompt initially.
            prompt = base_prompt

            # After rejection, request a targeted correction.
            if previous_output is not None:
                prompt = self._build_retry_prompt(
                    base_prompt=base_prompt,
                    previous_output=previous_output,
                    errors=previous_errors,
                )

            # Send the current attempt to OpenAI.
            response = tracked_ai_call(
                lambda: self.client.responses.create(model=DOCUMENT_PROFILER_MODEL, input=prompt),
                activity="profiling", model=DOCUMENT_PROFILER_MODEL,
                user_id=owner_id, document_id=document_id, attempt=attempt,
            )
            # Preserve the exact response before parsing it.
            raw_output = response.output_text

            # Parse and validate valid-looking JSON responses.
            try:

                # Convert JSON text into Python dictionaries.
                hierarchy = json.loads(raw_output)

                # Validate structure before database import.
                result = self.validator.validate(
                    hierarchy=hierarchy,
                    expected_language=document_language,
                )
                # Keep exact errors for saving and retrying.
                errors = result.errors

            # Convert malformed JSON into a validation error.
            except json.JSONDecodeError as error:

                # No parsed hierarchy exists this attempt.
                hierarchy = None

                # Explain where JSON parsing failed.
                errors = (
                    "The response is not valid JSON: "
                    f"{error.msg} at line {error.lineno}.",
                )

            # Save accepted and rejected attempts for review.
            self._save_attempt(
                owner_id=owner_id,
                document_id=document_id,
                attempt=attempt,
                raw_output=raw_output,
                hierarchy=hierarchy,
                errors=errors,
            )

            # Accept only a valid dictionary hierarchy.
            if not errors and isinstance(hierarchy, dict):

                # Save one convenient final hierarchy file.
                self._save_accepted_profile(
                    owner_id=owner_id,
                    document_id=document_id,
                    hierarchy=hierarchy,
                )
                # Make acceptance visible in the terminal.
                print(
                    f"Profile attempt {attempt} accepted."
                )
                # Return the only hierarchy allowed for import.
                return hierarchy

            # Preserve rejected output for correction.
            previous_output = raw_output

            # Preserve exact errors for the correction prompt.
            previous_errors = errors

            # Make rejection visible in the terminal.
            print(
                f"Profile attempt {attempt} rejected: "
                f"{len(errors)} validation error(s)."
            )

        # Stop ingestion after all three attempts fail.
        raise DocumentProfileValidationError(
            previous_errors
        )

    # Ask the profiler to correct its rejected response.
    def _build_retry_prompt(
        self,
        base_prompt: str,
        previous_output: str,
        errors: tuple[str, ...],
    ) -> str:

        # Format validation errors as a readable list.
        error_text = "\n".join(
            f"- {error}" for error in errors
        )

        # Include the document, errors, and rejected output.
        return f"""
{base_prompt}

CORRECTION REQUIRED

Your previous response failed validation.

VALIDATION ERRORS

{error_text}

CORRECTION RULES

Rebuild the parent-child relationships that caused each
error.
Do not merely remove an invalid wrapper while leaving its
children flattened at the same level.

Place governed content beneath the deepest applicable HEADING
or SUBHEADING. Do not create unlabeled container nodes.

PREVIOUS RESPONSE

{previous_output}

Return a complete corrected hierarchy as JSON only.
"""

    # Save one exact response and its validation report.
    def _save_attempt(
        self,
        owner_id: str,
        document_id: str,
        attempt: int,
        raw_output: str,
        hierarchy: object,
        errors: tuple[str, ...],
    ) -> None:

        # Resolve this user's document-specific folder.
        profile_folder = self._get_profile_folder(
            owner_id,
            document_id,
        )
        # Keep the exact OpenAI text for this attempt.
        response_path = (
            profile_folder
            / f"attempt_{attempt}_response.txt"
        )
        # Keep a machine-readable validation report.
        validation_path = (
            profile_folder
            / f"attempt_{attempt}_validation.json"
        )
        # Describe whether this attempt passed and parsed.
        validation_data = {
            "attempt": attempt,
            "accepted": not errors,
            "errors": list(errors),
            "parsed_json": hierarchy is not None,
        }
        # Save the untouched response even when JSON is broken.
        response_path.write_text(
            raw_output,
            encoding="utf-8",
        )
        # Save validation details beside the response.
        validation_path.write_text(
            json.dumps(
                validation_data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # Save the hierarchy selected for database import.
    def _save_accepted_profile(
        self,
        owner_id: str,
        document_id: str,
        hierarchy: dict,
    ) -> None:

        # Reuse the same user and document folder.
        profile_folder = self._get_profile_folder(
            owner_id,
            document_id,
        )
        # Use one predictable name for downstream review.
        accepted_path = (
            profile_folder / "accepted_profile.json"
        )
        # Store formatted JSON instead of raw response text.
        accepted_path.write_text(
            json.dumps(
                hierarchy,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # Create one isolated profile folder per user and document.
    def _get_profile_folder(
        self,
        owner_id: str,
        document_id: str,
    ) -> Path:

        # Prevent owner text from creating unsafe paths.
        safe_owner = self._safe_folder_name(owner_id)

        # Prevent document text from creating unsafe paths.
        safe_document = self._safe_folder_name(document_id)

        # Keep every document inside its owner's folder.
        profile_folder = (
            DEFAULT_PROFILES_FOLDER
            / safe_owner
            / safe_document
        )
        # Create missing folders without replacing contents.
        profile_folder.mkdir(
            parents=True,
            exist_ok=True,
        )
        # Return the ready folder to the saving methods.
        return profile_folder

    # Remove characters that are unsafe in folder names.
    def _safe_folder_name(self, value: str) -> str:

        # Keep safe characters and replace everything else.
        safe_characters = [
            character
            if character.isalnum()
            or character in {"-", "_", "."}
            else "_"
            for character in value
        ]
        # Combine the cleaned characters into one folder name.
        return "".join(safe_characters)

    # Build the full instruction containing document text.
    def _build_prompt(
        self,
        document_text: str,
        document_language: str
    ) -> str:

        return f"""
You are an expert document structure analyst specializing in
extracting hierarchical relationships from complex documents.

Analyze the supplied document and convert its structure into
a normalized hierarchical tree.

OBJECTIVE

Identify the document's structural hierarchy and return it as
machine-readable JSON.

The output will be consumed by an automated document
ingestion system.

The hierarchy must be complete, accurate, and
machine-readable.

Do not omit structural levels even if they contain only one
child node.

HIERARCHY OWNERSHIP RULES

1. HEADING and SUBHEADING nodes are structural containers.

2. Content governed by a HEADING or SUBHEADING must be
nested inside that container.

3. Never place a HEADING or SUBHEADING beside the SECTION,
ARTICLE, TABLE, or other content nodes that it governs.

4. When a SUBHEADING appears beneath a HEADING, nest all
following governed content beneath that SUBHEADING until the
next SUBHEADING or a higher-level container begins.

5. Every content node must be nested under the deepest
applicable preceding HEADING or SUBHEADING.

6. Do not create an empty PART, CHAPTER, HEADING, SUBHEADING,
or other container as an organizational wrapper.

7. A non-table container may exist only when its identifier or
title is visibly present in the source document.

8. A heading nested directly beneath a HEADING must use the
SUBHEADING type. It must never use HEADING again.

9. A HEADING node must never have another HEADING as its
direct child.

10. Determine HEADING versus SUBHEADING from its structural
depth, not from capitalization, font size, or wording alone.

INCORRECT FLATTENED STRUCTURE

DOCUMENT
- HEADING
  - SUBHEADING
- SECTION

CORRECT NESTED STRUCTURE

DOCUMENT
- HEADING: Parent heading
  - SUBHEADING: Nested heading
    - SECTION
      - SUBSECTION

ALLOWED NODE TYPES

Use ONLY the following node types:

- DOCUMENT
- PART
- CHAPTER
- ARTICLE
- SECTION
- SUBSECTION
- CLAUSE
- HEADING
- SUBHEADING
- SCHEDULE
- TABLE
- APPENDIX
- FORM

Do not create any additional node types.

Examples of prohibited node types:

- SUBPARAGRAPH
- SUBSUBPARAGRAPH
- ITEM
- TOPIC_GROUP
- REGULATION_ITEM
- ANNEX_SECTION

If a structural level does not exactly match one of the allowed node types, map it to the closest equivalent using the normalization rules below.

NORMALIZATION RULES

1. Numbered children directly under a SECTION must be represented as SUBSECTION.

Examples:

(1)
(2)
(3)

→ SUBSECTION

2. Lettered children directly under a SUBSECTION must be represented as CLAUSE.

Examples:

(a)
(b)
(c)

→ CLAUSE

3. Numbered or lettered children below a CLAUSE must also be represented as CLAUSE.

Do not introduce additional hierarchy types.

4. If a document contains headings that do not have formal numbering:

- Use HEADING
- Use SUBHEADING when nested beneath a HEADING

This relationship is mandatory. Never return a HEADING as a
direct child of another HEADING.

5. If a document contains annexes, appendices, forms, schedules, or tables, use:

- APPENDIX
- FORM
- SCHEDULE
- TABLE

respectively.

GENERAL RULES

1. Analyze the entire document.

2. Use only structure that actually exists in the document.

3. Do not invent hierarchy levels.

4. Preserve the hierarchy exactly as it appears.

5. Preserve all numbering, lettering, and identifiers exactly as written.

6. Detect tables and include them as TABLE nodes.

7. Detect schedules and include them as SCHEDULE nodes.

8. Detect appendices and include them as APPENDIX nodes.

9. Detect forms and include them as FORM nodes.

10. Maintain exact parent-child relationships.

11. Preserve deleted, omitted, repealed, reserved, or inactive provisions.

12. Do not summarize content.

13. Do not extract body text.

14. Do not infer missing structure.

15. Do not merge nodes.

16. Do not reorder nodes.

17. Preserve all titles exactly as they appear in the document.

18. Do not translate titles, headings, identifiers, schedules,
appendices, table captions or structural labels.

19. The output language must remain identical to the source document.

20. If the document contains multiple languages, preserve the original text exactly as written.

21. Do not normalize, paraphrase, rewrite, or translate any extracted title.

NODE FORMAT

Every node MUST contain:

- type
- identifier
- title
- children

Rules:

- If title does not exist, use an empty string.
- If identifier does not exist, use an empty string.
- children must always be present.
- If a node has no children, return an empty array.


DOCUMENT LANGUAGE

The document language has already been detected
by the application.

Use the exact language value below. Do not infer, translate, normalize or modify it.

DOCUMENT_LANGUAGE: {document_language}


FINAL HIERARCHY CHECK

Before returning JSON, inspect the completed tree and correct
all of the following:

1. Replace every HEADING directly beneath a HEADING with
SUBHEADING.

2. Ensure each SECTION is beneath the deepest applicable
HEADING or SUBHEADING.

3. Remove any invented container whose identifier and title
are both empty.

Do not return the JSON until all three checks pass.


OUTPUT FORMAT

Return JSON only.

Root node must always be:

{{
  "type": "DOCUMENT",
  "language": "{document_language}",
  "identifier": "",
  "title": "",
  "children": []
}}

DOCUMENT

{document_text}
"""
