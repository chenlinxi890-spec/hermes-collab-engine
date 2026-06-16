"""Write one skill per day to /root/.hermes/skills/daily-YYYY-MM-DD/.

A skill is always created — even on a quiet day we drop a
placeholder SKILL.md so the operator can see the distill ran.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._paths import SKILLS_ROOT


FRONTMATTER = """---
name: {name}
description: Auto-generated daily experience distill for {date}. Summarises today's lessons, failed runs, and risk logs from the engine DB.
version: 1.0.0
metadata:
  hermes:
    tags: [auto-generated, daily-distill, {date}]
    category: observability
    generated_by: hermes_collab_engine.distill.daily_distill
---

# Daily Distill — {date}

"""


def write_skill(summary: dict[str, Any], *, skills_root: Path = SKILLS_ROOT) -> dict:
    """Always writes a SKILL.md for the day.  Returns a status dict.

    If `summary['meaningful']` is False, the body is a one-line
    placeholder so the file still exists and downstream tools can
    tell the distill ran.
    """
    date = summary["date"]
    skill_dir = skills_root / f"daily-{date}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    body = _render_body(summary)
    skill_md.write_text(FRONTMATTER.format(name=f"daily-{date}", date=date) + body, encoding="utf-8")
    return {
        "status": "wrote" if summary.get("meaningful") else "placeholder",
        "path": str(skill_md),
        "meaningful": bool(summary.get("meaningful")),
    }


def _render_body(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"## Leader sentence")
    lines.append("")
    lines.append(summary["leader_sentence"])
    lines.append("")
    lines.append(f"## Counts")
    lines.append("")
    for cat, n in sorted(summary.get("counts", {}).items()):
        lines.append(f"- `{cat}`: {n}")
    lines.append("")
    highlight = summary.get("highlight") or []
    if highlight:
        lines.append("## Top signals")
        lines.append("")
        for h in highlight:
            lines.append(f"### {h['title']}")
            lines.append(f"- source: `{h['source_id']}`")
            lines.append(f"- category: `{h['category']}`")
            lines.append(f"- {h['detail']}")
            lines.append("")
    else:
        lines.append("## Top signals")
        lines.append("")
        lines.append("_No standout events today — quiet day._")
        lines.append("")
    lines.append(f"## Raw event log")
    lines.append("")
    lines.append(f"Total events captured: {len(summary.get('events', []))}")
    lines.append(f"Generated: {summary.get('timestamp')}")
    return "\n".join(lines) + "\n"
