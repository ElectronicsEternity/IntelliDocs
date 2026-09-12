# ========================================
# File: chunk_analyzer.py
# ========================================
#
# Current Status
# --------------
# Not used by the main hierarchy-based ingestion workflow.
# Retained for the legacy fallback and future experiments.
#
# ========================================

from math import ceil, floor


class ChunkAnalyzer:

    #******************** Recommend Chunk Size *********************#

    def recommend_chunk_size(
        self,
        page_token_counts: list[int],
        verbose: bool = False
    ) -> int:

        # Total pages
        total_pages = len(page_token_counts)
        print(f"\nTotal Pages : {total_pages}\n")

        # Search range
        low = self.calculate_p50(page_token_counts)
        high = max(page_token_counts)

        # Store smallest passing chunk size
        recommended_chunk_size = high

        # Binary search
        while low <= high:

            # Calculate midpoint
            chunk_size = (low + high) // 2

            total_chunks = 0
            pages_over_2_chunks = 0

            # Early fail flag
            candidate_failed = False

            max_pages_over_2_chunks = floor(total_pages * 0.10)

            # Simulate chunking
            for page_tokens in page_token_counts:

                chunks_for_page = ceil(
                    page_tokens / chunk_size
                )

                total_chunks += chunks_for_page

                if chunks_for_page > 2:
                    pages_over_2_chunks += 1

                # Early fail
                if (
                    pages_over_2_chunks
                    > max_pages_over_2_chunks
                ):
                    candidate_failed = True
                    break

            # Candidate already failed
            if candidate_failed:
                passed = False

            else:

                # Average chunks per page
                average_chunks_per_page = (
                    total_chunks / total_pages
                )

                # Check criteria
                passed = (
                    average_chunks_per_page < 2
                )

            if verbose:
                pages_over_2_chunks_pct = (
                    pages_over_2_chunks
                    / total_pages
                    * 100
                )
            print(
                f"Chunk Size: {chunk_size:4}"
                f" | ACPP: {average_chunks_per_page:.2f}"
                f" | >2: "
                f"{pages_over_2_chunks}/"
                f"{max_pages_over_2_chunks}"
                f" | {'PASS' if passed else 'FAIL'}"
            )
            if passed:
                # Store smallest
                # passing chunk size
                recommended_chunk_size = (
                    chunk_size
                )

                # Search left
                high = chunk_size - 1

            else:

                # Search right
                low = chunk_size + 1

        #******************** Debug *********************#

        print("Exited While Loop")

        print(
            f"\nRecommended Chunk Size: "
            f"{recommended_chunk_size}"
        )

        return recommended_chunk_size

    #******************** Calculate P50 *********************#

    def calculate_p50(
        self,
        values: list[int]
    ) -> int:

        sorted_values = sorted(values)
        n = len(sorted_values)

        if n % 2 == 0:

            return (
                sorted_values[(n // 2) - 1]
                + sorted_values[n // 2]
            ) // 2

        return sorted_values[n // 2]
