from app.services.documents.service import DocumentService
from app.services.rag.service import RagService
from app.services.usage.tracker import UsageTracker


def get_document_service() -> DocumentService:
    return DocumentService()


def get_rag_service() -> RagService:
    return RagService()


def get_usage_tracker() -> UsageTracker:
    return UsageTracker()
