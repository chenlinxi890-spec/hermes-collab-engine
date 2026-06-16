"""Extract today's events from the engine DB.

The engine's lessons table is the primary signal; we also pull
failed runs, top-level risk logs, and high-impact warnings so the
distill step has something to summarise even on quiet days.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ._paths import ENGINE_DB


@dataclass
class DayEvent:
    """One discrete thing that happened today."""
    category: str           # 'lesson' | 'run-failed' | 'run-completed' | 'risk-log' | 'warning-log'
    title: str              # short, human-readable
    detail: str             # longer body
    source_id: str          # DB row id (lesson id, run id, log id) for traceability
    raw: dict[str, Any] = field(default_factory=dict)


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"engine DB not found at {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_today(db_path: Path = ENGINE_DB) -> list[DayEvent]:
    """Return every event that landed in the engine DB on the local date.

    Uses SQLite's ``date(..., 'localtime')`` modifier so the boundary
    matches the operator's wall clock, not UTC.
    """
    events: list[DayEvent] = []
    conn = _connect(db_path)
    try:
        # 1. lessons — the primary source of truth for lessons-learned
        rows = conn.execute(
            """
            SELECT id, scope, category, lesson, evidence_json, created_at
            FROM lessons
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
            ORDER BY id
            """
        ).fetchall()
        for r in rows:
            evidence = _safe_json(r["evidence_json"])
            events.append(
                DayEvent(
                    category="lesson",
                    title=f"[{r['category']}] {r['scope']}",
                    detail=str(r["lesson"]),
                    source_id=f"lesson:{r['id']}",
                    raw={"id": r["id"], "evidence": evidence, "created_at": r["created_at"]},
                )
            )

        # 2. failed runs (and notable completed runs) — for context
        rows = conn.execute(
            """
            SELECT id, title, status, request, created_at, updated_at, completed_at
            FROM runs
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
            ORDER BY created_at
            """
        ).fetchall()
        for r in rows:
            cat = "run-failed" if r["status"] == "failed" else "run-completed"
            events.append(
                DayEvent(
                    category=cat,
                    title=f"run {r['id']}",
                    detail=str(r["title"] or r["request"] or "").strip()[:240],
                    source_id=f"run:{r['id']}",
                    raw={
                        "id": r["id"],
                        "status": r["status"],
                        "created_at": r["created_at"],
                    },
                )
            )

        # 3. high-severity logs — risk / error / warning
        # Note: cap the result set so a runaway log table (we have
        # seen 3M+ rows accumulated in WAL mode) cannot stall the
        # daily cron.  We take the most recent 200 matching rows;
        # the rule-based summary only needs a handful anyway.
        rows = conn.execute(
            """
            SELECT id, run_id, node_id, level, message, data_json, created_at
            FROM logs
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
              AND level IN ('error', 'risk', 'warning')
            ORDER BY id DESC
            LIMIT 200
            """
        ).fetchall()
        rows = list(reversed(rows))  # restore chronological order for downstream
        for r in rows:
            data = _safe_json(r["data_json"])
            events.append(
                DayEvent(
                    category="risk-log" if r["level"] == "risk" else f"{r['level']}-log",
                    title=f"{r['level']} log #{r['id']}" + (f" from {r['run_id']}" if r["run_id"] else ""),
                    detail=str(r["message"])[:240],
                    source_id=f"log:{r['id']}",
                    raw={"id": r["id"], "data": data, "created_at": r["created_at"]},
                )
            )
    finally:
        conn.close()
    return events


def _safe_json(s: str | None) -> Any:
    if not s:
        return {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": str(s)[:200]}


def summarise(events: Iterable[DayEvent]) -> dict[str, Any]:
    """Rule-based leader summary.  No LLM; keeps the cron path zero-token.

    Returns a dict shaped so both memory_writer and skill_writer can
    consume it without re-parsing the raw event list.
    """
    by_cat: dict[str, list[DayEvent]] = {}
    for e in events:
        by_cat.setdefault(e.category, []).append(e)

    counts = {k: len(v) for k, v in by_cat.items()}
    lessons = by_cat.get("lesson", [])
    failed_runs = by_cat.get("run-failed", [])

    # Pick top 3 most "lesson-y" things to surface in the memory entry.
    # Priority: lessons > risk-log > run-failed > warning-log.
    priority = ["lesson", "risk-log", "run-failed", "warning-log", "run-completed", "error-log"]
    highlight: list[DayEvent] = []
    for cat in priority:
        highlight.extend(by_cat.get(cat, []))
        if len(highlight) >= 3:
            break
    highlight = highlight[:3]

    # Build a 1-2 sentence "leader sentence" — flat template, no LLM.
    parts: list[str] = []
    if counts.get("lesson", 0):
        parts.append(f"{counts['lesson']} lesson(s) captured")
    if counts.get("run-failed", 0):
        parts.append(f"{counts['run-failed']} run(s) failed")
    if counts.get("run-completed", 0):
        parts.append(f"{counts['run-completed']} run(s) completed")
    if counts.get("risk-log", 0):
        parts.append(f"{counts['risk-log']} risk log(s)")
    if counts.get("error-log", 0):
        parts.append(f"{counts['error-log']} error log(s)")
    if counts.get("warning-log", 0):
        parts.append(f"{counts['warning-log']} warning log(s)")
    if not parts:
        leader_sentence = "Quiet day — no lessons, failures, or notable logs."
    else:
        leader_sentence = "Today: " + ", ".join(parts) + "."

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "highlight": [e.__dict__ for e in highlight],
        "leader_sentence": leader_sentence,
        "events": [e.__dict__ for e in events],
        "meaningful": bool(lessons or failed_runs or by_cat.get("risk-log")),
    }
