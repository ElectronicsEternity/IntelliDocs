# ========================================
# File: orchestrator.py
# ========================================
#
# Purpose
# -------
# Test production retrieval and answer generation.
#
# Responsibilities
# ----------------
# - Ask questions about the indexed document.
# - Run all production retrieval paths.
# - Generate answers from retrieved chunks.
# - Save readable results for inspection.
#
# ========================================

from pathlib import Path

from app.rag.embedder import Embedder
from app.rag.generator import Generator
from app.rag.retriever import Retriever
from app.storage.postgres_vector_store import (
    PostgresVectorStore,
)


# ==========================================================
# Test Configuration
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FILE = PROJECT_ROOT / "outputs" / "retrieval_output.txt"
OWNER_ID = "dev_user"

QUESTIONS = [
    (
        "Under Section 4, what are the monthly and hourly "
        "minimum wage rates?"
    ),
    (
        "What is the daily minimum wage for an employee "
        "who works six days per week?"
    ),
    (
        "When did the Minimum Wages Order 2022 come into "
        "operation?"
    ),
    "What is Section 6 about?",
    "Who is the Prime Minister of Malaysia?",
]


# ==========================================================
# Retrieval Test
# ==========================================================

def main() -> None:

    # Create the production dependencies used by retrieval.
    vector_store = PostgresVectorStore()
    embedder = Embedder()
    generator = Generator()

    # Connect the production retriever to PostgreSQL.
    retriever = Retriever(
        embedder=embedder,
        vector_store=vector_store,
    )

    # Ensure the output folder exists before writing results.
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        # Replace the previous report with a fresh test run.
        with OUTPUT_FILE.open(
            "w",
            encoding="utf-8",
        ) as file:
            file.write("IntelliDocs Retrieval Results\n")
            file.write("=" * 60 + "\n\n")

        # Test each question independently.
        for question_number, question in enumerate(
            QUESTIONS,
            start=1,
        ):

            # Retrieve ranked chunks through production code.
            retrieved_chunks = retriever.retrieve(
                owner_id=OWNER_ID,
                question=question,
            )

            # Ask the production generator to answer from them.
            answer = generator.generate(
                question=question,
                chunks=retrieved_chunks,
            )

            # Add this question and its evidence to the report.
            with OUTPUT_FILE.open(
                "a",
                encoding="utf-8",
            ) as file:
                file.write(
                    f"Question {question_number}: "
                    f"{question}\n\n"
                )
                file.write(
                    f"Retrieved chunks: "
                    f"{len(retrieved_chunks)}\n\n"
                )

                # Show every retrieved chunk in ranked order.
                for rank, chunk in enumerate(
                    retrieved_chunks,
                    start=1,
                ):
                    match_types = ", ".join(
                        chunk["match_types"]
                    )
                    file.write(f"Result {rank}\n")
                    file.write(
                        f"  Chunk ID: {chunk['chunk_id']}\n"
                    )
                    file.write(
                        f"  Content type: "
                        f"{chunk['content_type']}\n"
                    )
                    file.write(
                        f"  Document: "
                        f"{chunk['document_name']}\n"
                    )
                    file.write(
                        f"  Node type: {chunk['node_type']}\n"
                    )
                    file.write(
                        f"  Identifier: "
                        f"{chunk['identifier']}\n"
                    )
                    file.write(
                        f"  Node title: "
                        f"{chunk['node_title']}\n"
                    )
                    file.write(
                        f"  Similarity: "
                        f"{chunk['similarity']:.4f}\n"
                    )
                    file.write(
                        f"  Hybrid score: "
                        f"{chunk['hybrid_score']:.6f}\n"
                    )
                    file.write(
                        f"  Match types: {match_types}\n"
                    )
                    file.write(
                        f"  Text: {chunk['text']}\n\n"
                    )

                # Preserve the generated answer for comparison.
                file.write(f"Answer:\n{answer}\n\n")
                file.write("=" * 60 + "\n\n")

            # Keep terminal output short during paid API calls.
            print(
                f"Completed {question_number}/"
                f"{len(QUESTIONS)}: {question}"
            )

    finally:

        # Always release the PostgreSQL connection.
        vector_store.close()

    print(f"\nResults saved to: {OUTPUT_FILE}")


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()
