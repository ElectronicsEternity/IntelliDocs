# ========================================
# File: retriever_combine_results.py
# ========================================
#
# Purpose
# -------
# Test how Retriever combines search results.
#
# Responsibilities
# ----------------
# - Use controlled search results.
# - Confirm duplicate chunks are merged.
# - Confirm weak results are removed.
# - Confirm identifier weighting is stronger.
# - Confirm top_k limits the final results.
#
# ========================================

from app.rag.retriever import Retriever


# ==========================================================
# Controlled Search Results
# ==========================================================

vector_results = [
    {
        "chunk_id": "chunk-10",
        "text": "Section 4 content",
        "similarity": 0.82,
    },
    {
        "chunk_id": "chunk-20",
        "text": "General wage content",
        "similarity": 0.70,
    },
    {
        "chunk_id": "chunk-weak",
        "text": "Weak result",
        "similarity": 0.39,
    },
]

node_results = [
    {
        "chunk_id": "chunk-10",
        "node_id": "node-4",
        "node_title": "Minimum wages",
        "similarity": 0.76,
    },
    {
        "chunk_id": "chunk-30",
        "node_id": "node-7",
        "node_title": "Working days",
        "similarity": 0.68,
    },
]

identifier_results = [
    {
        "chunk_id": "chunk-40",
        "node_id": "node-5",
        "identifier": "5",
        "similarity": 0.65,
    },
]


# ==========================================================
# Test
# ==========================================================

def main() -> None:
    print("=== Retriever Combine Test Started ===")

    # Create Retriever without database dependencies.
    retriever = object.__new__(Retriever)

    # Test the result-combination method directly.
    results = retriever._combine_results(
        vector_results=vector_results,
        node_results=node_results,
        identifier_results=identifier_results,
        top_k=10,
    )

    # Display the final relevance order.
    for rank, result in enumerate(results, start=1):
        score = result["hybrid_score"]
        match_types = result["match_types"]
        print(
            f"Rank {rank} | {result['chunk_id']} | "
            f"score={score:.5f} | "
            f"matches={match_types}"
        )

    result_ids = [result["chunk_id"] for result in results]

    # Confirm the repeated chunk appears only once.
    duplicate_merged = result_ids.count("chunk-10") == 1

    # Confirm results below the threshold are removed.
    weak_removed = "chunk-weak" not in result_ids

    # Confirm agreement across searches ranks first.
    agreement_ranked_first = result_ids[0] == "chunk-10"

    # Confirm identifier weighting beats one normal match.
    identifier_beats_single = (
        result_ids.index("chunk-40")
        < result_ids.index("chunk-20")
    )

    # Confirm top_k limits the returned result count.
    limited_results = retriever._combine_results(
        vector_results=vector_results,
        node_results=node_results,
        identifier_results=identifier_results,
        top_k=2,
    )
    top_k_respected = len(limited_results) == 2

    print("\nResults:")
    print(f"Duplicate merged: {duplicate_merged}")
    print(f"Weak result removed: {weak_removed}")
    print(f"Agreement ranked first: {agreement_ranked_first}")
    print(
        "Identifier beats single normal match: "
        f"{identifier_beats_single}"
    )
    print(f"top_k respected: {top_k_respected}")
    print("=== Retriever Combine Test Ended ===")

    # Stop immediately if any expected behavior fails.
    assert duplicate_merged
    assert weak_removed
    assert agreement_ranked_first
    assert identifier_beats_single
    assert top_k_respected


if __name__ == "__main__":
    main()
