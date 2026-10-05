# ========================================
# File: generator.py
# ========================================

from openai import OpenAI

from app.config import settings
from app.constants import CHAT_MODEL, CHAT_REASONING_EFFORT
from app.services.usage.ai_usage import tracked_ai_call, estimate_request_cost
from app.rag.debug_capture import AnswerDebugCapture
from app.rag.context_packer import pack_context


# Bump when answer instructions change so saved requests remain comparable.
ANSWER_PROMPT_VERSION = "applicability-scope-compact-context-v3"


class Generator:

    # ******************** Constructor ********************

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=0,  # Each paid attempt must receive its own allowance hold.
        )
        self.last_usage: dict[str, int] = {}

    # ******************** Generate Answer ********************

    def generate(
        self,
        question: str,
        chunks: list[dict]
    ) -> str:

        # Compact labels and proven same-provision overlaps, without applying
        # a new allowance or dropping any selected/reference-followed provision.
        context, context_compaction = pack_context(chunks)
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

Resolve document (D), hierarchy (H), printed-reference (R),
and evidence (E) labels using the context legends. Hierarchy
labels inherit their parent's full path. Never cite these
internal labels in the answer; cite the original document,
node type, identifier and descriptive parent instead.
When text is included verbatim in another evidence block,
read that block while preserving this block's citation.

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
            "max_completion_tokens": settings.CHAT_MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        capture = AnswerDebugCapture(
            question=question, chunks=chunks, request=request,
            prompt_version=ANSWER_PROMPT_VERSION,
            context_compaction=context_compaction,
        )
        response = None
        try:
            response = tracked_ai_call(
                lambda: self.client.chat.completions.create(**request),
                activity="chat", model=CHAT_MODEL,
                budget_estimate=lambda: estimate_request_cost(CHAT_MODEL, request),
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
