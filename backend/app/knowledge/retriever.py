"""Retriever interface plus a dependency-free BM25 implementation.

`Retriever` is the seam for a later milestone: an embeddings + vector-store retriever (e.g.
pgvector) can implement the same `retrieve()` signature without touching agent code.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.knowledge.documents import Chunk, chunk_document, load_documents
from app.knowledge.sanitize import sanitize_chunk

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("a an and are as at be by for from has have how in is it its of on or that the this to was were what when "
           "which who why will with does do can".split())
SYNONYMS = {
    "tfr": ["fertility"], "fertility": ["births", "woman"], "ageing": ["aging", "65"], "aging": ["ageing", "65"],
    "elderly": ["65", "ageing"], "growth": ["growth", "change"], "migrants": ["migration"], "immigration": ["migration"],
    "emigration": ["migration"], "uncertainty": ["uncertainty", "intervals"], "counter": ["illustrative"],
    "projection": ["projections"], "forecast": ["projection"], "urbanisation": ["urban"], "urbanization": ["urban"],
    "density": ["density", "land"], "mortality": ["death", "life"],
}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


@dataclass(frozen=True)
class RetrievedChunk:
    label: str  # citation label, e.g. "D1"
    chunk_id: str
    doc_id: str
    title: str
    heading: str
    publisher: str
    published: str
    source_url: str
    text: str
    score: float
    flagged_lines: list[str] = field(default_factory=list)


class Retriever(Protocol):
    def retrieve(self, query: str, k: int = 4) -> list[RetrievedChunk]: ...


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75, min_score: float = 0.5) -> None:
        self.chunks = chunks
        self.k1, self.b, self.min_score = k1, b, min_score
        self.docs_tokens = [tokenize(f"{c.doc.title} {c.heading} {c.text}") for c in chunks]
        self.avgdl = sum(map(len, self.docs_tokens)) / max(len(self.docs_tokens), 1)
        df: Counter[str] = Counter()
        for toks in self.docs_tokens:
            df.update(set(toks))
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(toks) for toks in self.docs_tokens]

    @classmethod
    def from_directory(cls, directory: Path) -> BM25Retriever:
        chunks = [c for d in load_documents(directory) for c in chunk_document(d)]
        return cls(chunks)

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedChunk]:
        q = tokenize(query)
        q += [s for t in q for s in SYNONYMS.get(t, [])]
        scored = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs_tokens[i])
            score = 0.0
            for t in set(q):
                if t in tf:
                    f = tf[t]
                    score += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if score >= self.min_score:
                scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        out: list[RetrievedChunk] = []
        seen_docs: Counter[str] = Counter()
        for score, i in scored:
            c = self.chunks[i]
            if seen_docs[c.doc.id] >= 2:  # diversity: at most two chunks per document
                continue
            seen_docs[c.doc.id] += 1
            clean, removed = sanitize_chunk(c.text)
            out.append(RetrievedChunk(
                label=f"D{len(out) + 1}", chunk_id=c.chunk_id, doc_id=c.doc.id, title=c.doc.title, heading=c.heading,
                publisher=c.doc.publisher, published=c.doc.published, source_url=c.doc.source_url, text=clean,
                score=round(score, 3), flagged_lines=removed,
            ))
            if len(out) >= k:
                break
        return out
