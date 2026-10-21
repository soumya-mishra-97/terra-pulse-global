"""Load approved methodology documents (Markdown with a small front-matter block) and chunk them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
REQUIRED = ("id", "title", "publisher", "published", "source_url", "approved")


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    publisher: str
    published: str
    source_url: str
    body: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc: Document
    heading: str
    text: str


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    m = FRONT_MATTER.match(raw)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, raw[m.end():]


def load_documents(directory: Path) -> list[Document]:
    """Only documents explicitly marked `approved: true` with complete metadata are loaded."""
    docs = []
    for path in sorted(Path(directory).glob("*.md")):
        meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        if any(not meta.get(k) for k in REQUIRED) or meta["approved"].lower() != "true":
            continue
        docs.append(Document(id=meta["id"], title=meta["title"], publisher=meta["publisher"],
                             published=meta["published"], source_url=meta["source_url"], body=body))
    return docs


def chunk_document(doc: Document, max_chars: int = 1200) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading = doc.title
    buf: list[str] = []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            for i in range(0, len(text), max_chars):
                chunks.append(Chunk(f"{doc.id}#{len(chunks) + 1}", doc, heading, text[i: i + max_chars]))
        buf.clear()

    for line in doc.body.splitlines():
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip()
        else:
            buf.append(line)
    flush()
    return chunks
