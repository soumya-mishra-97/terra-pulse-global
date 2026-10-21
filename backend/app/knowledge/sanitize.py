"""Treat retrieved text as untrusted data.

Defence in depth: (1) only approved documents are indexed, (2) lines that look like
instructions to the model are removed and the chunk is flagged, (3) the prompt wraps every
chunk in <document> tags and tells the model to treat their contents as data only, and
(4) output validation rejects numbers that are not in the deterministic fact set.
"""

from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all|any|the)? ?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all|any|the)? ?(previous|prior|above)",
    r"\byou are now\b",
    r"\bsystem prompt\b",
    r"\bact as\b",
    r"\bnew instructions?\b",
    r"\boverride\b.*\b(figure|number|population|instruction)",
    r"\breveal\b.*\b(key|secret|prompt)",
    r"</?(system|assistant|user|document|instructions?)>",
    r"\bapi[_ ]?key\b",
    r"<script",
]
_RE = re.compile("|".join(INJECTION_PATTERNS), re.I)


def sanitize_chunk(text: str) -> tuple[str, list[str]]:
    """Return (clean_text, removed_lines)."""
    kept, removed = [], []
    for line in text.splitlines():
        if _RE.search(line):
            removed.append(line.strip()[:200])
        else:
            kept.append(line.replace("<", "&lt;").replace(">", "&gt;"))
    return "\n".join(kept).strip(), removed


def looks_like_injection(text: str) -> bool:
    return bool(_RE.search(text or ""))
