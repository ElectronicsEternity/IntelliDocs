"""Validated local checkpoints for paid embedding batches."""

import hashlib
import json
from pathlib import Path
import re

from app.constants import CURRENT_EMBEDDING_VERSION, DEFAULT_EMBEDDING_MODEL
from app.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES_FOLDER = settings.DOCUMENT_PROFILES_DIRECTORY


class EmbeddingCheckpointStore:
    """Persist provider results so interrupted indexing can resume safely."""

    def __init__(self, profiles_folder: Path | None = None):
        self.profiles_folder = profiles_folder or DEFAULT_PROFILES_FOLDER

    @staticmethod
    def _safe_folder_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"

    @staticmethod
    def _input_hashes(texts: list[str]) -> list[str]:
        return [
            hashlib.sha256(text.encode("utf-8")).hexdigest()
            for text in texts
        ]

    def _path(
        self,
        owner_id: str,
        document_id: str,
        activity: str,
        batch_number: int,
    ) -> Path:
        folder = (
            self.profiles_folder
            / self._safe_folder_name(owner_id)
            / self._safe_folder_name(document_id)
            / "embedding_batches"
        )
        folder.mkdir(parents=True, exist_ok=True)
        safe_activity = self._safe_folder_name(activity)
        return folder / f"{safe_activity}_{batch_number:04d}.json"

    def load(
        self,
        *,
        owner_id: str,
        document_id: str,
        activity: str,
        batch_number: int,
        texts: list[str],
    ) -> list[list[float]] | None:
        path = self._path(
            owner_id,
            document_id,
            activity,
            batch_number,
        )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        expected = {
            "model": DEFAULT_EMBEDDING_MODEL,
            "embedding_version": CURRENT_EMBEDDING_VERSION,
            "input_hashes": self._input_hashes(texts),
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            return None

        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            return None
        if not all(
            isinstance(vector, list)
            and vector
            and all(isinstance(value, (int, float)) for value in vector)
            for vector in embeddings
        ):
            return None
        return embeddings

    def save(
        self,
        *,
        owner_id: str,
        document_id: str,
        activity: str,
        batch_number: int,
        texts: list[str],
        embeddings: list[list[float]],
    ) -> None:
        path = self._path(
            owner_id,
            document_id,
            activity,
            batch_number,
        )
        payload = {
            "model": DEFAULT_EMBEDDING_MODEL,
            "embedding_version": CURRENT_EMBEDDING_VERSION,
            "input_hashes": self._input_hashes(texts),
            "embeddings": embeddings,
        }
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        # Atomic replacement prevents an interrupted write from becoming a
        # seemingly valid checkpoint on the next processing attempt.
        temporary_path.replace(path)
