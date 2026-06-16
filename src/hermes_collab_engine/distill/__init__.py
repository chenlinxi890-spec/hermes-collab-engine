"""Daily experience distill module.

Independent component that runs once per day (23:59:59) to:
1. Extract today's lessons, failed runs, warnings from the engine DB
2. Have a "leader" (rule-based, no LLM) summarise the day
3. Distribute the summary into:
   - /root/.hermes/memories/MEMORY.md (deduplicated, §-delimited)
   - /root/.hermes/skills/daily-YYYY-MM-DD/SKILL.md (always created)

Trigger via crontab:
  59 23 * * * /root/hermes/venv/bin/python -m hermes_collab_engine.distill.daily_distill \\
    >> /var/log/hermes-distill.log 2>&1

The module is intentionally self-contained: only depends on stdlib.
"""
from __future__ import annotations
