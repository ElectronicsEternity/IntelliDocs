# ========================================
# File: chunk_analyzer_test.py
# ========================================
#
# Current Status
# --------------
# Not part of the current hierarchy-based workflow tests.
# Retained for future ChunkAnalyzer experimentation.
#
# ========================================

from app.rag.chunk_analyzer import ChunkAnalyzer


#******************** Sample Page Tokens *********************#

page_token_counts = [
    200,
    210,
    220,
    230,
    240,
    250,
    260,
    270,
    280,
    5000
]


#******************** Execute Test *********************#

def main():


    analyzer = ChunkAnalyzer()

    recommended_chunk_size = (
        analyzer.recommend_chunk_size(
            page_token_counts=page_token_counts,
            verbose=True
        )
    )


#******************** Entry Point *********************#

if __name__ == "__main__":
    main()
