# Hermes Collab Engine

> 官方 Hermes Agent + Claude Code Worker 的独立协同引擎。支持复杂度判断、WBS 拆解、并行分发、超时拆分重试、SQLite 持久化、自学习经验和中文管理面板。

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](#requirements)
[![SQLite](https://img.shields.io/badge/Persistence-SQLite-green)](#why-sqlite)
[![Hermes](https://img.shields.io/badge/Hermes-Agent-purple)](#verified-runtime-chain)
[![Claude Code](https://img.shields.io/badge/Workers-Claude%20Code-orange)](#verified-runtime-chain)

## 一键部署

```bash
curl -fsSL https://raw.githubusercontent.com/lpc0387/hermes-collab-engine/main/scripts/install.sh | bash
```

安装后启动：

```bash
opc
```

`opc` 会读取 `/root/.claude/settings.json` 和 `/root/.claude/profiles/*.json`，让你选择：

1. API 配置来源
2. Leader Agent（Hermes 命令行 / 规划与聚合大脑）模型
3. Worker Agent（Claude Code 执行器大脑）模型
4. 面板监听地址和端口
5. 默认工作目录

然后自动启动协同引擎管理面板，并进入官方 Hermes 命令行。

## 项目定位

Standalone collaboration engine for coordinating Claude Code workers under official Hermes Agent supervision.

This project is intentionally separate from `im-bridge`. The design documents in `/root/im-bridge/docs/hermes-framework` were used as reference material only; this project does not install dependencies into `im-bridge` and does not modify its source code.

## Verified Runtime Chain

The actual working chain is:

```text
Official NousResearch Hermes Agent (/root/hermes)
  ↓ terminal tool
Hermes Collab Engine (/root/hermes-collab-engine)
  ↓ Python orchestration + SQLite state
Claude Code CLI workers (`claude -p ... --output-format json`)
  ↓
Optional aggregation worker
  ↓
Hermes returns the final result
```

Verified commands:

```bash
# Official Hermes repository/version
git -C /root/hermes remote -v
hermes --version

# Official Hermes terminal tool
hermes -z "Use terminal to run: echo OFFICIAL_HERMES_TERMINAL_OK. Reply only with the command output." --provider anthropic --model kimi-k2.6

# Claude Code CLI
claude -p "Reply exactly: CLAUDE_CODE_REAL_OK" --output-format json

# Collab engine calling Claude Code
cd /root/hermes-collab-engine
./hermes-collab run "Reply exactly: COLLAB_ENGINE_CALLS_CLAUDE_OK" --timeout 120 --json

# Full chain: Hermes → collab engine → Claude Code
hermes -z "Use terminal to run: /root/hermes-collab-engine/hermes-collab run 'Reply exactly: HERMES_TO_COLLAB_TO_CLAUDE_OK' --timeout 120 --json. Reply only with the JSON output." --provider anthropic --model kimi-k2.6
```

## What It Does

Hermes Collab Engine provides a practical WBS-based collaboration runtime:

- Autonomously assesses task complexity.
- Routes simple tasks directly and complex tasks through WBS decomposition.
- Builds WBS nodes with dependencies, capability tags, complexity, parallelizability, and deliverables.
- Dispatches dependency-ready WBS nodes in parallel with a configurable concurrency limit.
- Launches real Claude Code workers via `claude -p`.
- Supervises workers with watchdog timeouts.
- Splits timed-out tasks into smaller retry shards instead of treating timeout as final failure.
- Aggregates parent and shard results honestly.
- Persists runs, WBS nodes, workers, logs, metrics, and lessons in SQLite.
- Learns from slow or failed runs and writes lessons for future planning.
- Exposes a web dashboard with logs, run state, worker status, lessons, metrics, and SSE live updates.

## Design Inputs

Reference documents read from `im-bridge`:

```text
/root/im-bridge/docs/hermes-framework/01-overview.md
/root/im-bridge/docs/hermes-framework/02-hermes-core.md
/root/im-bridge/docs/hermes-framework/03-worker-pool.md
/root/im-bridge/docs/hermes-framework/04-persistence.md
/root/im-bridge/docs/hermes-framework/05-self-evolution.md
/root/im-bridge/docs/hermes-framework/06-integration.md
/root/im-bridge/docs/hermes-framework/07-roadmap.md
```

The implemented project follows those themes while remaining standalone.

## Why SQLite

Persistence uses Python's standard `sqlite3` module backed by a real SQLite database file. This avoids native Node build issues and keeps the engine portable without `npm install`.

Default database:

```text
/root/hermes-collab-engine/data/collab.sqlite3
```

SQLite tables:

| Table | Purpose |
|---|---|
| `runs` | Top-level collaboration run, request, complexity decision, lifecycle status |
| `wbs_nodes` | WBS DAG nodes, parent/child shards, dependency JSON, results, errors |
| `workers` | Claude Code worker lifecycle, session IDs, duration, status, error |
| `logs` | Structured run/node logs for dashboard and audit |
| `lessons` | Self-learning memory from timeouts and slow workers |
| `metrics` | Extensible key/value metrics |

SQLite writes are protected by a thread lock because workers run concurrently.

## Project Layout

```text
hermes-collab-engine/
├── hermes-collab                         # CLI wrapper
├── README.md                             # This document
├── data/
│   └── collab.sqlite3                    # SQLite database
├── examples/
│   └── im-bridge-request.md              # Example high-level request
├── src/
│   ├── __init__.py
│   └── hermes_collab_engine/
│       ├── __init__.py
│       ├── cli.py                        # CLI entrypoint: run/server/status
│       ├── engine.py                     # WBS scheduling, workers, watchdog, aggregation, learning
│       ├── models.py                     # ComplexityScore, WBSNode, WorkerResult dataclasses
│       ├── planner.py                    # Complexity scoring and WBS decomposition
│       ├── server.py                     # HTTP dashboard + JSON API + SSE
│       └── store.py                      # SQLite schema and persistence API
└── web/
    └── index.html                        # Single-file management dashboard
```

## Requirements

- Python 3.11+
- Claude Code CLI available as `claude`
- Official Hermes Agent available as `hermes` if you want Hermes to operate the engine

No Node or npm dependency is required for this project.

## Interactive Startup Script

Use the startup script when you want to choose the brain models at launch time:

```bash
cd /root/hermes-collab-engine
./start.sh
```

The script reads API configuration from:

```text
/root/.claude/settings.json
/root/.claude/profiles/*.json
```

It then asks you to choose:

1. API profile / BaseURL / API key source
2. Leader Agent model — the Hermes-side planning and aggregation brain
3. Worker Agent model — the Claude Code execution brain
4. Dashboard listen host
5. Dashboard listen port
6. Default working directory

It writes the chosen runtime configuration to:

```text
/root/hermes-collab-engine/.runtime-config.json
```

Example interactive choices:

```text
选择 API 配置来源
  1. 当前 Claude Code 配置 | <从本机 Claude 配置读取的 BaseURL> | 模型数 9
  2. mimo | <从本机 profile 读取的 BaseURL> | 模型数 3
  3. volcengine | <从本机 profile 读取的 BaseURL> | 模型数 9

选择 Leader Agent（Hermes/规划与聚合大脑）模型
  1. kimi-k2.6
  2. glm-5.1
  ...

选择 Worker Agent（Claude Code 执行器大脑）模型
  1. kimi-k2.6
  2. glm-5.1
  ...
```

The startup script exports the selected API key, BaseURL, leader model, and worker model into the launched server process.

## CLI Usage

### Run a simple task

```bash
cd /root/hermes-collab-engine
./hermes-collab run "Reply exactly: COLLAB_ENGINE_OK" --timeout 120 --json
```

### Run the reference high-level task

```bash
cd /root/hermes-collab-engine
./hermes-collab run \
  --request-file examples/im-bridge-request.md \
  --cwd /root/im-bridge \
  --concurrency 4 \
  --timeout 900 \
  --max-retries 2 \
  --split-count 4 \
  --json
```

### Check status

```bash
cd /root/hermes-collab-engine
./hermes-collab status --json
```

### Start dashboard

```bash
cd /root/hermes-collab-engine
./hermes-collab server --host 0.0.0.0 --port 8765 --cwd /root
```

Open:

```text
http://localhost:8765
```

## Official Hermes Usage

From official Hermes, call the engine through the terminal tool:

```bash
hermes -z "Use terminal to run: /root/hermes-collab-engine/hermes-collab run 'Reply exactly: HERMES_TO_COLLAB_TO_CLAUDE_OK' --timeout 120 --json. Reply only with the JSON output." --provider anthropic --model kimi-k2.6
```

For a real task:

```bash
hermes -z "Use terminal to run: /root/hermes-collab-engine/hermes-collab run --request-file /root/hermes-collab-engine/examples/im-bridge-request.md --cwd /root/im-bridge --concurrency 4 --timeout 900 --max-retries 2 --split-count 4 --json. Summarize the run status and aggregate result." --provider anthropic --model kimi-k2.6
```

## How Complexity Routing Works

`Planner.assess()` scores the request across:

- `domain`
- `steps`
- `ambiguity`
- `coupling`
- `risk`

It calculates `overall` and chooses routing:

```text
overall <= 3      direct
overall <= 6      single / moderate path
overall > 6       WBS decomposition
```

For WBS tasks, `Planner.decompose()` asks Claude Code to produce a JSON WBS. If that fails, it falls back to a deterministic WBS template.

## WBS Node Model

Each WBS node has:

```text
id
title
description
capability
complexity
dependencies
parallelizable
deliverable
status
parent_id
attempt
```

The engine only runs dependency-ready nodes. Independent nodes run concurrently.

## Watchdog, Retry, and Sharding

Timeouts are treated as decomposition signals, not final failure.

Default run policy:

```text
--timeout 900
--max-retries 2
--split-count 4
```

If a worker times out, its WBS node is split into focused shards:

| Shard | Focus |
|---|---|
| `scope` | smallest relevant scope and entrypoints |
| `evidence` | exact file paths, commands, symbols, short evidence |
| `implementation` | minimal implementation or patch strategy |
| `risks` | blockers, unknowns, verification needs |

Shard nodes are inserted into SQLite as child WBS nodes and executed as workers.

## Self-Learning / Evolution

The engine writes lessons into SQLite:

- timeout lessons — split similar work earlier next time
- slow-success lessons — reduce WBS scope for similar tasks

Current learning storage:

```text
lessons(category, lesson, evidence_json, created_at)
```

This is intentionally simple and inspectable. Future versions can feed these lessons back into `Planner.assess()` and `Planner.decompose()`.

## Dashboard

The dashboard is a single-file HTML app served by the Python server.

It shows:

- run counts
- running count
- worker-running count
- lessons count
- run table
- recent logs
- lessons
- live SSE heartbeat
- task submission form

### Dashboard API

| Endpoint | Purpose |
|---|---|
| `GET /api/overview` | counts and high-level metrics |
| `GET /api/runs` | recent runs |
| `GET /api/runs/:id` | run detail, WBS nodes, workers, logs |
| `GET /api/logs` | recent structured logs |
| `GET /api/lessons` | learned lessons |
| `GET /api/events` | SSE live updates |
| `POST /api/runs` | async run submission |

## Verification Results

### Official Hermes is real

```text
Hermes Agent v0.16.0 (2026.6.5) · upstream ee1a744a
Project: /root/hermes
```

### Hermes terminal tool works

```text
OFFICIAL_HERMES_TERMINAL_OK
```

### Claude Code CLI works

```text
CLAUDE_CODE_REAL_OK
```

### Collab engine calls Claude Code

```json
{
  "ok": true,
  "results": [
    {
      "result": "COLLAB_ENGINE_CALLS_CLAUDE_OK",
      "session_id": "d8e67dc7-26f4-4f7f-b759-9aa1fde084df"
    }
  ]
}
```

### Full chain works

Official Hermes → terminal → collab engine → Claude Code returned:

```text
HERMES_TO_COLLAB_TO_CLAUDE_OK
```

### Dashboard API works

```bash
curl -s http://127.0.0.1:8765/api/overview
```

Example response:

```json
{
  "runs": 4,
  "running": 0,
  "completed": 2,
  "failed": 2,
  "workers_running": 0,
  "lessons": 0
}
```

## Important Boundaries

- This project is standalone.
- It does not install packages into `im-bridge`.
- It does not replace official Hermes Agent.
- It uses official Hermes as an operator surface and Claude Code as workers.
- It uses real SQLite via Python's `sqlite3` module.
- It reports parent timeouts and shard outcomes separately.
