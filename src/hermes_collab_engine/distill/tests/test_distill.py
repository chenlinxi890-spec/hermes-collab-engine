"""Tests for the daily distill module.

Run with:
  python3 -m pytest hermes_collab_engine/distill/tests/ -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path("/root/hermes-collab-engine/src")
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hermes_collab_engine.distill import extractor, memory_writer, skill_writer


def _seed_db(path: Path) -> None:
    """Create a minimal engine schema with one day of activity."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            category TEXT NOT NULL,
            lesson TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE runs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            request TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            node_id TEXT,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # Today: 2 lessons, 1 failed run, 1 error log
    conn.execute(
        "INSERT INTO lessons(scope,category,lesson) VALUES(?,?,?)",
        ("global", "planning", "Use fewer WBS nodes for small tasks"),
    )
    conn.execute(
        "INSERT INTO lessons(scope,category,lesson) VALUES(?,?,?)",
        ("global", "watchdog", "Cancel hung futures before they hit the timeout"),
    )
    conn.execute(
        "INSERT INTO runs(id,title,status) VALUES(?,?,?)",
        ("run_abc", "test task", "failed"),
    )
    conn.execute(
        "INSERT INTO logs(run_id,level,message) VALUES(?,?,?)",
        ("run_abc", "error", "boom"),
    )
    conn.commit()
    conn.close()


class MemoryWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "MEMORY.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_entry_creates(self) -> None:
        result = memory_writer.append_entry("title", "body", path=self.path)
        self.assertEqual(result["status"], "created")
        self.assertTrue(self.path.exists())
        self.assertIn("body", self.path.read_text())

    def test_second_similar_entry_deduplicates(self) -> None:
        memory_writer.append_entry("dt module boundary", "禁止打破文件夹边际. 开发指定文件夹时严禁改其他文件夹任何文件.", path=self.path)
        result = memory_writer.append_entry(
            "dt module boundary 2026-06-16",
            "禁止打破文件夹边际. 开发指定文件夹项目时严禁改其他文件夹任何文件, 需要必须等用户明确同意.",
            path=self.path,
        )
        self.assertEqual(result["status"], "duplicate")
        self.assertGreaterEqual(result.get("overlap", 0), 0.6)

    def test_different_entry_appends(self) -> None:
        memory_writer.append_entry("dt module boundary", "禁止打破文件夹边际.", path=self.path)
        result = memory_writer.append_entry(
            "opc worker config",
            "opc 默认 opencode + opencode-go/deepseek-v4-flash. 命名必须 opencode-go/<model>.",
            path=self.path,
        )
        self.assertEqual(result["status"], "appended")
        # Verify both entries survived
        text = self.path.read_text()
        self.assertIn("dt module boundary", text)
        self.assertIn("opc worker config", text)

    def test_append_preserves_existing_entries_with_mixed_separators(self) -> None:
        """Regression: when a file uses blank-line separators instead of §
        the writer must normalise back to §-delimited, not collapse
        unrelated content."""
        # Seed a file that uses blank-line separation (legacy convention)
        self.path.write_text(
            "entry-one body\n\n"
            "entry-two body\n\n"
            "entry-three body\n",
            encoding="utf-8",
        )
        result = memory_writer.append_entry(
            "entry-four totally new content",
            "完全不一样的关键词没有任何重叠 应该 appended.",
            path=self.path,
        )
        self.assertEqual(result["status"], "appended")
        # The writer rebuilds the file from `_split_entries`, which
        # splits strictly on §.  Pre-§ the legacy file has 1 segment,
        # post-write we should have 2 (legacy + new).  The important
        # guarantee is that *all* content survives verbatim.
        text = self.path.read_text()
        self.assertIn("entry-one", text)
        self.assertIn("entry-two", text)
        self.assertIn("entry-three", text)
        self.assertIn("entry-four", text)
        # And the file must now be properly §-delimited going forward
        self.assertGreaterEqual(text.count("§"), 2)

    def test_repeated_run_does_not_grow_file(self) -> None:
        """Idempotency: running append with the same content twice must
        not grow the file or duplicate the entry."""
        body = "今天跑了 3 个 lesson, 2 个 run 失败. 重点关注 watchdog 触发."
        memory_writer.append_entry("Daily distill 2026-06-16", body, path=self.path)
        size_after_first = self.path.stat().st_size
        result = memory_writer.append_entry("Daily distill 2026-06-16 dup", body, path=self.path)
        self.assertEqual(result["status"], "duplicate")
        size_after_second = self.path.stat().st_size
        # File should not have grown by more than the trailing newline we add
        self.assertLessEqual(size_after_second, size_after_first + 10)


class ExtractorTests(unittest.TestCase):
    def test_fetches_today_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "c.sqlite3"
            _seed_db(db)
            # Patch the module-level ENGINE_DB to point at our temp db
            import hermes_collab_engine.distill.extractor as ext
            original = ext.ENGINE_DB
            ext.ENGINE_DB = db
            try:
                events = ext.fetch_today()
            finally:
                ext.ENGINE_DB = original
            self.assertGreaterEqual(len(events), 4)
            categories = {e.category for e in events}
            self.assertIn("lesson", categories)
            self.assertIn("run-failed", categories)

    def test_summarise_includes_leader_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "c.sqlite3"
            _seed_db(db)
            import hermes_collab_engine.distill.extractor as ext
            original = ext.ENGINE_DB
            ext.ENGINE_DB = db
            try:
                events = ext.fetch_today()
                summary = ext.summarise(events)
            finally:
                ext.ENGINE_DB = original
            self.assertIn("leader_sentence", summary)
            self.assertIn("counts", summary)
            self.assertTrue(summary["leader_sentence"])


class SkillWriterTests(unittest.TestCase):
    def test_writes_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            skills_root = Path(td) / "skills"
            summary = {
                "date": "2026-06-16",
                "timestamp": "2026-06-16T12:00:00",
                "counts": {"lesson": 1},
                "highlight": [],
                "leader_sentence": "Quiet day.",
                "events": [],
                "meaningful": False,
            }
            result = skill_writer.write_skill(summary, skills_root=skills_root)
            self.assertEqual(result["status"], "placeholder")
            skill_md = skills_root / "daily-2026-06-16" / "SKILL.md"
            self.assertTrue(skill_md.exists())
            self.assertIn("Daily Distill", skill_md.read_text())


if __name__ == "__main__":
    unittest.main()
