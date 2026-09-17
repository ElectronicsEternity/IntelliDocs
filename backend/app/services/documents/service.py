import hashlib
import logging
from pathlib import Path
import tempfile
import uuid

from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader

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
        page_counter=None,
    ) -> None:
        self.repository = repository or DocumentRepository()
        self.storage = storage or SupabaseDocumentStorage()
        self.usage = usage or UsageTracker()
        self.workflow_factory = workflow_factory
        self.page_counter = page_counter or self._count_pdf_pages

    @staticmethod
    def _count_pdf_pages(path: Path) -> int:
        return len(PdfReader(str(path)).pages)

    @staticmethod
    def _public_processing_error(error: Exception) -> str:
        if isinstance(error, HTTPException):
            return str(error.detail)
        message = str(error).casefold()
        if "encrypt" in message or "password" in message:
            return "This PDF is password-protected or encrypted. Upload an unlocked copy and retry."
        if "page limit" in message:
            return "This PDF exceeds the page-processing limit for your plan."
        if "invalid" in message or "damaged" in message or "corrupt" in message:
            return "This PDF appears to be damaged or unreadable. Try exporting it again and retry."
        return "We could not process this PDF. You can retry, or upload a newly exported copy."

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
        self.usage.ensure_upload_allowed(
            user_id,
            document_count=document_count,
            storage_bytes=storage_bytes,
            incoming_bytes=len(content),
        )

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
        self.repository.fail_stale_processing(user_id, settings.PROCESSING_STALE_AFTER_SECONDS)
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
        if record["processing_status"] == "failed":
            self.repository.clear_processing_artifacts(document_id, user_id)
        self.repository.set_status(document_id, user_id, "processing")
        temporary_path: Path | None = None
        workflow = None
        try:
            content = self.storage.download(record["storage_path"])
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
                temporary_file.write(content)
                temporary_path = Path(temporary_file.name)
            page_count = self.page_counter(temporary_path)
            if page_count > settings.MAX_PAGES_PER_DOCUMENT:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "This PDF exceeds the maximum pages allowed per document.",
                )
            self.usage.ensure_processing_allowed(user_id, page_count)
            workflow = self.workflow_factory()
            processed_page_count = workflow.process(
                pdf_path=temporary_path,
                owner_id=user_id,
                document_id=document_id,
                register_document=False,
                original_filename=record["original_filename"],
            )
            if not isinstance(processed_page_count, bool) and processed_page_count is not None:
                page_count = processed_page_count
            self.repository.set_status(document_id, user_id, "ready", page_count=page_count)
            if page_count:
                self.usage.record(user_id, "pages_processed", quantity=page_count, document_id=document_id)
        except Exception as exc:
            logger.exception("Document processing failed for %s", document_id)
            message = self._public_processing_error(exc)
            self.repository.set_status(document_id, user_id, "failed", error=message)
            if isinstance(exc, HTTPException):
                raise exc from None
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, message) from None
        finally:
            if workflow is not None:
                try:
                    workflow.close()
                except Exception:
                    logger.exception("Failed to close processing resources for %s", document_id)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return self.get(document_id, user_id)
