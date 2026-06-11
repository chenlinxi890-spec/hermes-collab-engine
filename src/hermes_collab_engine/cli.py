from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import CollabEngine
from .server import DashboardServer


def main() -> int:
    parser = argparse.ArgumentParser(prog="hermes-collab", description="Standalone Hermes-Claude collaboration engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run a collaboration task")
    run.add_argument("request", nargs="*", help="Task request text")
    run.add_argument("--request-file", help="Read request from file")
    run.add_argument("--title")
    run.add_argument("--cwd", default=".")
    run.add_argument("--db", default="data/collab.sqlite3")
    run.add_argument("--model", help="Use the same model for leader and workers")
    run.add_argument("--leader-model", help="Leader brain model for planning and aggregation")
    run.add_argument("--worker-model", help="Worker brain model for Claude Code workers")
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--timeout", type=int, default=900)
    run.add_argument("--max-retries", type=int, default=2)
    run.add_argument("--split-count", type=int, default=4)
    run.add_argument("--no-aggregate", action="store_true")
    run.add_argument("--json", action="store_true")

    server = sub.add_parser("server", help="Run management dashboard")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--cwd", default=".")
    server.add_argument("--db", default="data/collab.sqlite3")
    server.add_argument("--model", help="Use the same model for leader and workers")
    server.add_argument("--leader-model", help="Leader brain model for planning and aggregation")
    server.add_argument("--worker-model", help="Worker brain model for Claude Code workers")

    status = sub.add_parser("status", help="Show engine status")
    status.add_argument("--db", default="data/collab.sqlite3")
    status.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.cmd == "run":
        request = Path(args.request_file).read_text(encoding="utf-8") if args.request_file else " ".join(args.request)
        engine = CollabEngine(args.db, args.cwd, args.model, leader_model=args.leader_model, worker_model=args.worker_model)
        result = engine.run(
            request,
            title=args.title,
            concurrency=args.concurrency,
            timeout=args.timeout,
            max_retries=args.max_retries,
            split_count=args.split_count,
            aggregate=not args.no_aggregate,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Run: {result['run_id']} ok={result['ok']}")
            if result.get("aggregate"):
                print(result["aggregate"]["result"])
        return 0 if result["ok"] else 1

    if args.cmd == "server":
        DashboardServer(args.host, args.port, args.db, args.cwd, args.model, leader_model=args.leader_model, worker_model=args.worker_model).serve()
        return 0

    if args.cmd == "status":
        from .store import CollabStore
        store = CollabStore(args.db)
        data = {"overview": store.overview(), "runs": store.list_runs(10), "lessons": store.lessons(10)}
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
