# Overview

The RAG (Retrieval-Augmented Generation) module is
responsible for transforming uploaded documents into
retrievable knowledge.

The module processes documents through multiple stages:

1. Parse document content
2. Generate page token statistics
3. Determine optimal chunk size
4. Split content into chunks
5. Generate embeddings
6. Store chunks and embeddings
7. Retrieve relevant chunks during search

This README currently documents the
`ChunkAnalyzer` component.

# File Responsibilities

+---------------------+--------------------------------------+
| File                | Responsibility                       |
+---------------------+--------------------------------------+
| chunk_analyzer.py   | Recommend optimal chunk size         |
+---------------------+--------------------------------------+

# Chunk Analyzer

## Purpose

The `ChunkAnalyzer` determines the optimal chunk size
for a document before chunk generation begins.

Instead of using a fixed chunk size for all documents,
the analyzer evaluates the token distribution of the
current document and recommends the smallest chunk
size that satisfies the defined acceptance criteria.

## Why It Exists

Different documents have different structures.

Example:

```text
Document A
Average Tokens/Page = 180

Document B
Average Tokens/Page = 950
```

Using the same chunk size for both documents may
produce poor retrieval quality.

The analyzer attempts to find a chunk size that:

- Minimizes unnecessary chunk splitting
- Preserves page boundaries
- Improves retrieval quality
- Reduces storage requirements

# Acceptance Criteria

A chunk size is considered valid when:

```text
Average Chunks Per Page (ACPP) < 2
```

AND

```text
Pages Requiring More Than 2 Chunks < 10%
```

# Execution Flow

Generate Page Token Counts
    ↓
Calculate P50
    ↓
Determine Search Range
(P50 → Maximum Tokens/Page)
    ↓
Binary Search
    ↓
Simulate Chunking
    ↓
Evaluate Acceptance Criteria
    ↓
Store Smallest Passing Chunk Size
    ↓
Return Recommended Chunk Size

# Binary Search Strategy

The analyzer uses binary search to avoid testing every
possible chunk size.

Example:

```text
P50 = 355
Max Tokens/Page = 1630
```

Search Range:

```text
355 ---------------- 1630
```

Binary Search:

```text
992
 ↓
673
 ↓
832
 ↓
752
 ↓
...
```

The algorithm continues until the smallest valid
chunk size is found.

# Simulation Logic

For each candidate chunk size:

```text
For Every Page
    ↓
Calculate Chunks Required
    ↓
Track Total Chunks
    ↓
Track Pages Requiring > 2 Chunks
    ↓
Evaluate Acceptance Criteria
```

Chunk Calculation:

```text
Chunks Required
=
Ceiling(
    Page Tokens
    ÷
    Chunk Size
)
```

Example:

```text
Page Tokens = 820
Chunk Size = 400

820 ÷ 400
=
2.05

Ceiling(2.05)
=
3 Chunks
```

# Early Failure Optimization

The analyzer stops processing a candidate chunk size
as soon as it becomes impossible to satisfy the
acceptance criteria.

Example:

```text
Total Pages = 100

Maximum Allowed
Pages > 2 Chunks

=
10
```

If the simulation reaches:

```text
Pages > 2 Chunks
=
11
```

the candidate immediately fails and the remaining
pages are skipped.

This reduces unnecessary processing for large
documents.

# Inputs

```python
page_token_counts: list[int]
```

Example:

```python
[
    120,
    180,
    250,
    400,
    520,
    810
]
```

# Outputs

```python
int
```

Example:

```python
550
```

# Example

Document Statistics:

```text
Pages                 : 127
Min Tokens/Page       : 18
Average Tokens/Page   : 392
Median Tokens/Page    : 355
P75 Tokens/Page       : 510
P90 Tokens/Page       : 820
Max Tokens/Page       : 1630
```

Simulation Result:

```text
Chunk Size 540 : FAIL
Chunk Size 560 : PASS
Chunk Size 550 : PASS
Chunk Size 545 : FAIL
Chunk Size 548 : FAIL
Chunk Size 549 : FAIL
```

Final Recommendation:

```text
Recommended Chunk Size
=
550
```

# Future Enhancements

Planned enhancements include:

- P25, P75, P90 and P95 analysis
- Mode range detection
- Document classification
- Adaptive chunk overlap recommendation
- Chunk quality scoring
- Multi-document benchmarking