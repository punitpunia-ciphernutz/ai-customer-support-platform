"""Content loaders for TEXT, PDF, and single-URL sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.modules.knowledge.infrastructure.parsers.normalize import html_to_text, normalize_text


@dataclass
class LoadedContent:
    title: str
    text: str
    source_url: str | None = None
    metadata: dict | None = None


class DocumentLoader(ABC):
    @abstractmethod
    async def load(self) -> LoadedContent:
        raise NotImplementedError


class TextLoader(DocumentLoader):
    def __init__(self, text: str, title: str = "Untitled") -> None:
        self.text = text
        self.title = title

    async def load(self) -> LoadedContent:
        return LoadedContent(title=self.title, text=normalize_text(self.text), metadata={"source_type": "TEXT"})


class PDFLoader(DocumentLoader):
    def __init__(self, data: bytes, title: str = "PDF Document") -> None:
        self.data = data
        self.title = title

    async def load(self) -> LoadedContent:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(self.data))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = normalize_text("\n\n".join(parts))
        return LoadedContent(
            title=self.title,
            text=text,
            metadata={"source_type": "PDF", "page_count": len(reader.pages)},
        )


class URLLoader(DocumentLoader):
    """One URL → one document (no crawler)."""

    def __init__(self, url: str, title: str | None = None) -> None:
        self.url = url
        self.title = title

    async def load(self) -> LoadedContent:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(self.url, headers={"User-Agent": "SupportPlatformBot/0.1"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            body = response.text
            if "html" in content_type or body.lstrip().lower().startswith("<!doctype") or "<html" in body[:200].lower():
                text = html_to_text(body)
            else:
                text = normalize_text(body)
            title = self.title or self.url
            return LoadedContent(
                title=title,
                text=text,
                source_url=self.url,
                metadata={"source_type": "URL", "url": self.url},
            )
