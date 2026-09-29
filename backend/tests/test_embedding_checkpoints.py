import json

from app.indexing.embedding_checkpoint_store import EmbeddingCheckpointStore


def test_embedding_checkpoint_round_trip_and_input_validation(tmp_path):
    store = EmbeddingCheckpointStore(profiles_folder=tmp_path)
    arguments = {
        "owner_id": "user-a",
        "document_id": "doc-a",
        "activity": "chunk_embedding",
        "batch_number": 1,
        "texts": ["first", "second"],
    }
    embeddings = [[0.1, 0.2], [0.3, 0.4]]

    store.save(**arguments, embeddings=embeddings)

    assert store.load(**arguments) == embeddings
    assert store.load(**{**arguments, "texts": ["changed", "second"]}) is None


def test_embedding_checkpoint_rejects_incomplete_vectors(tmp_path):
    store = EmbeddingCheckpointStore(profiles_folder=tmp_path)
    arguments = {
        "owner_id": "user-a",
        "document_id": "doc-a",
        "activity": "node_embedding",
        "batch_number": 2,
        "texts": ["one"],
    }
    store.save(**arguments, embeddings=[[0.1]])
    checkpoint = store._path(
        arguments["owner_id"],
        arguments["document_id"],
        arguments["activity"],
        arguments["batch_number"],
    )
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["embeddings"] = []
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load(**arguments) is None
