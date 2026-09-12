from dataclasses import dataclass
from datetime import datetime


@dataclass
class DocumentNode:

    id: str

    document_id: str

    parent_id: str | None

    node_type: str

    identifier: str

    title: str

    sequence_no: int

    depth: int

    start_page: int | None = None

    # Zero-based position where this node's title begins in start_page text.
    start_character: int | None = None

    end_page: int | None = None

    created_at: datetime | None = None
