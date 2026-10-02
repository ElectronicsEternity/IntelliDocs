# ========================================
# File: generator.py
# ========================================

from openai import OpenAI

from app.config import settings
from app.constants import CHAT_MODEL, CHAT_REASONING_EFFORT
from app.services.usage.ai_usage import tracked_ai_call
from app.rag.debug_capture import AnswerDebugCapture


# Bump when answer instructions change so saved requests remain comparable.
ANSWER_PROMPT_VERSION = "applicability-scope-references-v2"


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
            # State why linked evidence was included, without claiming the link
            # itself proves a legal effect. The actual provision text controls.
            for link in chunk.get("reference_links", []):
                reference = link["reference"]
                target = reference["identifier"] + (reference["sub_identifier"] or "")
                context_lines.append(
                    f"Printed reference connection ({link['direction']}): "
                    f"{reference['node_type']} {target} within this document."
                )
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

4. An applicability clause is a clause that expressly states
whether the requested provision applies or does not apply.
When such a clause exists, use it as the controlling scope
instead of clauses that describe particular requirements or
regulated categories.

5. When a TABLE has no Identifier, refer to its Node title
when available.

6. Preserve conditions attached to values, including dates,
areas, categories, and working-day counts.

7. If a definition exists, quote the complete definition as
accurately as possible.

8. Be concise but complete. State the source document title
for each answer.

9. If the answer is not found in the context, say:
"I could not find the answer in the provided document."

10. Format the answer as clean Markdown for a web interface:

- Start with a direct answer or one-sentence summary.
- Use short descriptive headings only when the answer has
  more than one distinct section.
- Put every bullet or numbered item on its own line.
- Use bullet lists for parallel facts, rates, conditions, or
  options.
- Use numbered lists only for steps, rankings, or an ordered
  sequence.
- Use nested bullets for subcategories such as different
  locations, dates, or employee groups.
- Use bold text sparingly for key labels and values.
- Leave a blank line before and after every list.
- Do not force a list when a short paragraph is clearer.
- Do not add an "Answer" heading.

11. Put the supporting document title on a final separate
line in this format: **Source:** document title.

Answer:
"""

        # Generate answer
        self.last_usage = {}
        # Save the same request dictionary passed to OpenAI, including the
        # fully assembled instructions, question and dynamic chunk text.
        request = {
            "model": CHAT_MODEL,
            "reasoning_effort": CHAT_REASONING_EFFORT,
            "messages": [{"role": "user", "content": prompt}],
        }
        capture = AnswerDebugCapture(
            question=question, chunks=chunks, request=request,
            prompt_version=ANSWER_PROMPT_VERSION,
        )
        response = None
        try:
            response = tracked_ai_call(
                lambda: self.client.chat.completions.create(**request),
                activity="chat", model=CHAT_MODEL,
            )
            if response.usage is not None:
                self.last_usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("OpenAI returned empty content.")
        except Exception as exc:
            capture.finish(response=response, error=exc)
            raise
        capture.finish(response=response, answer=content)
        return content
