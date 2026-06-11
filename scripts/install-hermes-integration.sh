#!/usr/bin/env bash
set -euo pipefail

ENGINE_DIR="${ENGINE_DIR:-$HOME/hermes-collab-engine}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_DIR="$HERMES_HOME/skills/hermes-claude-collab"
MEMORY_DIR="$HERMES_HOME/memories"
SOUL_FILE="$HERMES_HOME/SOUL.md"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

mkdir -p "$SKILL_DIR" "$MEMORY_DIR" "$BIN_DIR"

ln -sf "$ENGINE_DIR/hermes-collab" "$BIN_DIR/hermes-collab"
ln -sf "$ENGINE_DIR/start.sh" "$BIN_DIR/opc"

cat > "$SKILL_DIR/SKILL.md" <<'SKILL'
---
name: hermes-claude-collab
description: Default capability for substantive tasks: use the local Hermes Collab Engine to plan, split, dispatch Claude Code workers, supervise timeouts, and aggregate results.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [claude-code, orchestration, multi-agent, terminal, coding]
    category: software-development
    requires_toolsets: [terminal]
---

# Hermes Collaboration Engine

## When to Use

Use this skill by default for substantive tasks: implementation, repository analysis, debugging, audits, research, planning, multi-step work, long-running work, or anything that benefits from parallel Claude Code workers. Only skip it for simple chat, tiny questions, or obvious single-step answers.

## Required Behavior

Hermes has a local collaboration engine available at:

```bash
~/hermes-collab-engine/hermes-collab
```

For substantive tasks, call it through the terminal tool with bounded concurrency, timeout supervision, shard splitting, retries, SQLite persistence, and aggregation.

Recommended command:

```bash
~/hermes-collab-engine/hermes-collab run "<task>" --cwd "<working-directory>" --concurrency 4 --timeout 900 --max-retries 2 --split-count 4 --json
```

For large tasks, write the request to a file and use `--request-file`.

If a worker times out, treat it as a decomposition signal. Split, re-dispatch shards, aggregate, and report parent/shard outcomes honestly.
SKILL

cat > "$MEMORY_DIR/COLLAB_ENGINE_CAPABILITY.md" <<'MEMORY'
# Collaboration engine capability

Hermes has a local collaboration engine available at `~/hermes-collab-engine/hermes-collab`.

Default behavior:

- For substantive task requests — implementation, repository analysis, debugging, audits, research, planning, multi-step work, long-running work, or anything that benefits from parallel Claude Code workers — Hermes should use the collaboration engine by default via the terminal tool.
- Only handle directly when the request is simple chat, a very small question, or an obviously single-step answer.
- Use the collaboration engine with checkpointing, timeout supervision, shard splitting, retries, and aggregation.

Recommended command template:

```bash
~/hermes-collab-engine/hermes-collab run "<task>" --cwd "<working-directory>" --concurrency 4 --timeout 900 --max-retries 2 --split-count 4 --json
```
MEMORY

mkdir -p "$HERMES_HOME"
if [ ! -f "$SOUL_FILE" ]; then
  echo "You are Hermes Agent, an intelligent AI assistant." > "$SOUL_FILE"
fi
if ! grep -q "hermes-collab-engine/hermes-collab" "$SOUL_FILE"; then
  cat >> "$SOUL_FILE" <<'SOUL'

You have a local collaboration engine available at `~/hermes-collab-engine/hermes-collab`. For substantive task requests — implementation, repo analysis, debugging, audits, research, planning, multi-step work, long-running tasks, or anything that benefits from parallel Claude Code workers — default to using this collaboration engine through the terminal tool instead of trying to do everything in one Hermes turn. Simple chat, very small questions, or single-step answers can be handled directly.

When using the collaboration engine, supervise the run. Do not treat worker launches as fire-and-forget. Use checkpointing, timeout splitting, retry shards, and aggregation by default. If a Claude Code worker times out, decompose the timed-out work into smaller focused shards, re-dispatch them, and aggregate the successful parent/shard results. Report parent timeouts and shard outcomes honestly.
SOUL
fi

echo "Hermes integration installed."
echo "Skill: $SKILL_DIR/SKILL.md"
echo "Memory: $MEMORY_DIR/COLLAB_ENGINE_CAPABILITY.md"
echo "Command: $BIN_DIR/opc"
