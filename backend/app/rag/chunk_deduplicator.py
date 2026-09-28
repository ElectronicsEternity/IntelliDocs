"""Remove exact repeated chunks without collapsing distinct source locations."""
from dataclasses import asdict
import json

from app.models.chunk import Chunk


def deduplicate_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Keep the first chunk, preserving its citation and hierarchy metadata.

    IDs and hierarchy paths are not evidence of different physical content.
    Source boundaries and table geometry are: never merge across these.
    Comparison is exact, not semantic, case-insensitive or whitespace-normalized.
    """
    seen = set()
    unique = []
    for chunk in chunks:
        source = asdict(chunk.metadata)
        source.pop('hierarchy_path', None)
        key = (chunk.document_id, chunk.content_type, chunk.page_number,
               chunk.text, json.dumps(source, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    for number, chunk in enumerate(unique, 1):
        chunk.chunk_number = number
    return unique
