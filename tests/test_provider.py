"""Tests for ProviderProfile — construction, serialisation, model resolution,
env var mapping, and model_prefix handling."""
from __future__ import annotations

import os
import unittest

from src.hermes_collab_engine.provider import (
    ProviderProfile,
    env_targets_for_protocol,
    apply_provider_to_env,
    resolve_model,
    build_model_flag_value,
)


class ProviderProfileConstructionTests(unittest.TestCase):
    def test_minimal_construction(self):
        p = ProviderProfile(
            name="test",
            protocol="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            default_model="claude-4",
        )
        self.assertEqual(p.name, "test")
        self.assertEqual(p.protocol, "anthropic")
        self.assertEqual(p.base_url, "https://api.anthropic.com")
        self.assertEqual(p.api_key, "sk-test")
        self.assertEqual(p.default_model, "claude-4")
        self.assertIsNone(p.allowed_models)
        self.assertEqual(p.model_prefix, "")
        self.assertEqual(p.path_mode, "append")
        self.assertEqual(p.headers_extra, {})
        self.assertEqual(p.env_aliases, {})

    def test_full_construction(self):
        p = ProviderProfile(
            name="deepseek-relay",
            protocol="openai",
            base_url="https://api.deepseek.com",
            api_key="sk-ds",
            default_model="deepseek-chat",
            allowed_models=["deepseek-chat", "deepseek-reasoner"],
            model_prefix="opencode-go/",
            path_mode="full",
            headers_extra={"X-Custom": "value"},
            env_aliases={"api_key": "DEEPSEEK_KEY"},
        )
        self.assertEqual(p.name, "deepseek-relay")
        self.assertEqual(p.allowed_models, ["deepseek-chat", "deepseek-reasoner"])
        self.assertEqual(p.model_prefix, "opencode-go/")
        self.assertEqual(p.path_mode, "full")
        self.assertEqual(p.headers_extra, {"X-Custom": "value"})
        self.assertEqual(p.env_aliases, {"api_key": "DEEPSEEK_KEY"})


class ProviderProfileSerializationTests(unittest.TestCase):
    def test_to_dict(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        d = p.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["protocol"], "anthropic")
        self.assertEqual(d["api_key"], "sk-test")
        self.assertIn("allowed_models", d)
        self.assertIn("model_prefix", d)

    def test_from_dict(self):
        d = {
            "name": "test",
            "protocol": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key": "sk-test",
            "default_model": "claude-4",
            "model_prefix": "opencode-go/",
        }
        p = ProviderProfile.from_dict(d)
        self.assertEqual(p.name, "test")
        self.assertEqual(p.model_prefix, "opencode-go/")
        self.assertIsNone(p.allowed_models)

    def test_from_dict_ignores_unknown_fields(self):
        d = {
            "name": "test",
            "protocol": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key": "sk-test",
            "default_model": "claude-4",
            "unknown_field": "should be ignored",
        }
        p = ProviderProfile.from_dict(d)
        self.assertEqual(p.name, "test")
        self.assertFalse(hasattr(p, "unknown_field"))

    def test_from_dict_roundtrip(self):
        p1 = ProviderProfile(
            name="roundtrip", protocol="openai",
            base_url="https://api.openai.com", api_key="sk-ot",
            default_model="gpt-4o",
            allowed_models=["gpt-4o", "gpt-4-turbo"],
            model_prefix="prefix/",
            path_mode="full",
            headers_extra={"X-Api": "test"},
        )
        d = p1.to_dict()
        p2 = ProviderProfile.from_dict(d)
        for field in ("name", "protocol", "base_url", "api_key", "default_model",
                      "model_prefix", "path_mode"):
            self.assertEqual(getattr(p1, field), getattr(p2, field))
        self.assertEqual(p1.allowed_models, p2.allowed_models)
        self.assertEqual(p1.headers_extra, p2.headers_extra)


