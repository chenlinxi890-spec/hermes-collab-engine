#!/usr/bin/env python3
"""Seed sanitized sandbox demo data for the Hermes dashboard."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,title TEXT NOT NULL,request TEXT NOT NULL,status TEXT NOT NULL,complexity_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT);
CREATE TABLE IF NOT EXISTS wbs_nodes (id TEXT PRIMARY KEY,run_id TEXT NOT NULL,parent_id TEXT,title TEXT NOT NULL,description TEXT NOT NULL,capability TEXT NOT NULL,complexity INTEGER NOT NULL,dependencies_json TEXT NOT NULL DEFAULT '[]',parallelizable INTEGER NOT NULL DEFAULT 1,deliverable TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 1,checkpoint INTEGER NOT NULL DEFAULT 0,result TEXT,session_id TEXT,duration_seconds REAL,error TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,brief TEXT DEFAULT '',shared_brief TEXT DEFAULT '',estimated_duration INTEGER DEFAULT NULL,result_struct_json TEXT DEFAULT NULL,skills_json TEXT DEFAULT NULL,tools_json TEXT DEFAULT NULL,FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY,run_id TEXT NOT NULL,node_id TEXT,status TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,duration_seconds REAL,session_id TEXT,error TEXT);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,node_id TEXT,level TEXT NOT NULL,message TEXT NOT NULL,data_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY AUTOINCREMENT,scope TEXT NOT NULL DEFAULT 'global',category TEXT NOT NULL,lesson TEXT NOT NULL,evidence_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS metrics (key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS node_results (node_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,result_text TEXT DEFAULT '',result_struct_json TEXT DEFAULT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS run_state (run_id TEXT PRIMARY KEY,paused INTEGER DEFAULT 0,checkpoint_paused_nodes_json TEXT DEFAULT '[]',updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS context_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,snapshot_type TEXT NOT NULL,node_id TEXT DEFAULT NULL,snapshot_json TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""

RUNS = [
    {
        "id": "demo_run_active",
        "title": "Demo: clone product dashboard into sandbox",
        "request": "复制现有页面到沙盒环境，使用脱敏数据与 Mock 服务演示核心链路。",
        "status": "running",
        "complexity": {"domain": 7, "steps": 6, "ambiguity": 3, "coupling": 7, "risk": 5, "overall": 6, "routing": "wbs"},
        "created_at": "2026-06-12 09:00:00",
        "updated_at": "2026-06-12 09:18:00",
        "completed_at": None,
        "agent": "claude-code",
    },
    {
        "id": "demo_run_success",
        "title": "Demo: v5.0 capability preview verified",
        "request": "验证 Skill/Tool 预览、Worker 池、运行日志和历史记录展示。",
        "status": "completed",
        "complexity": {"domain": 5, "steps": 4, "ambiguity": 2, "coupling": 5, "risk": 3, "overall": 4, "routing": "single"},
        "created_at": "2026-06-11 16:20:00",
        "updated_at": "2026-06-11 16:38:00",
        "completed_at": "2026-06-11 16:38:00",
        "agent": "claude-code",
    },
    {
        "id": "demo_run_failed",
        "title": "Demo: blocked production dependency",
        "request": "尝试调用生产通知网关；沙盒应阻断并提示使用 Mock。",
        "status": "failed",
        "complexity": {"domain": 4, "steps": 3, "ambiguity": 2, "coupling": 6, "risk": 8, "overall": 5, "routing": "single"},
        "created_at": "2026-06-10 10:00:00",
        "updated_at": "2026-06-10 10:07:00",
        "completed_at": "2026-06-10 10:07:00",
        "agent": "mock-agent",
    },
]

NODES = [
    {
        "id": "demo_active_wbs_1",
        "run_id": "demo_run_active",
        "parent_id": None,
        "title": "Analyze production page dependencies",
        "description": "识别页面依赖的数据接口、外部服务和演示风险点。",
        "capability": "analysis",
        "complexity": 5,
        "dependencies": [],
        "parallelizable": True,
        "deliverable": "依赖清单与隔离建议",
        "status": "completed",
        "attempt": 1,
        "checkpoint": 0,
        "result": "发现页面需要 overview/runs/logs/lessons/agents/skills/tools/events 数据；生产通知网关必须替换为 mock-notify。",
        "session_id": "demo-session-analysis",
        "duration_seconds": 21.4,
        "error": None,
        "brief": "只读分析，不触达生产环境。",
        "shared_brief": "Sandbox demo uses only sanitized records and localhost mocks.",
        "estimated_duration": 300,
        "skills": ["search-verify"],
        "tools": ["file-edit", "git-local"],
    },
    {
        "id": "demo_active_wbs_2",
        "run_id": "demo_run_active",
        "parent_id": None,
        "title": "Prepare sanitized seed dataset",
        "description": "生成足以覆盖总览指标、Worker、历史记录、日志、经验面板的演示数据。",
        "capability": "implementation",
        "complexity": 6,
        "dependencies": ["demo_active_wbs_1"],
        "parallelizable": False,
        "deliverable": "可重复加载的 SQLite 种子数据",
        "status": "running",
        "attempt": 1,
        "checkpoint": 0,
        "result": "正在写入脱敏运行、节点、Worker 和日志样本。",
        "session_id": "demo-session-seed",
        "duration_seconds": 42.0,
        "error": None,
        "brief": "不得写入 API Key、真实用户、真实生产 URL。",
        "shared_brief": "Sandbox demo uses only sanitized records and localhost mocks.",
        "estimated_duration": 480,
        "skills": ["implementation-focus", "test-verify"],
        "tools": ["file-edit", "python-tests"],
    },
    {
        "id": "demo_active_wbs_3",
        "run_id": "demo_run_active",
        "parent_id": None,
        "title": "Wire sandbox mock endpoints",
        "description": "配置不可访问生产依赖的 mock/stub 行为。",
        "capability": "implementation",
        "complexity": 5,
        "dependencies": ["demo_active_wbs_1"],
        "parallelizable": True,
        "deliverable": "Mock 服务配置",
        "status": "pending",
        "attempt": 1,
        "checkpoint": 0,
        "result": None,
        "session_id": None,
        "duration_seconds": None,
        "error": None,
        "brief": "替代通知、鉴权和 worker agent 发现，不连接公网生产服务。",
        "shared_brief": "Sandbox demo uses only sanitized records and localhost mocks.",
        "estimated_duration": 360,
        "skills": ["implementation-focus"],
        "tools": ["file-edit"],
    },
    {
        "id": "demo_success_wbs_1",
        "run_id": "demo_run_success",
        "parent_id": None,
        "title": "Verify dashboard API payloads",
        "description": "验证 dashboard 所需 API 返回稳定结构。",
        "capability": "verification",
        "complexity": 4,
        "dependencies": [],
        "parallelizable": True,
        "deliverable": "验证结果",
        "status": "completed",
        "attempt": 1,
        "checkpoint": 0,
        "result": "Skill/Tool payload and dashboard references verified.",
        "session_id": "demo-session-verify",
        "duration_seconds": 15.2,
        "error": None,
        "brief": "本地验证，不启动真实 worker。",
        "shared_brief": "",
        "estimated_duration": 180,
        "skills": ["test-verify"],
        "tools": ["python-tests"],
    },
    {
        "id": "demo_failed_wbs_1",
        "run_id": "demo_run_failed",
        "parent_id": None,
        "title": "Call production notification gateway",
        "description": "沙盒禁止调用生产通知网关。",
        "capability": "implementation",
        "complexity": 7,
        "dependencies": [],
        "parallelizable": False,
        "deliverable": "应被阻断的外部调用",
        "status": "failed",
        "attempt": 1,
        "checkpoint": 1,
        "result": "Blocked by sandbox egress policy; use mock-notify instead.",
        "session_id": None,
        "duration_seconds": 4.8,
        "error": "sandbox blocked outbound production dependency",
        "brief": "演示隔离策略。",
        "shared_brief": "",
        "estimated_duration": 120,
        "skills": ["risk-checkpoint"],
        "tools": ["git-local"],
    },
]

WORKERS = [
    ("demo_worker_analysis", "demo_run_active", "demo_active_wbs_1", "completed", "2026-06-12 09:02:00", "2026-06-12 09:04:00", 21.4, "demo-session-analysis", None),
    ("demo_worker_seed", "demo_run_active", "demo_active_wbs_2", "running", "2026-06-12 09:12:00", "2026-06-12 09:18:00", None, "demo-session-seed", None),
    ("demo_worker_verify", "demo_run_success", "demo_success_wbs_1", "completed", "2026-06-11 16:21:00", "2026-06-11 16:38:00", 15.2, "demo-session-verify", None),
    ("demo_worker_blocked", "demo_run_failed", "demo_failed_wbs_1", "failed", "2026-06-10 10:02:00", "2026-06-10 10:07:00", 4.8, None, "sandbox blocked outbound production dependency"),
]

LOGS = [
    ("demo_run_active", "demo_active_wbs_1", "info", "worker started", {"node": "demo_active_wbs_1", "title": "Analyze production page dependencies", "agent": "claude-code"}, "2026-06-12 09:02:00"),
    ("demo_run_active", "demo_active_wbs_1", "info", "worker finished", {"ok": True, "duration_seconds": 21.4}, "2026-06-12 09:04:00"),
    ("demo_run_active", "demo_active_wbs_2", "info", "worker skills selected", {"skills": ["implementation-focus", "test-verify"]}, "2026-06-12 09:12:00"),
    ("demo_run_active", "demo_active_wbs_2", "info", "worker tool profiles selected", {"profiles": ["file-edit", "python-tests"]}, "2026-06-12 09:12:02"),
    ("demo_run_active", "demo_active_wbs_2", "info", "seed data write in progress", {"records": "sanitized"}, "2026-06-12 09:18:00"),
    ("demo_run_success", "demo_success_wbs_1", "info", "dashboard API payloads verified", {"skills": 3, "tools": 3}, "2026-06-11 16:38:00"),
    ("demo_run_failed", "demo_failed_wbs_1", "warning", "production dependency blocked", {"dependency": "notify-gateway", "replacement": "mock-notify"}, "2026-06-10 10:07:00"),
]

LESSONS = [
    ("project", "sandbox", "Sandbox demos must use sanitized records and localhost-only mock dependencies.", {"source": "demo-seed"}, "2026-06-12 09:00:00"),
    ("global", "worker-contract", "Successful worker output should end with HERMES-COLLAB-RESULT JSON for downstream summaries.", {"source": "demo-seed"}, "2026-06-11 16:38:00"),
    ("project", "egress", "Production notification and auth gateways are replaced by deterministic mocks in sandbox mode.", {"source": "demo-seed"}, "2026-06-10 10:07:00"),
]

SETTINGS = {
    "sandbox_mode": True,
    "sandbox_seed": "demo-v1",
    "mock_services": {
        "auth": "static-demo-token",
        "notify": "mock-notify",
        "agent_registry": "local-fixture",
    },
    "risk_policy": {"low": "continue", "medium": "checkpoint", "high": "checkpoint", "checkpoint_timeout": 300},
}


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ensure_agent_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "agent" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN agent TEXT DEFAULT 'claude-code'")


def seed(db_path: Path, reset: bool) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _ensure_agent_column(conn)
        if reset:
            for table in ("context_snapshots", "run_state", "node_results", "settings", "metrics", "lessons", "logs", "workers", "wbs_nodes", "runs"):
                conn.execute(f"DELETE FROM {table}")

        for run in RUNS:
            conn.execute(
                """INSERT OR REPLACE INTO runs(id,title,request,status,complexity_json,created_at,updated_at,completed_at,agent)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (run["id"], run["title"], run["request"], run["status"], _dumps(run["complexity"]), run["created_at"], run["updated_at"], run["completed_at"], run["agent"]),
            )

        for node in NODES:
            conn.execute(
                """INSERT OR REPLACE INTO wbs_nodes(id,run_id,parent_id,title,description,capability,complexity,dependencies_json,parallelizable,deliverable,status,attempt,checkpoint,result,session_id,duration_seconds,error,brief,shared_brief,estimated_duration,skills_json,tools_json,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (
                    node["id"], node["run_id"], node["parent_id"], node["title"], node["description"], node["capability"], node["complexity"], _dumps(node["dependencies"]),
                    1 if node["parallelizable"] else 0, node["deliverable"], node["status"], node["attempt"], node["checkpoint"], node["result"], node["session_id"], node["duration_seconds"],
                    node["error"], node["brief"], node["shared_brief"], node["estimated_duration"], _dumps(node["skills"]), _dumps(node["tools"]),
                ),
            )
            if node["result"]:
                result_struct = {"status": "ok" if node["status"] == "completed" else node["status"], "summary": node["result"], "verification": ["seeded fixture"]}
                conn.execute(
                    "INSERT OR REPLACE INTO node_results(node_id,run_id,result_text,result_struct_json) VALUES(?,?,?,?)",
                    (node["id"], node["run_id"], node["result"], _dumps(result_struct)),
                )

        conn.executemany(
            "INSERT OR REPLACE INTO workers(id,run_id,node_id,status,started_at,updated_at,duration_seconds,session_id,error) VALUES(?,?,?,?,?,?,?,?,?)",
            WORKERS,
        )
        for run_id, node_id, level, message, data, created_at in LOGS:
            conn.execute(
                "INSERT INTO logs(run_id,node_id,level,message,data_json,created_at) VALUES(?,?,?,?,?,?)",
                (run_id, node_id, level, message, _dumps(data), created_at),
            )
        for scope, category, lesson, evidence, created_at in LESSONS:
            conn.execute(
                "INSERT INTO lessons(scope,category,lesson,evidence_json,created_at) VALUES(?,?,?,?,?)",
                (scope, category, lesson, _dumps(evidence), created_at),
            )
        for key, value in SETTINGS.items():
            conn.execute("INSERT OR REPLACE INTO settings(key,value_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)", (key, _dumps(value)))

        snapshot = {
            "plan_summary": "Sandbox demo uses only sanitized records and localhost mocks.",
            "nodes": {node["id"]: {"status": node["status"], "key_facts": node["result"] or "pending"} for node in NODES if node["run_id"] == "demo_run_active"},
            "decisions": ["Use mock-notify instead of production notification gateway."],
            "risk_assessments": [{"level": "medium", "reason": "external dependencies are stubbed"}],
            "user_instructions": ["Keep page code isolated from production data."],
            "pending_actions": ["demo_active_wbs_3"],
        }
        conn.execute(
            "INSERT INTO context_snapshots(run_id,snapshot_type,node_id,snapshot_json,created_at) VALUES(?,?,?,?,?)",
            ("demo_run_active", "checkpoint", "demo_active_wbs_2", _dumps(snapshot), "2026-06-12 09:18:00"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO run_state(run_id,paused,checkpoint_paused_nodes_json,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
            ("demo_run_active", 0, _dumps([])),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed sanitized Hermes sandbox demo data")
    parser.add_argument("--db", default="data/demo_sandbox.sqlite3", help="SQLite database path to create or update")
    parser.add_argument("--reset", action="store_true", help="Clear existing rows in Hermes tables before seeding")
    args = parser.parse_args()

    seed(Path(args.db), args.reset)
    print(_dumps({"ok": True, "db": args.db, "runs": len(RUNS), "nodes": len(NODES), "workers": len(WORKERS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
