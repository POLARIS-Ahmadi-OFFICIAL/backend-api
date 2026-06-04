from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from typing import Annotated

from app.core.auth import AuthUser
from app.core.deps import get_current_user
from app.services.document_export import get_document_folder

router = APIRouter()


@router.get("/documents/{document_id}/markdown")
def get_document_markdown(
    document_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> PlainTextResponse:
    folder = get_document_folder(document_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Document not found")
    md = folder / "document.md"
    if not md.is_file():
        raise HTTPException(status_code=404, detail="Markdown not found")
    return PlainTextResponse(md.read_text(encoding="utf-8"))


@router.get("/documents/{document_id}/pdf")
def download_document_pdf(
    document_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> FileResponse:
    folder = get_document_folder(document_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Document not found")
    pdf = folder / "document.pdf"
    if not pdf.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        path=str(pdf),
        media_type="application/pdf",
        filename=f"polaris_{document_id}.pdf",
    )
