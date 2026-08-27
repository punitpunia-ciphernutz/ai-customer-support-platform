from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import KNOWLEDGE_READ, KNOWLEDGE_WRITE
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.application.knowledge_service import KnowledgeService
from app.modules.knowledge.domain.models import KnowledgeSourceType
from app.modules.knowledge.domain.schemas import (
    DocumentAccepted,
    DocumentOut,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    KnowledgeSourceCreate,
    KnowledgeSourceOut,
    TextDocumentCreate,
    URLDocumentCreate,
)
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever
from app.workers.tasks import ingest_document, knowledge_upload_dir

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/sources", response_model=list[KnowledgeSourceOut])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_READ)),
) -> list[KnowledgeSourceOut]:
    return await KnowledgeService(db).list_sources(user.organization_id)


@router.post("/sources", response_model=KnowledgeSourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: KnowledgeSourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_WRITE)),
) -> KnowledgeSourceOut:
    return await KnowledgeService(db).create_source(
        organization_id=user.organization_id,
        name=body.name,
        source_type=body.type,
        configuration=body.configuration,
    )


@router.get("/sources/{source_id}", response_model=KnowledgeSourceOut)
async def get_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_READ)),
) -> KnowledgeSourceOut:
    source = await KnowledgeService(db).get_source(user.organization_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    return source


@router.get("/sources/{source_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_READ)),
) -> list[DocumentOut]:
    service = KnowledgeService(db)
    source = await service.get_source(user.organization_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    return await service.list_documents(user.organization_id, source_id)


@router.post(
    "/sources/{source_id}/documents/text",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_text_document(
    source_id: str,
    body: TextDocumentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_WRITE)),
) -> DocumentAccepted:
    source = await KnowledgeService(db).get_source(user.organization_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    if source.type != KnowledgeSourceType.TEXT:
        raise HTTPException(status_code=400, detail="Source type must be TEXT")

    document = await IngestionService(db).create_pending_document(
        source=source,
        title=body.title,
        content=body.content,
        metadata={"source_type": "TEXT"},
    )
    await db.commit()
    ingest_document.delay(document.id)
    return DocumentAccepted(document=DocumentOut.model_validate(document), job_queued=True)


@router.post(
    "/sources/{source_id}/documents/url",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_url_document(
    source_id: str,
    body: URLDocumentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_WRITE)),
) -> DocumentAccepted:
    source = await KnowledgeService(db).get_source(user.organization_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    if source.type != KnowledgeSourceType.URL:
        raise HTTPException(status_code=400, detail="Source type must be URL")

    url = str(body.url)
    document = await IngestionService(db).create_pending_document(
        source=source,
        title=body.title,
        source_url=url,
        metadata={"source_type": "URL", "url": url},
    )
    await db.commit()
    ingest_document.delay(document.id)
    return DocumentAccepted(document=DocumentOut.model_validate(document), job_queued=True)


@router.post(
    "/sources/{source_id}/documents/pdf",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_pdf_document(
    source_id: str,
    title: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_WRITE)),
) -> DocumentAccepted:
    source = await KnowledgeService(db).get_source(user.organization_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found")
    if source.type != KnowledgeSourceType.PDF:
        raise HTTPException(status_code=400, detail="Source type must be PDF")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty PDF upload")

    document = await IngestionService(db).create_pending_document(
        source=source,
        title=title,
        metadata={"source_type": "PDF", "filename": file.filename},
    )
    pdf_path = knowledge_upload_dir() / f"{document.id}.pdf"
    pdf_path.write_bytes(data)
    await db.commit()
    ingest_document.delay(document.id)
    return DocumentAccepted(document=DocumentOut.model_validate(document), job_queued=True)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_WRITE)),
) -> None:
    deleted = await KnowledgeService(db).delete_document(user.organization_id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    pdf_path = knowledge_upload_dir() / f"{document_id}.pdf"
    if pdf_path.exists():
        pdf_path.unlink()


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    body: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(KNOWLEDGE_READ)),
) -> KnowledgeSearchResponse:
    hits = await PgVectorRetriever(db).search(
        body.query,
        organization_id=user.organization_id,
        top_k=body.top_k,
    )
    return KnowledgeSearchResponse(
        results=[
            KnowledgeSearchResult(
                document_id=hit.document_id,
                title=hit.title,
                content=hit.content,
                score=hit.score,
                chunk_id=hit.chunk_id,
                metadata=hit.metadata,
            )
            for hit in hits
        ]
    )
