# ========================================
# File: exact_identifier_retrieval.py
# ========================================
#
# Purpose
# -------
# Test an exact structural reference through production code.
#
# Responsibilities
# ----------------
# - Ask the Section 6 question.
# - Run the production Retriever.
# - Show exact matches even below the semantic threshold.
# - Leave the database unchanged.
#
# ========================================

from app.constants import SIMILARITY_THRESHOLD
from app.rag.embedder import Embedder
from app.rag.retriever import Retriever
from app.storage.postgres_vector_store import (
    PostgresVectorStore,
)


# ==========================================================
# Test Configuration
# ==========================================================

OWNER_ID = "dev_user"
QUESTION = "What is Section 6 about?"


# ==========================================================
# Exact Identifier Retrieval Test
# ==========================================================

def main() -> None:
    vector_store = PostgresVectorStore()
    retriever = Retriever(
        embedder=Embedder(),
        vector_store=vector_store,
    )

    try:
        results = retriever.retrieve(
            owner_id=OWNER_ID,
            question=QUESTION,
        )
    finally:
        vector_store.close()

    exact_results = [
        result
        for result in results
        if "exact_identifier" in result["match_types"]
    ]

    print("\n=== Exact Identifier Test Started ===")
    print(f"Question: {QUESTION}")
    print(f"Semantic threshold: {SIMILARITY_THRESHOLD}")
    print(f"Exact results retained: {len(exact_results)}\n")

    for rank, result in enumerate(exact_results, start=1):
        below_threshold = (
            result["similarity"] < SIMILARITY_THRESHOLD
        )
        print(
            f"Result {rank} | "
            f"{result['node_type']} "
            f"{result['identifier'] or ''} | "
            f"similarity={result['similarity']:.4f} | "
            f"below threshold={below_threshold}"
        )
        print(f"Title: {result['node_title']}")
        print(f"Text: {result['text']}\n")

    print("=== Exact Identifier Test Ended ===")


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()
