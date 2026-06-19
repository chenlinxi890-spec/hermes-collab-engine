import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.hermes_collab_engine.engine import CollabEngine
from src.hermes_collab_engine.models import ComplexityScore, WBSNode, WorkerResult
from src.hermes_collab_engine.store import CollabStore


class InterruptCleanupTest(unittest.TestCase):
    def test_keyboard_interrupt_marks_running_work_failed(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "collab.sqlite3"
            engine = CollabEngine(db, td)
            nodes = [
                WBSNode("WBS-01", "first", "first task", "general", 1, [], True, "first result"),
                WBSNode("WBS-02", "second", "second task", "general", 1, [], True, "second result"),
            ]
            engine.planner.assess = lambda request: ComplexityScore(1, 1, 1, 1, 1, 1, "wbs")
            engine.planner.decompose = lambda request, **kw: nodes

            def fake_run_worker(run_id, node, timeout, model_override=None):
                worker_id = f"worker_{run_id}_{node.id}_{node.attempt}"
                engine.store.worker_start(worker_id, run_id, node.id)
                engine.store.update_node(node.id, "running")
                if node.id == "WBS-02":
                    raise KeyboardInterrupt()
                engine.store.worker_finish(worker_id, "completed", 0.1, "session-ok", None)
                return WorkerResult(node.id, node.title, True, "ok", "session-ok", 0.1, 0, "", node.attempt)

            engine._run_worker = fake_run_worker

            with self.assertRaises(KeyboardInterrupt):
                engine.run("interrupt me", concurrency=1, aggregate=False)

            store = CollabStore(db)
            overview = store.overview()
            self.assertEqual(overview["running"], 0)
            self.assertEqual(overview["workers_running"], 0)

            runs = store.list_runs()
            self.assertEqual(runs[0]["status"], "failed")
            self.assertIsNotNone(runs[0]["completed_at"])

            detail = store.run_detail(runs[0]["id"])
            node_statuses = {n["id"]: n["status"] for n in detail["nodes"]}
            self.assertEqual(node_statuses["WBS-01"], "completed")
            self.assertEqual(node_statuses["WBS-02"], "failed")
            lessons = store.lessons()
            self.assertEqual(lessons[0]["category"], "interrupt-cleanup")
            self.assertIn("ghost-running", lessons[0]["lesson"])


class FailStaleRunAtomicTest(unittest.TestCase):
    """2026-06-17 stale-cleanup regression: `fail_stale_run` must be
    atomic. If anything raises mid-call, NO writes should be durable
    — not the workers UPDATE, not the wbs_nodes UPDATE, not the
    runs.completed_at, not the log, not the add_lesson. The previous
    implementation called `_execute` 4 times, each of which committed
    independently; a SIGKILL on the parent CLI between the runs.UPDATE
    commit and the wbs_nodes UPDATE commit produced the
    "run=terminal, wbs=stale-running" dashboard bug. The new
    implementation wraps everything in one BEGIN IMMEDIATE / COMMIT
    block, and these tests lock that behaviour in.
    """

    def _seed_run(self, store: CollabStore) -> str:
        """Create a run with two wbs rows (one running, one pending) and
        one worker (running). Used by both happy-path and rollback
        tests. The returned run_id is the one to pass to
        `fail_stale_run`."""
        run_id = "run_test_atomic"
        store.create_run(
            run_id,
            "test",
            "test request",
            {"routing": "single"},
            agent="opencode",
        )
        # create_run leaves the run in `created`; promote to `running`
        # so the rollback test can verify that fail_stale_run doesn't
        # *downgrade* a running run to failed. (The production bug
        # was: `runs.status='failed'` was set durably while the wbs
        # rows stayed in `running`/`pending` — the inverse direction.)
        store.update_run(run_id, "running")
        store._execute(
            "INSERT INTO wbs_nodes(id,run_id,parent_id,title,description,capability,complexity,dependencies_json,parallelizable,deliverable,status,attempt,checkpoint,brief,write_targets_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("wbs-a", run_id, None, "A", "A desc", "implementation", 1, "[]", 1, "A del", "running", 1, 0, "", "[]"),
        )
        store._execute(
            "INSERT INTO wbs_nodes(id,run_id,parent_id,title,description,capability,complexity,dependencies_json,parallelizable,deliverable,status,attempt,checkpoint,brief,write_targets_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("wbs-b", run_id, None, "B", "B desc", "implementation", 1, "[]", 1, "B del", "pending", 1, 0, "", "[]"),
        )
        store.worker_start(f"worker_{run_id}_wbs-a_1", run_id, "wbs-a")
        return run_id

    def test_happy_path_marks_all_running_pending_failed_atomically(self):
        """All 5 writes (workers, wbs, runs, log, lesson) must commit
        in one transaction. Verified by counting log/lesson rows and
        checking that runs.completed_at is set together with the
        wbs status changes (no torn state on read)."""
        with tempfile.TemporaryDirectory() as td:
            store = CollabStore(Path(td) / "db.sqlite3")
            run_id = self._seed_run(store)

            # Sanity: before fail_stale_run, the rows are not in the
            # terminal state.
            before_wbs = {n["id"]: n["status"] for n in store.get_nodes(run_id)}
            self.assertEqual(before_wbs, {"wbs-a": "running", "wbs-b": "pending"})

            store.fail_stale_run(run_id, "interrupted: test")

            # All in-flight work failed
            after_wbs = {n["id"]: n["status"] for n in store.get_nodes(run_id)}
            self.assertEqual(after_wbs, {"wbs-a": "failed", "wbs-b": "failed"})

            # Worker row also failed
            worker = store._one("SELECT status, error FROM workers WHERE run_id=?", (run_id,))
            self.assertEqual(worker["status"], "failed")
            self.assertIn("interrupted: test", worker["error"])

            # Run row terminal
            run = store._one("SELECT status, completed_at FROM runs WHERE id=?", (run_id,))
            self.assertEqual(run["status"], "failed")
            self.assertIsNotNone(run["completed_at"])

            # Log + lesson recorded (both inside the same transaction)
            logs = store.recent_logs(limit=50)
            self.assertTrue(
                any("stale running work marked failed" in (l["message"] or "") for l in logs),
                f"expected cleanup log; got: {[l['message'] for l in logs]}",
            )
            lessons = store.lessons()
            self.assertTrue(
                any(l["category"] == "interrupt-cleanup" for l in lessons),
                f"expected interrupt-cleanup lesson; got: {[l['category'] for l in lessons]}",
            )

    def test_rollback_on_mid_transaction_failure_leaves_state_intact(self):
        """If anything raises inside the transaction, the entire
        fail_stale_run must roll back. Verified by creating a
        trigger on the `wbs_nodes` table that raises
        OperationalError when the `fail_stale_run` UPDATE fires.
        The post-condition: workers row is still `running`, wbs
        rows are still `running`/`pending`, run row is still
        `running` (not terminal), and no `interrupt-cleanup`
        log/lesson was written. The previous implementation would
        have left workers='failed' and runs.status='failed'
        (durable) while the wbs rows were stale (the exact
        operator bug from 2026-06-17).

        The trigger approach was chosen over monkey-patching
        `Connection.execute` because the sqlite3 module makes
        `execute` a read-only attribute on the C-level Connection
        object (verified by `AttributeError: attribute 'execute'
        of type 'sqlite3.Connection' is read-only` when patched
        directly). A SQL trigger is the only deterministic,
        non-invasive way to make the *third* statement inside
        `fail_stale_run` raise without touching production code.
        """
        with tempfile.TemporaryDirectory() as td:
            store = CollabStore(Path(td) / "db.sqlite3")
            run_id = self._seed_run(store)

            # Install a trigger that aborts the wbs UPDATE on
            # the second statement inside fail_stale_run. SQLite
            # triggers fire on data-modification statements
            # (INSERT/UPDATE/DELETE) and raise RAISE() which
            # propagates as sqlite3.IntegrityError / OperationalError
            # at the next statement boundary. This is the
            # cleanest "mid-transaction injection" available
            # without changing production code.
            store._execute("""
                CREATE TRIGGER wbs_update_abort
                BEFORE UPDATE OF status ON wbs_nodes
                FOR EACH ROW
                WHEN OLD.status IN ('running', 'pending') AND NEW.status = 'failed'
                BEGIN
                    SELECT RAISE(ABORT, 'simulated mid-transaction failure');
                END
            """)

            with self.assertRaises(sqlite3.DatabaseError):
                store.fail_stale_run(run_id, "interrupted: should-rollback")

            # CRITICAL: nothing should be durable. Pre-fix, the
            # first `_execute` (workers UPDATE) would have committed
            # before the wbs UPDATE was reached. Post-fix, the
            # ROLLBACK unwinds it.
            after_wbs = {n["id"]: n["status"] for n in store.get_nodes(run_id)}
            self.assertEqual(
                after_wbs,
                {"wbs-a": "running", "wbs-b": "pending"},
                f"wbs rows should be unchanged after rollback; got {after_wbs}",
            )
            worker = store._one("SELECT status FROM workers WHERE run_id=?", (run_id,))
            self.assertEqual(
                worker["status"],
                "running",
                "worker row should be unchanged after rollback",
            )
            run = store._one("SELECT status, completed_at FROM runs WHERE id=?", (run_id,))
            self.assertEqual(
                run["status"],
                "running",
                f"run row should not be marked failed after rollback; got status={run['status']!r}",
            )
            self.assertIsNone(
                run["completed_at"],
                f"runs.completed_at should be NULL after rollback; got {run['completed_at']!r}",
            )

            # No interrupt-cleanup log row (the INSERT was inside
            # the rolled-back transaction).
            logs = store.recent_logs(limit=50)
            self.assertFalse(
                any("stale running work marked failed" in (l["message"] or "") for l in logs),
                f"no interrupt-cleanup log should be durable after rollback; got: {[l['message'] for l in logs]}",
            )
            # No interrupt-cleanup lesson row either.
            lessons = store.lessons()
            self.assertFalse(
                any(l["category"] == "interrupt-cleanup" for l in lessons),
                f"no interrupt-cleanup lesson should be durable after rollback; got: {[l['category'] for l in lessons]}",
            )

    def test_synchronous_full_pragmas_set_at_init(self):
        """The `synchronous=FULL` PRAGMA must be set when CollabStore
        opens the DB. The fail_stale_run fix depends on every commit
        fsyncing durably; without this PRAGMA, a SIGKILL between
        commit and OS-flushed write would re-introduce the original
        ghost-running bug."""
        with tempfile.TemporaryDirectory() as td:
            store = CollabStore(Path(td) / "db.sqlite3")
            mode = store._one("PRAGMA synchronous")
            self.assertEqual(
                int(mode["synchronous"]),
                2,  # FULL == 2 (OFF=0, NORMAL=1, FULL=2, EXTRA=3)
                f"PRAGMA synchronous should be FULL (2); got {mode['synchronous']!r}",
            )


if __name__ == "__main__":
    unittest.main()
