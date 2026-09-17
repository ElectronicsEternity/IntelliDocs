from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.services.documents.service import DocumentService
from app.services.storage.supabase_storage import SupabaseDocumentStorage


class FakeRepository:
    def __init__(self):
        self.record = None
        self.statuses = []
        self.cleared = []

    def totals_for_user(self, user_id):
        return 0, 0

    def fail_stale_processing(self, user_id, stale_after_seconds):
        pass

    def clear_processing_artifacts(self, document_id, user_id):
        self.cleared.append((document_id, user_id))

    def create_uploaded(self, **values):
        from datetime import datetime, timezone
        self.record = {
            "id": values["document_id"],
            "user_id": values["user_id"],
            "original_filename": values["original_filename"],
            "storage_path": values["storage_path"],
            "file_size": values["file_size"],
            "page_count": None,
            "processing_status": "uploaded",
            "processing_error": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        return self.record

    def get_for_user(self, document_id, user_id):
        if self.record and self.record["id"] == document_id and self.record["user_id"] == user_id:
            return self.record
        return None

    def set_status(self, document_id, user_id, status, *, error=None, page_count=None):
        self.statuses.append(status)
        self.record["processing_status"] = status
        self.record["processing_error"] = error
        if page_count is not None:
            self.record["page_count"] = page_count


class FakeStorage:
    build_path = staticmethod(SupabaseDocumentStorage.build_path)

    def __init__(self):
        self.uploaded = None

    def upload(self, path, content):
        self.uploaded = (path, content)

    def download(self, path):
        return b"%PDF-1.4 test"

    def delete(self, path):
        pass


class FakeUsage:
    def __init__(self):
        self.events = []

    def record(self, user_id, event_type, **values):
        self.events.append((user_id, event_type, values))

    def ensure_upload_allowed(self, user_id, **values):
        pass

    def ensure_processing_allowed(self, user_id, page_count):
        pass


class SuccessfulWorkflow:
    def process(self, **kwargs):
        assert kwargs["owner_id"] == "user-a"
        assert kwargs["register_document"] is False
        return 3

    def close(self):
        pass


class FailedWorkflow(SuccessfulWorkflow):
    def process(self, **kwargs):
        raise RuntimeError("parser rejected encrypted PDF")


@pytest.mark.anyio
async def test_upload_creates_owner_record_and_isolated_path():
    repository, storage, usage = FakeRepository(), FakeStorage(), FakeUsage()
    service = DocumentService(repository, storage, usage)
    upload = UploadFile(filename="contract.pdf", file=BytesIO(b"%PDF-1.4"))
    record = await service.upload(upload, "user-a")
    assert record["user_id"] == "user-a"
    assert record["storage_path"].startswith("users/user-a/documents/")
    assert storage.uploaded[0] == record["storage_path"]


def test_storage_paths_are_user_isolated():
    a = SupabaseDocumentStorage.build_path("user-a", "doc", "../../unsafe name.pdf")
    b = SupabaseDocumentStorage.build_path("user-b", "doc", "../../unsafe name.pdf")
    assert a == "users/user-a/documents/doc/unsafe_name.pdf"
    assert b == "users/user-b/documents/doc/unsafe_name.pdf"


def test_supabase_storage_adapter_uses_private_bucket_operations():
    calls = []

    class Bucket:
        def upload(self, **kwargs):
            calls.append(("upload", kwargs))

        def download(self, path):
            calls.append(("download", path))
            return b"pdf"

        def remove(self, paths):
            calls.append(("remove", paths))

    class Storage:
        def from_(self, bucket):
            calls.append(("bucket", bucket))
            return Bucket()

    class Client:
        storage = Storage()

    adapter = SupabaseDocumentStorage(client=Client())
    adapter.upload("users/user-a/documents/doc/a.pdf", b"pdf")
    assert adapter.download("users/user-a/documents/doc/a.pdf") == b"pdf"
    adapter.delete("users/user-a/documents/doc/a.pdf")
    assert [call[0] for call in calls].count("bucket") == 3
    assert calls[-1] == ("remove", ["users/user-a/documents/doc/a.pdf"])


def test_document_status_changes_to_ready():
    repository, storage, usage = FakeRepository(), FakeStorage(), FakeUsage()
    repository.create_uploaded(
        document_id="doc-a", user_id="user-a", original_filename="a.pdf",
        storage_path="users/user-a/documents/doc-a/a.pdf", file_size=8, file_hash="hash",
    )
    service = DocumentService(
        repository, storage, usage,
        workflow_factory=SuccessfulWorkflow,
        page_counter=lambda _path: 3,
    )
    result = service.process("doc-a", "user-a")
    assert repository.statuses == ["processing", "ready"]
    assert result["page_count"] == 3


def test_failed_processing_produces_failed_status():
    repository, storage, usage = FakeRepository(), FakeStorage(), FakeUsage()
    repository.create_uploaded(
        document_id="doc-a", user_id="user-a", original_filename="a.pdf",
        storage_path="users/user-a/documents/doc-a/a.pdf", file_size=8, file_hash="hash",
    )
    service = DocumentService(
        repository, storage, usage,
        workflow_factory=FailedWorkflow,
        page_counter=lambda _path: 3,
    )
    with pytest.raises(HTTPException) as error:
        service.process("doc-a", "user-a")
    assert error.value.status_code == 500
    assert repository.statuses == ["processing", "failed"]
    assert repository.record["processing_error"] == (
        "This PDF is password-protected or encrypted. Upload an unlocked copy and retry."
    )


def test_retry_clears_partial_processing_artifacts():
    repository, storage, usage = FakeRepository(), FakeStorage(), FakeUsage()
    repository.create_uploaded(
        document_id="doc-a", user_id="user-a", original_filename="a.pdf",
        storage_path="users/user-a/documents/doc-a/a.pdf", file_size=8, file_hash="hash",
    )
    repository.record["processing_status"] = "failed"
    service = DocumentService(
        repository, storage, usage,
        workflow_factory=SuccessfulWorkflow,
        page_counter=lambda _path: 3,
    )

    service.process("doc-a", "user-a")

    assert repository.cleared == [("doc-a", "user-a")]


@pytest.mark.anyio
async def test_upload_uses_plan_specific_limits():
    class RejectingUsage(FakeUsage):
        def ensure_upload_allowed(self, user_id, **values):
            raise HTTPException(429, "Your Trial plan document limit has been reached.")

    service = DocumentService(FakeRepository(), FakeStorage(), RejectingUsage())
    upload = UploadFile(filename="contract.pdf", file=BytesIO(b"%PDF-1.4"))

    with pytest.raises(HTTPException) as error:
        await service.upload(upload, "user-a")

    assert error.value.status_code == 429
    assert "Trial plan" in str(error.value.detail)
