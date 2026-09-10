# ========================================
# File: node_scope_token_counter.py
# ========================================
#
# Purpose
# -------
# Count tokens in text extracted for each hierarchy scope.
#
# Responsibilities
# ----------------
# - Preserve the original layout text.
# - Create normalized text for downstream RAG processing.
# - Count tokens without unnecessary PDF layout whitespace.
#
# ========================================

# Import the application's tokenizer.
from app.rag.tokenizer import Tokenizer


# ==========================================================
# Node Scope Token Counter
# ==========================================================

# Normalize and count the text belonging to each node scope.
class NodeScopeTokenCounter:

    # Store the tokenizer used to count each scope.
    def __init__(self, tokenizer: Tokenizer):

        # Keep the supplied tokenizer for later method calls.
        self.tokenizer = tokenizer

    # Return scope copies containing normalized text and token counts.
    def count_scope_tokens(self, scopes: list[dict]) -> list[dict]:
        """Return copies of node scopes containing their token counts."""

        # Collect the processed scope copies without changing the originals.
        counted_scopes = []

        # Process every extracted hierarchy scope individually.
        for scope in scopes:

            # Copy the scope so its original dictionary remains unchanged.
            counted_scope = scope.copy()

            # Replace repeated spaces and line breaks with one normal space.
            normalized_text = " ".join(scope["text"].split())

            # Keep normalized text for later chunking and embedding stages.
            counted_scope["normalized_text"] = normalized_text

            # Count only meaningful normalized text, not PDF layout padding.
            counted_scope["token_count"] = self.tokenizer.count_tokens(normalized_text)

            # Add the completed scope copy to the returned collection.
            counted_scopes.append(counted_scope)

        # Return all normalized and counted hierarchy scopes.
        return counted_scopes
