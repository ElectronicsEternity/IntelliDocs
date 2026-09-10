from dataclasses import dataclass


@dataclass
class Embedding:

    # Parent chunk identifier
    chunk_id: str

    # Embedding vector
    vector: list[float]