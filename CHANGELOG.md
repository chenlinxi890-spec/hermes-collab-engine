# Changelog

All notable public changes to Hermes Collab Engine are documented here.

## v5.6.0 — 2026-06-20

### Resource-driven proactive splitting
- **分片策略重写**：从基于 timeout 剩余时间改为基于任务估算量 + 系统负载 + WBS 最小颗粒度四级决策
- **负载感知 dispatch**：CPU > 85% 或 MEM > 90% 时暂停派发新 worker，等 watchdog 先清理资源
- **ARG_MAX 防护**：prompt 拼装后 900KB 硬截断，防止 subprocess.Popen 因 argv 超长崩溃

### shadcn/ui MCP & ui-design-v2 skill
- 新增 shadcn-ui MCP 服务器（4 工具：list_components, get_component, list_blocks, get_block）
- 新增 ui-design-v2 skill：shadcn/ui v4 高级审美规范（Linear/Stripe/Vercel 风格）
- 更新 skill_distributor.py 映射表，MCP 去重合并重构

### Model connectivity test
- start.py 交互式启动时自动测试 Leader/Worker 模型可达性
- 支持 OpenAI / Anthropic / provider-routed 三种适配格式
- 失败可重试或跳过

### Bug fixes
- ARG_MAX hard truncation in _run_worker (900KB cap)
- Aggregate node: truncate result_struct and request fields
- Ghost running: pending nodes with failed dependencies now properly cleaned up on engine restart

## v5.6.1 — 2026-06-20

### Resource-pressure watchdog improvements
- **SIGKILL → killpg**：Watchdog 杀死 worker 时使用 `os.killpg` 杀整个进程组，消灭幽灵子进程
- **Deferred retry queue**：被 watchdog 杀的节点不立即重试，放入 `_deferred_queue` 等待资源恢复
- **恢复守护**：每 60s 检查 CPU/MEM，资源空闲（<70%）时自动重新 dispatch 被延迟的节点
- **超时保护**：deferred 节点 600s 内无法恢复 → 标记 failed，防止无限等待

### Shard value threshold (MIN_SHARD_WORK=180)
- 最小分片颗粒度从 2min 提升至 **3min**，确保分片收益 > 开销
- 最大片数从 8 降至 **4**，减少并发压力
- 5min 以内任务不拆分

### Ghost running root cause fix
- 预算耗尽分支补 `pending.pop(node.id)`，防止 pending 字典遗留导致死循环
- 父节点在 budget exhausted 时正确 reconcile

### Timezone fix
- SQLite `CURRENT_TIMESTAMP`（UTC）→ `datetime('now','localtime')`（CST）
- store.py `_execute`/`_query`/`_one` 统一替换，新数据全部使用本地时间

### misc
- store.py 新增 `get_run_meta()` + `_migrate_runs_meta_json()`（与 dragon-team 同步）

## v5.0.0 — First formal public release

Hermes Collab Engine v5.0.0 is the first formal public release line for the standalone Hermes collaboration workflow. Earlier v4.5 materials remain useful as internal/pre-release lineage, but v5.0.0 is the baseline intended for public review, installation, sandbox demos, and downstream release notes.

### Added

- WBS-based multi-agent collaboration flow: a Leader scores and decomposes a request, Workers execute dependency-scoped nodes in parallel, and the Leader aggregates results into a final deliverable.
- Real-time dashboard for runs, WBS nodes, Worker state, Skill/Tool injection, active models, logs, and Leader feedback.
- Leader feedback diary in the dashboard with copy/download Markdown actions for aggregate feedback after completion.
- Agent Backend abstraction for Claude Code, Codex, OpenCode, and custom command-backed coding agents.
- Skill registry and Tool profile registry with CLI/API previews for node-specific capability injection.
- SQLite persistence for runs, nodes, workers, logs, lessons, node results, settings, and context snapshots.
- One-line installer that clones or updates the repository, checks dependencies, creates a local virtual environment, and keeps runtime secrets/configuration outside the repository.
- Hermes integration template installer with dry-run review before copying local configuration skeletons.
- Sandbox launcher and sandbox server with mock demo data, TTL cleanup, sub-path deployment support, and optional limited real-worker mode in an isolated database/workspace.
- CLI commands for running tasks, starting the dashboard, inspecting skills/tools/agents/status, managing lessons, intervening in nodes, and running local verification.

### Changed

- Public release framing now treats v5.0.0 as the formal release baseline instead of exposing v4.5 as the primary public version.
- Dashboard run-detail payloads are split between lightweight refresh-friendly responses and full responses for Worker/log/model/Leader-feedback detail.
- Sandbox real execution is explicitly scoped to ignored demo runtime paths and remains separate from production data.

### Security and release boundaries

- The repository does not bundle runtime data, API keys, real Hermes/Claude configuration, tokens, sessions, logs, memories, skills, auth files, or production SQLite files.
- API keys are sourced from local environment/configuration and are not written to the collaboration database.
- Worker execution is constrained by node-specific `allowed_tools` profiles; MCP tooling is read-only by default.
- Sandbox demos default to mock data and an isolated demo database; real-worker sandbox mode writes to `data/sandbox_real.sqlite3` and `data/sandbox_workspace/`.

### Verification

Recommended release checks before publishing artifacts:

```bash
python3 -m py_compile src/hermes_collab_engine/*.py sandbox/server.py scripts/seed_demo_data.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m hermes_collab_engine.cli verify-release
bash -n scripts/install.sh scripts/install-hermes-integration.sh scripts/start_sandbox.sh start.sh
```

### Known limitations

- `verify-v45` remains available as a compatibility alias for the capability set inherited from the v4.5 pre-release line; public release checks should use `verify-release`.
- Package metadata may still be updated by the release-versioning step; confirm `pyproject.toml` and `src/hermes_collab_engine/__init__.py` before building distribution artifacts.
- The sandbox is a demo environment, not a production deployment profile. Keep it on isolated demo data and reviewed mock configuration.
- Real Worker execution requires locally installed/configured agent backends and valid local credentials; the public repository intentionally does not include them.
