#!/usr/bin/env bash
set -euo pipefail

ENGINE_DIR="${ENGINE_DIR:-$HOME/hermes-collab-engine}"
TARGET_DIR="${HERMES_HOME:-$HOME/.hermes}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: scripts/install-hermes-integration.sh [--target-dir DIR] [--bin-dir DIR] [--dry-run]

Creates a conservative Hermes integration skeleton:
  DIR/skills/hermes-claude-collab/SKILL.example.md
  DIR/memories/COLLAB_ENGINE_CAPABILITY.example.md

The files are templates only. No tokens are written and no existing Hermes files are read.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-dir)
      TARGET_DIR="${2:?missing value for --target-dir}"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="${2:?missing value for --bin-dir}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

resolve_path() {
  python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$1"
}

reject_unsafe_path() {
  label="$1"
  value="$2"
  resolved="$(resolve_path "$value")"
  home_resolved="$(resolve_path "$HOME")"
  if [ -z "$value" ] || [ "$resolved" = "/" ] || [ "$resolved" = "$home_resolved" ]; then
    echo "Unsafe ${label}: $value" >&2
    exit 1
  fi
  printf '%s\n' "$resolved"
}

ENGINE_DIR="$(reject_unsafe_path ENGINE_DIR "$ENGINE_DIR")"
TARGET_DIR="$(reject_unsafe_path TARGET_DIR "$TARGET_DIR")"
BIN_DIR="$(reject_unsafe_path BIN_DIR "$BIN_DIR")"

SKILL_DIR="$TARGET_DIR/skills/hermes-claude-collab"
MEMORY_DIR="$TARGET_DIR/memories"
SKILL_FILE="$SKILL_DIR/SKILL.example.md"
MEMORY_FILE="$MEMORY_DIR/COLLAB_ENGINE_CAPABILITY.example.md"

write_file_if_missing() {
  path="$1"
  content="$2"
  if [ -f "$path" ]; then
    echo "保留已有文件: $path"
    return 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "将创建: $path"
    return 0
  fi
  printf '%s\n' "$content" > "$path"
}

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run: no files will be written."
  echo "Target: $TARGET_DIR"
  echo "Bin dir: $BIN_DIR"
else
  mkdir -p "$SKILL_DIR" "$MEMORY_DIR" "$BIN_DIR"
fi

write_file_if_missing "$SKILL_FILE" '---
name: hermes-claude-collab
description: Template skill for connecting Hermes to a local Hermes Collab Engine checkout.
version: 1.0.0
---

# Hermes Collab Engine integration template

Replace this example with your local policy before enabling it as SKILL.md.

Suggested command template:

```bash
~/hermes-collab-engine/hermes-collab run "<task>" --cwd "<working-directory>" --json
```

Security notes:

- Do not paste API keys or tokens into this skill.
- Keep project-specific secrets in your normal secret manager or environment.
- Review tool permissions before enabling automated worker execution.'

write_file_if_missing "$MEMORY_FILE" '# Collaboration engine capability template

This is an empty skeleton memory. Copy it to a real memory file only after reviewing the behavior you want Hermes to remember.

Suggested non-secret fact:

- A local Hermes Collab Engine checkout may be available at `~/hermes-collab-engine`.

Do not store API keys, auth tokens, session data, logs, or private project memory in this template.'

if [ -x "$ENGINE_DIR/hermes-collab" ] && [ "$DRY_RUN" -eq 0 ]; then
  ln -sf "$ENGINE_DIR/hermes-collab" "$BIN_DIR/hermes-collab"
fi
if [ -x "$ENGINE_DIR/start.sh" ] && [ "$DRY_RUN" -eq 0 ]; then
  ln -sf "$ENGINE_DIR/start.sh" "$BIN_DIR/opc"
fi

echo "Hermes integration skeleton ready."
echo "Skill template: $SKILL_FILE"
echo "Memory template: $MEMORY_FILE"
echo ""
echo "To enable, inspect the example files, then copy/rename them without the .example suffix."
echo "No secrets were created or copied."
