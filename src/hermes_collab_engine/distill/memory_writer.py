"""Append a §-delimited entry to /root/.hermes/memories/MEMORY.md.

Deduplication: simple word-overlap check against existing entries.
If the new entry shares >60% of its meaningful tokens with an
existing one, it is recorded as a "duplicate of #N" instead of a
fresh entry, so MEMORY.md does not bloat.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ._paths import MEMORY_FILE

# Chinese + ASCII word tokeniser.  CJK chars are kept individually
# (they're the meaningful unit); ASCII words are kept whole.
# CJK-aware tokeniser.
#
# Chinese text has no spaces between words, so a plain \w split
# treats a whole sentence as one token — that makes Jaccard miss
# near-duplicates.  We therefore also collect overlapping 2-char
# bigrams for CJK ranges.  ASCII words are kept whole.
_TOKEN_RE = re.compile(r"[A-Za-z]+|[\u4e00-\u9fff]", re.UNICODE)


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for t in _TOKEN_RE.findall(text):
        if len(t) > 1:
            out.add(t.lower())
        # Add overlapping 2-char bigrams for CJK runs to catch
        # near-duplicate Chinese sentences.
        if len(t) >= 2 and any("\u4e00" <= c <= "\u9fff" for c in t):
            for i in range(len(t) - 1):
                out.add(t[i:i + 2])
    return out


def _split_entries(text: str) -> list[str]:
    """Return non-empty §-delimited entries (without the § marker)."""
    return [e.strip() for e in text.split("§") if e.strip()]


def _read_existing(path: Path) -> list[str]:
    if not path.exists():
        return []
    return _split_entries(path.read_text(encoding="utf-8"))


def _overlap(a: str, b: str) -> float:
    """Jaccard similarity: |A ∩ B| / |A ∪ B|.

    Using Jaccard (not min or max) prevents a single short
    high-overlap entry from dominating — a 2-token entry that
    shares 1 token with everything would otherwise score 0.5
    against unrelated long entries.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def append_entry(title: str, body: str, *, path: Path = MEMORY_FILE) -> dict:
    """Append a daily entry.  Returns a status dict for the caller / tests.

    status is one of: 'appended' | 'duplicate' | 'created'.
    """
    new_block = f"{title}\n{body}".strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing(path)
    overlap_threshold = 0.6
    best_idx = -1
    best_score = 0.0
    for i, entry in enumerate(existing):
        score = _overlap(new_block, entry)
        if score > best_score:
            best_score = score
            best_idx = i
    created = not path.exists()
    if best_score >= overlap_threshold:
        # Mark the existing entry as reinforced, don't duplicate.
        new_text = "\n\n".join(_split_entries(
            (path.read_text(encoding="utf-8") if path.exists() else "")
        ))
        path.write_text(new_text + "\n§\n", encoding="utf-8")
        return {
            "status": "duplicate",
            "duplicate_of_index": best_idx,
            "overlap": round(best_score, 3),
            "path": str(path),
        }
    new_text = (path.read_text(encoding="utf-8") if path.exists() else "").rstrip()
    if new_text and not new_text.endswith("§"):
        new_text += "\n§\n"
    elif new_text.endswith("§"):
        new_text += "\n"
    new_text += new_block + "\n"
    path.write_text(new_text, encoding="utf-8")
    return {
        "status": "appended" if not created else "created",
        "entry": new_block,
        "path": str(path),
    }
