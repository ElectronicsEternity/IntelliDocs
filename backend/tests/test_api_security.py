from app.api.dependencies import get_document_service
from app.main import app
from conftest import FakeDocumentService, document_record


def test_health_endpoint_works(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthenticated_access_is_rejected(client):
    response = client.get("/documents")
    assert response.status_code == 401


def test_user_a_cannot_access_user_b_document(user_a_client):
    service = FakeDocumentService({"doc-b": document_record("doc-b", "user-b")})
    app.dependency_overrides[get_document_service] = lambda: service
    assert user_a_client.get("/documents/doc-b").status_code == 404


def test_user_a_cannot_delete_user_b_document(user_a_client):
    service = FakeDocumentService({"doc-b": document_record("doc-b", "user-b")})
    app.dependency_overrides[get_document_service] = lambda: service
    assert user_a_client.delete("/documents/doc-b").status_code == 404
    assert service.deleted == []
