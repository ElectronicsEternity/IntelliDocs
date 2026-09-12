import hashlib
import logging
from pathlib import Path
import tempfile
import uuid

from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.ingestion.document_ingestion_workflow import DocumentIngestionWorkflow
from app.services.documents.repository import DocumentRepository
from app.services.storage.supabase_storage import SupabaseDocumentStorage
from app.services.usage.tracker import UsageTracker

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository | None = None,
        storage: SupabaseDocumentStorage | None = None,
        usage: UsageTracker | None = None,
        workflow_factory=DocumentIngestionWorkflow,
    ) -> None:
        self.repository = repository or DocumentRepository()
        self.storage = storage or SupabaseDocumentStorage()
        self.usage = usage or UsageTracker()
        self.workflow_factory = workflow_factory

    async def upload(self, upload: UploadFile, user_id: str) -> dict:
        filename = Path(upload.filename or "").name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are supported.")
        content = await upload.read(settings.MAX_UPLOAD_BYTES + 1)
        if not content or len(content) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The PDF exceeds the configured upload limit.")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "The uploaded file is not a valid PDF.")

        document_count, storage_bytes = self.repository.totals_for_user(user_id)
        if document_count >= settings.MAX_DOCUMENTS_PER_USER:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Document limit reached.")
        if storage_bytes + len(content) > settings.MAX_STORAGE_BYTES_PER_USER:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Storage limit reached.")

        document_id = str(uuid.uuid4())
        storage_path = self.storage.build_path(user_id, document_id, filename)
        self.storage.upload(storage_path, content)
        try:
            record = self.repository.create_uploaded(
                document_id=document_id,
                user_id=user_id,
                original_filename=filename,
                storage_path=storage_path,
                file_size=len(content),
                file_hash=hashlib.sha256(content).hexdigest(),
            )
        except Exception:
            self.storage.delete(storage_path)
            raise
        self.usage.record(user_id, "document_uploaded", document_id=document_id)
        self.usage.record(user_id, "storage_bytes", quantity=len(content), document_id=document_id)
        return record

    def list(self, user_id: str) -> list[dict]:
        return self.repository.list_for_user(user_id)

    def get(self, document_id: str, user_id: str) -> dict:
        record = self.repository.get_for_user(document_id, user_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
        return record

    def delete(self, document_id: str, user_id: str) -> None:
        record = self.get(document_id, user_id)
        self.storage.delete(record["storage_path"])
        if not self.repository.delete_for_user(document_id, user_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")

    def process(self, document_id: str, user_id: str) -> dict:
        record = self.get(document_id, user_id)
        if record["processing_status"] == "processing":
            raise HTTPException(status.HTTP_409_CONFLICT, "Document is already processing.")
        self.repository.set_status(document_id, user_id, "processing")
        temporary_path: Path | None = None
        workflow = None
        try:
            content = self.storage.download(record["storage_path"])
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
                temporary_file.write(content)
                temporary_path = Path(temporary_file.name)
            workflow = self.workflow_factory()
            page_count = workflow.process(
                pdf_path=temporary_path,
                owner_id=user_id,
                document_id=document_id,
                register_document=False,
                original_filename=record["original_filename"],
            )
            if isinstance(page_count, bool):
                page_count = None
            self.repository.set_status(document_id, user_id, "ready", page_count=page_count)
            if page_count:
                self.usage.record(user_id, "pages_processed", quantity=page_count, document_id=document_id)
        except Exception as exc:
            logger.exception("Document processing failed for %s", document_id)
            message = str(exc).strip()[:1000] or "Document processing failed."
            self.repository.set_status(document_id, user_id, "failed", error=message)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Document processing failed.") from None
        finally:
            if workflow is not None:
                try:
                    workflow.close()
                except Exception:
                    logger.exception("Failed to close processing resources for %s", document_id)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return self.get(document_id, user_id)
