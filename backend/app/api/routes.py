from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.api.dependencies import get_document_service, get_rag_service, get_usage_tracker
from app.core.auth import AuthenticatedUser, get_current_user
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.schemas.usage import UsageSummaryResponse
from app.services.documents.service import DocumentService
from app.services.rag.service import RagService
from app.services.usage.tracker import UsageTracker

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/usage", response_model=UsageSummaryResponse)
def usage_summary(
    user: AuthenticatedUser = Depends(get_current_user),
    tracker: UsageTracker = Depends(get_usage_tracker),
):
    return tracker.summary(user.id)


@router.post("/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    return await service.upload(file, user.id)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    user: AuthenticatedUser = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    return {"documents": service.list(user.id)}


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    return service.get(document_id, user.id)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    service.delete(document_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/process", response_model=DocumentResponse)
def process_document(
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    return service.process(document_id, user.id)


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: RagService = Depends(get_rag_service),
):
    try:
        return service.chat(
            question=request.question,
            user_id=user.id,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
        )
    finally:
        service.close()
