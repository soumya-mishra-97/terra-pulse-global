"""Output validation: every number in LLM-generated text must be traceable to supplied evidence.

A number passes if, at the precision it is written with, it matches a deterministic fact value,
a number that appears in the supplied documents or in the user's question, a year covered by the
evidence, or a small counting integer (0-10). Anything else is reported as unsupported.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

CITATION = re.compile(r"\[(?:[FDS]\d+(?:\s*,\s*)?)+\]")
NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-+−])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<scale>billion|bn|million|mn|thousand|percent|per cent|%))?",
    re.I,
)
SCALES = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "thousand": 1e3}
REALTIME_CLAIM = re.compile(r"\b(real[- ]time|live)\b[^.]*\bcount", re.I)
NEGATION = re.compile(r"\b(not|no|never|cannot|can't|isn't|doesn't|without)\b", re.I)


@dataclass
class NumericCheck:
    passed: bool
    unsupported: list[str] = field(default_factory=list)
    checked: int = 0
    issues: list[str] = field(default_factory=list)


def _decimals(num: str) -> int:
    return len(num.split(".")[1]) if "." in num else 0


def extract_numbers(text: str) -> list[tuple[str, float, float, bool, bool]]:
    """Return (raw, value, tolerance, is_percent, has_scale) for each number in the text."""
    out = []
    for m in NUMBER.finditer(CITATION.sub(" ", text)):
        raw_num = m.group("num")
        scale_word = (m.group("scale") or "").lower()
        base = float(raw_num.replace(",", ""))
        is_pct = scale_word in ("%", "percent", "per cent")
        mult = SCALES.get(scale_word, 1.0)
        value = base * mult
        if m.group("sign") in ("-", "−"):
            value = -value
        # Half a unit in the last written digit, scaled: "1.5 billion" may stand for 1.45-1.55 billion.
        tol = 0.5 * 10 ** (-_decimals(raw_num)) * mult
        out.append((m.group(0).strip(), value, tol, is_pct, bool(mult != 1.0)))
    return out


def _numbers_in(texts: Iterable[str]) -> set[float]:
    vals: set[float] = set()
    for t in texts:
        for _, v, _, _, _ in extract_numbers(t or ""):
            vals.add(abs(v))
    return vals


def check_numbers(text: str, fact_values: Iterable[float], allowed_years: Iterable[int],
                  context_texts: Iterable[str] = ()) -> NumericCheck:
    facts = [abs(v) for v in fact_values if v is not None]
    years = set(allowed_years)
    context = _numbers_in(context_texts)
    result = NumericCheck(passed=True)
    for raw, value, tol, is_pct, has_scale in extract_numbers(text):
        result.checked += 1
        v = abs(value)
        if not is_pct and not has_scale and float(v).is_integer():
            iv = int(v)
            if 1900 <= iv <= 2100:
                if iv in years:
                    continue
                result.unsupported.append(raw)
                continue
            if iv <= 10:
                continue
        if any(abs(v - c) <= max(tol, 1e-9) for c in context):
            continue
        # Allow a tiny relative slack on top of written precision for float noise.
        if any(abs(v - f) <= tol + abs(f) * 1e-6 for f in facts):
            continue
        result.unsupported.append(raw)
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if REALTIME_CLAIM.search(sentence) and not NEGATION.search(sentence):
            result.issues.append("claims a real-time/live count of people")
    result.passed = not result.unsupported and not result.issues
    return result


def check_citations(text: str, valid_labels: set[str]) -> list[str]:
    """Return citation labels used in the text that do not exist in the evidence."""
    used = set(re.findall(r"\b([FDS]\d+)\b", " ".join(CITATION.findall(text))))
    return sorted(used - valid_labels)
