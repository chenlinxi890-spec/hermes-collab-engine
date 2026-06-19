import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.hermes_collab_engine.engine import CollabEngine
from src.hermes_collab_engine.models import WBSNode


class MockPopen:
    """Mock for subprocess.Popen — captures cmd, returns canned output."""
    captured = {}

    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        MockPopen.captured["cmd"] = cmd
        self.stdout = None
        self.stderr = None
        self.returncode = 0

    def communicate(self, timeout=None):
        self.stdout = '{"result":"done\\nHERMES-COLLAB-RESULT:{\\\"status\\\":\\\"ok\\\",\\\"summary\\\":\\\"done\\\",\\\"files_modified\\":[],\\\"verification\\":[]}","session_id":"s1","is_error":false}'
        self.stderr = ""
        return (self.stdout, self.stderr)

    def kill(self):
        pass


class WorkerSkillInjectionTest(unittest.TestCase):
    def test_worker_prompt_includes_selected_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CollabEngine(db_path=Path(tmp) / "collab.sqlite3", cwd=tmp)
            node = WBSNode(
                id="wbs-impl",
                title="Implement feature",
                description="Write code changes and run unittest verification.",
                capability="implementation",
                complexity=2,
                dependencies=[],
                parallelizable=True,
                deliverable="Working implementation",
            )

            import json as _json
            node.skills_json = _json.dumps(["implementation-focus", "test-verify"])

            MockPopen.captured = {}

            with patch("subprocess.Popen", MockPopen):
                result = engine._run_worker("run_test", node, timeout=30)

            self.assertTrue(result.ok)
            prompt = MockPopen.captured["cmd"][MockPopen.captured["cmd"].index("-p") + 1]
            self.assertIn("Relevant skills injected by Hermes", prompt)
            self.assertIn("Focused Implementation", prompt)
            self.assertIn("Test & Verification", prompt)
            self.assertIsNotNone(node.skills_json)


if __name__ == "__main__":
    unittest.main()
