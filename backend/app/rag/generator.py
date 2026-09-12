# ========================================
# File: generator.py
# ========================================

from openai import OpenAI

from app.config import settings
from app.constants import CHAT_MODEL


class Generator:

    # ******************** Constructor ********************

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )
        self.last_usage: dict[str, int] = {}

    # ******************** Generate Answer ********************

    def generate(
        self,
        question: str,
        chunks: list[dict]
    ) -> str:

        # Label every context block with its source document.
        context_parts = []

        # Preserve source identity when topics overlap.
        for chunk in chunks:
            source = (
                chunk.get("document_title")
                or chunk.get("document_name")
                or "Unknown"
            )

            # Include only metadata needed to interpret text.
            node_type = chunk.get("node_type") or "Unknown"
            identifier = chunk.get("identifier") or ""
            node_title = chunk.get("node_title") or ""
            metadata = chunk.get("metadata") or {}
            hierarchy_path = metadata.get(
                "hierarchy_path",
                [],
            )

            # Build one clearly labelled context block.
            context_lines = [
                f"Source: {source}",
                f"Node type: {node_type}",
            ]

            # Include the exact identifier when present.
            if identifier:
                context_lines.append(
                    f"Identifier: {identifier}"
                )

            # Include a descriptive title only when available.
            if node_title:
                context_lines.append(
                    f"Node title: {node_title}"
                )

            # Show the parent chain from broad to specific.
            if hierarchy_path:
                context_lines.append(
                    "Hierarchy: "
                    + " > ".join(hierarchy_path)
                )

            # Add the complete retrieved chunk text last.
            context_lines.append(f"Text: {chunk['text']}")
            context_parts.append(
                "\n".join(context_lines)
            )

        # Separate sources clearly for the answer model.
        context = "\n\n".join(context_parts)

        # Build prompt
        prompt = f"""
Context:
{context}

Question:
{question}

Instructions:

1. Answer only using the provided context.

2. Answer the question directly and include every materially
relevant point. Do not include unrelated retrieved details.

3. Treat Node type and Identifier as the authoritative
structural reference.

When an Identifier exists, cite it by combining the exact
Node type and Identifier.

Examples:

- SUBSECTION and (3) becomes SUBSECTION (3).
- CLAUSE and (a) becomes CLAUSE (a).
- SECTION and 6. becomes SECTION 6.

Never infer a different node type from the identifier or text.
Never rename a SUBSECTION as a SECTION.

When citing a SUBSECTION or CLAUSE, use its Hierarchy to
name the nearest descriptive parent. Do not present a child
reference as though it stands alone.

4. When a TABLE has no Identifier, refer to its Node title
when available.

5. Preserve conditions attached to values, including dates,
areas, categories, and working-day counts.

6. If a definition exists, quote the complete definition as
accurately as possible.

7. Be concise but complete. State the source document title
for each answer.

8. If the answer is not found in the context, say:
"I could not find the answer in the provided document."

Answer:
"""

        # Generate answer
        response = (
            self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
        )

        if response.usage is not None:
            self.last_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }

        content = (response.choices[0].message.content)

        if content is None:
            raise ValueError(
                "OpenAI returned empty content."
            )

        return content
