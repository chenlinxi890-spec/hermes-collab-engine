# Daily Distill

Independent component that runs once a day (default 23:59:59) and
extracts today's lessons, failed runs, and high-severity logs from
the engine DB, then writes:

1. A deduplicated entry in `/root/.hermes/memories/MEMORY.md`
2. A daily skill at `/root/.hermes/skills/daily-YYYY-MM-DD/SKILL.md`

The "leader" is rule-based — no LLM, zero-token cron path.

## Architecture

```
hermes_collab_engine/distill/
├── __init__.py
├── _paths.py            # engine DB + memory + skills paths
├── extractor.py         # fetch_today() + summarise()
├── memory_writer.py     # §-delimited Jaccard-deduped MEMORY.md writer
├── skill_writer.py      # daily skill directory + SKILL.md
├── daily_distill.py     # CLI entry point
└── tests/
    └── test_distill.py  # 6 tests
```

## CLI

```bash
# Dry-run (no files written)
python3 -m hermes_collab_engine.distill.daily_distill --dry-run

# Real run
python3 -m hermes_collab_engine.distill.daily_distill

# Override date label (for back-fill)
python3 -m hermes_collab_engine.distill.daily_distill --date 2026-06-15
```

## Cron install (NOT enabled yet — operator must opt in)

Append to user's crontab (`crontab -e`):

```cron
59 23 * * * /root/hermes/venv/bin/python -m hermes_collab_engine.distill.daily_distill \\
    >> /var/log/hermes-distill.log 2>&1
```

Prerequisites:
- `mkdir -p /var/log` (write permission required)
- The venv at `/root/hermes/venv` must have `hermes-collab-engine` installed
  in editable mode (`pip install -e /root/hermes-collab-engine`)

## Deduplication

`memory_writer.append_entry` uses Jaccard token overlap (with CJK
2-char bigram fallback) to decide whether a new entry is a duplicate
of an existing one.  Threshold: 0.6.  Duplicates are NOT re-appended
but are recorded as "duplicate of entry #N" in the result dict.

## Tested

- 6 unit tests pass (memory writer, extractor, skill writer)
- Engine pytest 378/379 pass (1 historical fragile test pre-existing)
- Live run: 248 events captured today, 8 lessons, 16 failed runs
- Idempotent: re-running the same day reports `status: duplicate` for
  memory, overwrites the daily skill (idempotent path is by design)
