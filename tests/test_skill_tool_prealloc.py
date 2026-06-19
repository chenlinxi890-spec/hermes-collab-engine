"""Tests for skill/tool pre-allocation in the leader WBS phase.

Verifies that:
1. Pre-allocation fills node.skills_json and node.tools_json before workers start.
2. Pre-allocated values flow correctly into the SkillDistributor.
3. Backward compatibility: empty skills_json falls back to capability defaults.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.hermes_collab_engine.engine import CollabEngine
from src.hermes_collab_engine.models import WBSNode
from src.hermes_collab_engine.skill_distributor import SkillDistributor
from src.hermes_collab_engine.skills import get_default_registry
from src.hermes_collab_engine.tools import get_default_tool_registry


class TestPreallocateSkillsTools(unittest.TestCase):
    """Test that _preallocate_skills_tools fills node JSON fields."""

    def _make_engine(self):
        tmp = tempfile.mkdtemp()
        return CollabEngine(Path(tmp) / "db.sqlite3", tmp)

    def _make_node(self, node_id="wbs-test", capability="implementation"):
        return WBSNode(
            id=node_id,
            title="Test task",
            description="Do something testable.",
            capability=capability,
            complexity=5,
            dependencies=[],
            parallelizable=True,
            deliverable="Result",
        )

    def test_preallocate_fills_skills_json(self):
        engine = self._make_engine()
        node = self._make_node()
        engine._preallocate_skills_tools("run_test", [node])
        self.assertTrue(node.skills_json)
        names = json.loads(node.skills_json)
        self.assertIn("implementation-focus", names)

    def test_preallocate_fills_tools_json(self):
        engine = self._make_engine()
        node = self._make_node()
        engine._preallocate_skills_tools("run_test", [node])
        self.assertTrue(node.tools_json)
        names = json.loads(node.tools_json)
        self.assertIn("file-edit", names)

    def test_preallocate_respects_capability(self):
        engine = self._make_engine()
        node = self._make_node(capability="scope")
        engine._preallocate_skills_tools("run_test", [node])
        names = json.loads(node.skills_json)
        self.assertIn("search-verify", names)

    def test_preallocate_persists_to_store(self):
        engine = self._make_engine()
        node = self._make_node()
        engine.store.create_run("run_test", "title", "req", {}, agent="claude-code")
        engine.store.insert_wbs_node("run_test", node.to_dict())
        engine._preallocate_skills_tools("run_test", [node])
        stored = engine.store.get_node("run_test", node.id)
        self.assertIsNotNone(stored)
        self.assertTrue(stored["skills_json"])
        self.assertTrue(stored["tools_json"])

    def test_preallocate_leaves_leader_skills_intact(self):
        engine = self._make_engine()
        node = self._make_node()
        node.skills_json = json.dumps(["test-verify"])
        engine._preallocate_skills_tools("run_test", [node])
        names = json.loads(node.skills_json)
        self.assertIn("test-verify", names)  # Leader-assigned value preserved


class TestWorkerUsesSkillDistributor(unittest.TestCase):
    """Test that pre-allocated values flow correctly through SkillDistributor."""

    def test_skill_distributor_reads_preallocated_skills(self):
        sd = SkillDistributor(
            skill_registry=get_default_registry(),
            tool_registry=get_default_tool_registry(),
        )
        skills, tools = sd.resolve_for_node("implementation", ["implementation-focus"], None)
        self.assertEqual(skills, ["implementation-focus"])
        self.assertIn("file-edit", tools)

    def test_skill_distributor_prompt_rendering(self):
        sd = SkillDistributor(
            skill_registry=get_default_registry(),
            tool_registry=get_default_tool_registry(),
        )
        sb, tb, mb = sd.render_for_prompt(
            ["implementation-focus"], ["file-edit", "git-local"], [],
        )
        self.assertIn("Focused Implementation", sb)
        self.assertIn("File Read/Edit", tb)
        self.assertIn("git-local", tb)


class TestFallbackBehavior(unittest.TestCase):
    """When skills_json is empty, SkillDistributor falls back to defaults."""

    def _make_engine(self):
        tmp = tempfile.mkdtemp()
        return CollabEngine(Path(tmp) / "db.sqlite3", tmp)

    def _make_node(self, capability="implementation"):
        return WBSNode(
            id="wbs-test",
            title="Test task",
            description="Do something testable.",
            capability=capability,
            complexity=5,
            dependencies=[],
            parallelizable=True,
            deliverable="Result",
        )

    def test_fallback_scope_uses_search_verify(self):
        engine = self._make_engine()
        node = self._make_node(capability="scope")
        engine._preallocate_skills_tools("run_test", [node])
        names = json.loads(node.skills_json)
        self.assertIn("search-verify", names)

    def test_fallback_verification_uses_test_verify(self):
        engine = self._make_engine()
        node = self._make_node(capability="verification")
        engine._preallocate_skills_tools("run_test", [node])
        names = json.loads(node.skills_json)
        self.assertIn("test-verify", names)

    def test_fallback_with_leader_skills(self):
        """Leader-assigned skills_json takes priority over fallback."""
        engine = self._make_engine()
        node = self._make_node()
        node.skills_json = json.dumps(["risk-checkpoint"])
        engine._preallocate_skills_tools("run_test", [node])
        names = json.loads(node.skills_json)
        self.assertIn("risk-checkpoint", names)


if __name__ == "__main__":
    unittest.main()
