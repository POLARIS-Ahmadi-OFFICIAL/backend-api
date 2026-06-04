"""Export agent outputs as markdown + downloadable PDF."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.paths import get_user_data_dir

_DOCS_SUBDIR = "documents"


def _documents_root() -> Path:
    root = Path(get_user_data_dir()) / _DOCS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _strip_md_for_pdf(text: str) -> str:
    t = text or ""
    t = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).replace("```", ""), t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    return t.strip()


def _build_pdf(title: str, body: str, pdf_path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(title.replace("&", "&amp;"), styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))
    plain = _strip_md_for_pdf(body)
    for block in plain.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        safe = (
            block.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        story.append(Paragraph(safe, styles["BodyText"]))
        story.append(Spacer(1, 0.12 * inch))

    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    doc.build(story)


def export_agent_document(
    *,
    title: str,
    markdown_body: str,
    agent: str,
    memory: Any = None,
) -> Dict[str, str]:
    """Persist markdown + PDF; return ids/urls for API clients."""
    doc_id = uuid.uuid4().hex[:16]
    folder = _documents_root() / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    md_path = folder / "document.md"
    pdf_path = folder / "document.pdf"
    body = (markdown_body or "").strip()
    md_path.write_text(body, encoding="utf-8")
    _build_pdf(title, body, pdf_path)

    meta = {
        "document_id": doc_id,
        "title": title,
        "agent": agent,
        "markdown": body,
        "pdf_url": f"/api/v1/documents/{doc_id}/pdf",
        "markdown_url": f"/api/v1/documents/{doc_id}/markdown",
    }
    if memory is not None:
        memory.set_var(f"document_{agent.replace(' ', '_').lower()}", meta)
        memory.set_var("last_document", meta)
    return meta


def get_document_folder(document_id: str) -> Optional[Path]:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", document_id or "")
    if not safe:
        return None
    folder = _documents_root() / safe
    return folder if folder.is_dir() else None
