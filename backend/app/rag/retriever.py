# ========================================
# File: retriever.py
# ========================================
#
# Purpose
# -------
# Retrieve relevant chunks for one question.
#
# Responsibilities
# ----------------
# - Run vector similarity search.
# - Run hierarchy-aware node-vector search.
# - Recognize exact structural identifiers.
# - Combine both result lists without duplicates.
#
# ========================================

from app.constants import SIMILARITY_THRESHOLD, TOP_K
from app.rag.embedder import Embedder
from app.services.usage.ai_usage import ai_usage_context
from app.storage.postgres_vector_store import (
    PostgresVectorStore,
)


# ==========================================================
# Retriever
# ==========================================================

class Retriever:

    def __init__(
        self,
        embedder: Embedder,
        vector_store: PostgresVectorStore,
    ):
        self.embedder = embedder
        self.vector_store = vector_store

    # Run vector and hierarchy retrieval together.
    def retrieve(
        self,
        question: str,
        owner_id: str,
        top_k: int = TOP_K,
    ) -> list[dict]:
        with ai_usage_context(user_id=owner_id, embedding_activity="query_embedding"):
            question_embedding = self.embedder.generate_embedding(question)

        # Search all chunks directly by meaning.
        vector_results = self.vector_store.search(
            owner_id=owner_id,
            embedding=question_embedding,
            top_k=top_k,
        )
        # Search similar hierarchy nodes and descendants.
        node_results = (
            self.vector_store.search_node_hierarchy(
                owner_id=owner_id,
                embedding=question_embedding,
                top_k=top_k,
            )
        )

        # Exact structural references bypass semantic guessing.
        identifier_results = (
            self.vector_store.search_exact_identifier(
                owner_id=owner_id,
                query=question,
                embedding=question_embedding,
                top_k=top_k,
            )
        )

        return self._combine_results(
            vector_results,
            node_results,
            identifier_results,
            top_k,
        )

    # Fuse ranked lists while retaining one copy per chunk.
    def _combine_results(
        self,
        vector_results: list[dict],
        node_results: list[dict],
        identifier_results: list[dict],
        top_k: int,
    ) -> list[dict]:
        combined = {}
        # # random number to control
        # how strongly result rank affects the combined score.
        rank_offset = 60
        search_paths = (
            ("chunk_vector", vector_results, 1.0),
            ("node_vector", node_results, 1.0),
            ("exact_identifier",identifier_results, 2.0,),
        )

        # Add reciprocal-rank credit from each search path.
        for search_type, results, weight in search_paths:
            # Assign each result a rank based on
            # its relevance order.
            # Start ranking from 1 instead of 0
            for rank, result in enumerate(results, start=1):
                is_exact_identifier = (
                    search_type == "exact_identifier"
                )

                # Semantic searches require the threshold.
                # Exact structural matches bypass it.
                if (
                    not is_exact_identifier
                    and
                    result["similarity"]
                    < SIMILARITY_THRESHOLD
                ):
                    continue

                chunk_id = result["chunk_id"]

                if chunk_id not in combined:
                    combined[chunk_id] = result.copy()
                    # hybrid score starts at 0.0
                    combined[chunk_id]["hybrid_score"] = 0.0
                    # create empty list to store match types
                    combined[chunk_id]["match_types"] = []

                stored = combined[chunk_id]

                # Preserve fields unique to either search path.
                for key, value in result.items():
                    if key not in stored:
                        stored[key] = value

                stored["hybrid_score"] += weight / (
                    rank_offset + rank
                )
                stored["match_types"].append(search_type)

        ranked_results = sorted(
            combined.values(),
            key=lambda result: result["hybrid_score"],
            reverse=True,
        )
        return ranked_results[:top_k]
