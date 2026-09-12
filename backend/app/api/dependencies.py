from app.services.documents.service import DocumentService
from app.services.rag.service import RagService


def get_document_service() -> DocumentService:
    return DocumentService()


def get_rag_service() -> RagService:
    return RagService()
