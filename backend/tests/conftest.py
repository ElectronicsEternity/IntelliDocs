from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_document_service
from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app


def document_record(document_id: str, owner: str, status: str = "uploaded") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": document_id,
        "user_id": owner,
        "original_filename": "example.pdf",
        "storage_path": f"users/{owner}/documents/{document_id}/example.pdf",
        "file_size": 8,
        "page_count": None,
        "processing_status": status,
        "processing_error": None,
        "created_at": now,
        "updated_at": now,
    }


class FakeDocumentService:
    def __init__(self, records: dict[str, dict] | None = None):
        self.records = records or {}
        self.deleted: list[tuple[str, str]] = []

    def list(self, user_id):
        return [record for record in self.records.values() if record["user_id"] == user_id]

    def get(self, document_id, user_id):
        from fastapi import HTTPException

        record = self.records.get(document_id)
        if not record or record["user_id"] != user_id:
            raise HTTPException(404, "Document not found.")
        return record

    def delete(self, document_id, user_id):
        self.get(document_id, user_id)
        self.deleted.append((document_id, user_id))


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def user_a_client(client):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("user-a")
    return client


@pytest.fixture
def override_document_service():
    def apply(service):
        app.dependency_overrides[get_document_service] = lambda: service
        return service
    return apply
