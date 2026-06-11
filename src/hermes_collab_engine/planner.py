from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .models import ComplexityScore, WBSNode


class Planner:
    def __init__(self, cwd: Path, model: str | None = None, timeout: int = 120):
        self.cwd = cwd
        self.model = model
        self.timeout = timeout

    def assess(self, request: str) -> ComplexityScore:
        text = request.lower()
        steps = min(10, max(1, len(re.findall(r"[,;；，。\n]| and | then |同时|然后|并且", request)) + 1))
        domain = 7 if any(k in text for k in ["architecture", "framework", "engine", "协同", "架构", "框架"]) else 4
        ambiguity = 7 if any(k in text for k in ["重新梳理", "整个", "自主", "self", "evolution", "复杂"]) else 3
        coupling = 7 if any(k in text for k in ["集成", "dashboard", "sqlite", "worker", "memory", "面板"]) else 3
        risk = 6 if any(k in text for k in ["实现", "数据库", "持久化", "监控", "并行"]) else 3
        overall = round((domain + steps + ambiguity + coupling + risk) / 5)
        if overall <= 3:
            routing = "direct"
        elif overall <= 6:
            routing = "single"
        else:
            routing = "wbs"
        return ComplexityScore(domain, steps, ambiguity, coupling, risk, overall, routing)

    def decompose(self, request: str, max_nodes: int = 8) -> list[WBSNode]:
        prompt = f"""You are designing a WBS for a software collaboration engine implementation.

Repository: {self.cwd}
User request:
{request}

Return ONLY a JSON array of 4-{max_nodes} WBS nodes. Each node must have:
id, title, description, capability, complexity (1-10), dependencies (array of ids), parallelizable (boolean), deliverable.
Design nodes so independent work can run in parallel while write-heavy implementation is sequenced safely.
"""
        try:
            data = self._claude_json(prompt)
            nodes = []
            for i, item in enumerate(data[:max_nodes], 1):
                nodes.append(WBSNode(
                    id=str(item.get("id") or f"wbs-{i}"),
                    title=str(item.get("title") or f"WBS {i}"),
                    description=str(item.get("description") or item.get("title") or ""),
                    capability=str(item.get("capability") or item.get("capabilityRequired") or "implementation"),
                    complexity=int(item.get("complexity") or 5),
                    dependencies=list(item.get("dependencies") or []),
                    parallelizable=bool(item.get("parallelizable", True)),
                    deliverable=str(item.get("deliverable") or "Completed work"),
                ))
            if nodes:
                return nodes
        except Exception:
            pass
        return self.fallback_wbs(request)

    def fallback_wbs(self, request: str) -> list[WBSNode]:
        return [
            WBSNode("wbs-1", "Read design docs", "Read source design documents and extract requirements.", "analysis", 5, [], True, "Requirements summary"),
            WBSNode("wbs-2", "Design core engine", "Define complexity scoring, WBS, queue, worker, watchdog, and aggregation architecture.", "architecture", 7, ["wbs-1"], True, "Engine design"),
            WBSNode("wbs-3", "Implement persistence", "Implement durable SQLite persistence for runs, nodes, workers, logs, lessons, and metrics.", "storage", 6, ["wbs-2"], True, "SQLite store"),
            WBSNode("wbs-4", "Implement worker orchestration", "Implement Claude Code worker launch, concurrency, timeout splitting, retry, checkpoints, and aggregation.", "implementation", 8, ["wbs-2", "wbs-3"], False, "Worker engine"),
            WBSNode("wbs-5", "Implement dashboard", "Implement dashboard and APIs for logs, workers, WBS, retries, checkpoints, and metrics.", "frontend", 6, ["wbs-3"], True, "Dashboard"),
            WBSNode("wbs-6", "Document and verify", "Write README, run smoke tests, and summarize project state.", "docs", 5, ["wbs-4", "wbs-5"], False, "README and verification"),
        ]

    def _claude_json(self, prompt: str):
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if self.model:
            cmd.extend(["--model", self.model])
        proc = subprocess.run(cmd, cwd=self.cwd, text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)
        outer = json.loads(proc.stdout)
        text = outer.get("result", "")
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1)
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            text = match.group(0)
        return json.loads(text)