class ModelResolutionTests(unittest.TestCase):
    def setUp(self):
        self._saved = {}
        for var in ("HERMES_COLLAB_MODEL", "ANTHROPIC_MODEL"):
            self._saved[var] = os.environ.pop(var, None)

    def tearDown(self):
        for var, val in self._saved.items():
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)

    def test_cli_model_wins(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        result = resolve_model(cli_model="gpt-5", provider=p)
        self.assertEqual(result, "gpt-5")

    def test_provider_default_model(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        result = resolve_model(cli_model=None, provider=p)
        self.assertEqual(result, "claude-4")

    def test_fallback_to_env_var(self):
        os.environ["HERMES_COLLAB_MODEL"] = "env-model"
        result = resolve_model(cli_model=None, provider=None)
        self.assertEqual(result, "env-model")

    def test_no_provider_returns_cli_model(self):
        result = resolve_model(cli_model="manual-model", provider=None)
        self.assertEqual(result, "manual-model")

    def test_no_provider_no_cli_returns_none_when_unset(self):
        result = resolve_model(cli_model=None, provider=None)
        self.assertIsNone(result)


class BuildModelFlagValueTests(unittest.TestCase):
    def test_no_prefix(self):
        result = build_model_flag_value("claude-4", None)
        self.assertEqual(result, "claude-4")

    def test_with_prefix(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4", model_prefix="opencode-go/",
        )
        result = build_model_flag_value("claude-4", p)
        self.assertEqual(result, "opencode-go/claude-4")

    def test_no_double_prefix(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4", model_prefix="opencode-go/",
        )
        result = build_model_flag_value("opencode-go/claude-4", p)
        self.assertEqual(result, "opencode-go/claude-4")

    def test_empty_prefix(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4", model_prefix="",
        )
        result = build_model_flag_value("claude-4", p)
        self.assertEqual(result, "claude-4")

    def test_provider_without_prefix(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        result = build_model_flag_value("claude-4", p)
        self.assertEqual(result, "claude-4")


class EnvTargetsForProtocolTests(unittest.TestCase):
    def test_anthropic_targets(self):
        targets = env_targets_for_protocol("anthropic")
        self.assertIn("base_url", targets)
        self.assertIn("api_key", targets)
        self.assertIn("model", targets)
        self.assertIn("ANTHROPIC_BASE_URL", targets["base_url"])
        self.assertIn("ANTHROPIC_API_KEY", targets["api_key"])
        self.assertIn("ANTHROPIC_MODEL", targets["model"])

    def test_openai_targets(self):
        targets = env_targets_for_protocol("openai")
        self.assertIn("base_url", targets)
        self.assertIn("api_key", targets)
        self.assertIn("model", targets)
        self.assertIn("OPENAI_BASE_URL", targets["base_url"])
        self.assertIn("OPENAI_API_KEY", targets["api_key"])
        self.assertIn("OPENAI_MODEL", targets["model"])

    def test_gemini_targets(self):
        targets = env_targets_for_protocol("gemini")
        self.assertNotIn("base_url", targets)
        self.assertIn("api_key", targets)
        self.assertIn("model", targets)
        self.assertIn("GOOGLE_API_KEY", targets["api_key"])
        self.assertIn("GOOGLE_MODEL", targets["model"])

    def test_custom_returns_empty(self):
        targets = env_targets_for_protocol("custom")
        self.assertEqual(targets, {})

    def test_unknown_protocol_returns_empty(self):
        targets = env_targets_for_protocol("nonexistent")
        self.assertEqual(targets, {})


class ApplyProviderToEnvTests(unittest.TestCase):
    def test_anthropic_sets_env_vars(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        env = {}
        apply_provider_to_env(env, p)
        self.assertEqual(env.get("ANTHROPIC_BASE_URL"), "https://api.anthropic.com")
        self.assertEqual(env.get("ANTHROPIC_API_KEY"), "sk-test")
        self.assertEqual(env.get("ANTHROPIC_MODEL"), "claude-4")

    def test_openai_sets_env_vars(self):
        p = ProviderProfile(
            name="test", protocol="openai",
            base_url="https://api.openai.com", api_key="sk-ot",
            default_model="gpt-4o",
        )
        env = {}
        apply_provider_to_env(env, p)
        self.assertEqual(env.get("OPENAI_BASE_URL"), "https://api.openai.com")
        self.assertEqual(env.get("OPENAI_API_KEY"), "sk-ot")
        self.assertEqual(env.get("OPENAI_MODEL"), "gpt-4o")

    def test_gemini_sets_env_vars(self):
        p = ProviderProfile(
            name="test", protocol="gemini",
            base_url="", api_key="gk-test",
            default_model="gemini-2.0",
        )
        env = {}
        apply_provider_to_env(env, p)
        self.assertNotIn("GOOGLE_BASE_URL", env)
        self.assertEqual(env.get("GOOGLE_API_KEY"), "gk-test")
        self.assertEqual(env.get("GOOGLE_MODEL"), "gemini-2.0")

    def test_custom_uses_env_aliases(self):
        p = ProviderProfile(
            name="custom", protocol="custom",
            base_url="https://custom.api", api_key="ck-test",
            default_model="custom-model",
            env_aliases={"api_key": "CUSTOM_KEY"},
        )
        env = {}
        apply_provider_to_env(env, p)
        self.assertEqual(env.get("CUSTOM_KEY"), "ck-test")

    def test_model_override_takes_precedence(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        env = {}
        apply_provider_to_env(env, p, model_override="claude-opus-5")
        self.assertEqual(env.get("ANTHROPIC_MODEL"), "claude-opus-5")

    def test_none_provider_noop(self):
        env = {"EXISTING": "value"}
        apply_provider_to_env(env, None)
        self.assertEqual(env, {"EXISTING": "value"})

    def test_preserves_existing_env(self):
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        env = {"EXISTING": "keep"}
        apply_provider_to_env(env, p)
        self.assertEqual(env.get("EXISTING"), "keep")
        self.assertEqual(env.get("ANTHROPIC_BASE_URL"), "https://api.anthropic.com")


class AgentBackendProviderIntegrationTests(unittest.TestCase):
    """Test that AgentBackend.build_command uses provider for model_prefix."""

    def test_build_command_with_provider_model_prefix(self):
        from src.hermes_collab_engine.agents import get_backend
        p = ProviderProfile(
            name="opencode-test", protocol="custom",
            base_url="https://custom.api", api_key="ck-test",
            default_model="custom-model",
            model_prefix="opencode-go/",
        )
        backend = get_backend("opencode")
        # Pass provider explicitly
        cmd = backend.build_command(prompt="test", model="deepseek-chat", provider=p)
        # opencode does not support --model flag (supports_model_flag=False)
        # so model_prefix should NOT appear
        self.assertNotIn("--model", cmd)
        self.assertNotIn("opencode-go/deepseek-chat", cmd)

    def test_build_command_claude_with_provider_prefix(self):
        from src.hermes_collab_engine.agents import get_backend
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
            model_prefix="opencode-go/",
        )
        backend = get_backend("claude-code")
        cmd = backend.build_command(prompt="hello", model="claude-4", provider=p)
        self.assertIn("--model", cmd)
        # claude-code supports model flag so prefix should be applied
        model_idx = cmd.index("--model") + 1
        self.assertEqual(cmd[model_idx], "opencode-go/claude-4")

    def test_build_command_claude_without_provider_prefix(self):
        from src.hermes_collab_engine.agents import get_backend
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
            model_prefix="",
        )
        backend = get_backend("claude-code")
        cmd = backend.build_command(prompt="hello", model="claude-4", provider=p)
        model_idx = cmd.index("--model") + 1
        self.assertEqual(cmd[model_idx], "claude-4")

    def test_build_command_claude_without_explicit_provider(self):
        """When provider is not passed, build_command should fall back to
        backend's own provider field (which is None by default)."""
        from src.hermes_collab_engine.agents import get_backend
        backend = get_backend("claude-code")
        cmd = backend.build_command(prompt="hello", model="claude-4")
        model_idx = cmd.index("--model") + 1
        self.assertEqual(cmd[model_idx], "claude-4")


class EngineProviderIntegrationTests(unittest.TestCase):
    """Test that CollabEngine stores and uses provider correctly."""

    def setUp(self):
        # Save conflicting env vars that the test runner may have set
        self._saved = {}
        for var in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL",
                     "HERMES_COLLAB_WORKER_BASE_URL", "HERMES_COLLAB_WORKER_API_KEY",
                     "HERMES_COLLAB_WORKER_MODEL"):
            self._saved[var] = os.environ.pop(var, None)

    def tearDown(self):
        for var, val in self._saved.items():
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)

    def test_engine_stores_provider(self):
        import tempfile
        from pathlib import Path
        from src.hermes_collab_engine.engine import CollabEngine
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-test",
            default_model="claude-4",
        )
        with tempfile.TemporaryDirectory() as tmp:
            engine = CollabEngine(Path(tmp) / "db.sqlite3", tmp, provider=p)
            self.assertIsNotNone(engine.provider)
            self.assertEqual(engine.provider.name, "test")

    def test_engine_provider_used_in_env_for_role(self):
        import tempfile
        from pathlib import Path
        from src.hermes_collab_engine.engine import CollabEngine
        p = ProviderProfile(
            name="test", protocol="anthropic",
            base_url="https://api.custom.com", api_key="sk-custom",
            default_model="claude-4",
        )
        with tempfile.TemporaryDirectory() as tmp:
            engine = CollabEngine(Path(tmp) / "db.sqlite3", tmp, provider=p)
            engine.worker_model = "claude-4"
            env = engine._env_for_role("worker")
            self.assertEqual(env.get("ANTHROPIC_BASE_URL"), "https://api.custom.com")
            self.assertEqual(env.get("ANTHROPIC_API_KEY"), "sk-custom")

    def test_engine_provider_openai_env_vars(self):
        import tempfile
        from pathlib import Path
        from src.hermes_collab_engine.engine import CollabEngine
        p = ProviderProfile(
            name="openai-test", protocol="openai",
            base_url="https://api.openai.com", api_key="sk-ot",
            default_model="gpt-4o",
        )
        with tempfile.TemporaryDirectory() as tmp:
            engine = CollabEngine(Path(tmp) / "db.sqlite3", tmp, provider=p)
            engine.worker_model = "gpt-4o"
            env = engine._env_for_role("worker")
            self.assertEqual(env.get("OPENAI_BASE_URL"), "https://api.openai.com")
            self.assertEqual(env.get("OPENAI_API_KEY"), "sk-ot")
            self.assertEqual(env.get("OPENAI_MODEL"), "gpt-4o")

    def test_engine_provider_none_preserves_original_behavior(self):
        import tempfile
        from pathlib import Path
        from src.hermes_collab_engine.engine import CollabEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = CollabEngine(Path(tmp) / "db.sqlite3", tmp)
            env = engine._env_for_role("worker")
            # With no provider, ANTHROPIC env vars come from the actual environment
            # The key is that it doesn't crash and returns a dict
            self.assertIsInstance(env, dict)
            # Should contain basic env vars
            self.assertIn("PATH", env)


if __name__ == "__main__":
    unittest.main()
