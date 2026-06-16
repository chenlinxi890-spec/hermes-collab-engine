"""Agent Backend Registry — ACP-compliant multi-agent support.

Each ``AgentBackend`` describes how to invoke and parse output from a
specific coding agent CLI (Claude Code, Codex, OpenCode, Hermes, ...).

The engine's ``_run_worker`` consults the selected backend to build
subprocess commands and parse results, rather than hardcoding
claude-specific logic.

The concrete built-in backends live in ``hermes_collab_engine.adapters.*``
(one module per agent CLI) and are auto-registered on import of this
module — adding a new built-in means appending a new adapter module and
adding its import here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Any

if __name__ != "__main__":
    # Avoid circular import at module level; provider is imported on demand
    from .provider import ProviderProfile as _ProviderProfile
else:
    _ProviderProfile = None  # type: ignore[assignment,misc]


@dataclass
class AgentBackend:
    """Pluggable agent backend definition."""

    name: str                          # e.g. "claude-code", "codex", "opencode"
    display_name: str                  # e.g. "Claude Code"
    command: list[str]                 # base command, e.g. ["claude"]
    prompt_flag: str                   # flag to pass prompt, e.g. "-p"
    output_format_flags: list[str]     # e.g. ["--output-format", "json"]
    supports_model_flag: bool          # whether --model flag works
    model_flag: str                    # e.g. "--model"
    permission_flags: list[str] | None # e.g. ["--permission-mode", "acceptEdits"]
    allowed_tools_flag: str | None     # e.g. "--allowedTools"
    output_parser: str                 # "claude_json" | "raw_text" | "codex_json"
    process_pattern: str               # regex for kill-node, e.g. "claude.*--output-format"
    prompt_prefix: str                 # text prepended to prompt
    prompt_suffix: str                 # text appended to prompt
    default_allowed_tools: list[str]   # tools allowed by default
    capabilities: list[str] = field(default_factory=list)  # e.g. ["file-edit","git-ops","test-run"]
    enabled: bool = True
    provider: Any = None  # Optional ProviderProfile instance (imported lazily to avoid cycle)

    def build_command(
        self,
        prompt: str,
        model: str | None = None,
        allowed_tools: list[str] | None = None,
        provider: Any = None,
    ) -> list[str]:
        """Build the full command to invoke this agent.

        If *provider* carries a ``model_prefix`` (e.g. ``"opencode-go/"``),
        it is prepended to the model value when building the ``--model`` flag.
        Falls back to ``self.provider`` if *provider* is not passed.
        """
        cmd = list(self.command)
        # If prompt_flag is empty, treat the prompt as a positional arg (e.g. `opencode run "prompt"`)
        if self.prompt_flag:
            cmd.append(self.prompt_flag)
        cmd.append(prompt)
        cmd.extend(self.output_format_flags)
        if self.permission_flags:
            cmd.extend(self.permission_flags)
        if self.allowed_tools_flag and (allowed_tools or self.default_allowed_tools):
            tools = allowed_tools or self.default_allowed_tools
            cmd.extend([self.allowed_tools_flag, ",".join(tools)])
        if model and self.supports_model_flag:
            effective_provider = provider or self.provider
            if effective_provider is not None:
                # Late import to avoid circular dependency
                from .provider import build_model_flag_value
                model_arg = build_model_flag_value(model, effective_provider)
            else:
                model_arg = model
            cmd.extend([self.model_flag, model_arg])
        return cmd

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        node_id: str,
        node_title: str,
        duration: float,
        attempt: int,
    ) -> dict[str, Any]:
        """Parse agent output into WorkerResult-compatible dict.

        Returns dict with keys: ok, result, session_id, returncode, stderr, result_struct
        """
        parser = getattr(self, f"_parse_{self.output_parser}", None)
        if parser is None:
            return self._parse_raw_text(stdout, stderr, returncode, node_id, node_title, duration, attempt)
        return parser(stdout, stderr, returncode, node_id, node_title, duration, attempt)

    def _parse_claude_json(
        self, stdout: str, stderr: str, returncode: int,
        node_id: str, node_title: str, duration: float, attempt: int,
    ) -> dict[str, Any]:
        """Parse Claude Code JSON output format."""
        text = stdout.strip()
        session_id = None
        ok = returncode == 0
        try:
            parsed = json.loads(text)
            text = str(parsed.get("result", text))
            session_id = parsed.get("session_id")
            ok = ok and not bool(parsed.get("is_error"))
        except Exception:
            pass
        return {
            "ok": ok,
            "result": text,
            "session_id": session_id,
            "returncode": returncode,
            "stderr": stderr,
            "result_struct": None,
        }

    def _parse_raw_text(
        self, stdout: str, stderr: str, returncode: int,
        node_id: str, node_title: str, duration: float, attempt: int,
    ) -> dict[str, Any]:
        """Parse raw text output (no JSON envelope)."""
        return {
            "ok": returncode == 0,
            "result": stdout.strip(),
            "session_id": None,
            "returncode": returncode,
            "stderr": stderr,
            "result_struct": None,
        }

    def _parse_codex_json(
        self, stdout: str, stderr: str, returncode: int,
        node_id: str, node_title: str, duration: float, attempt: int,
    ) -> dict[str, Any]:
        """Parse Codex CLI JSON output format."""
        text = stdout.strip()
        session_id = None
        ok = returncode == 0
        try:
            parsed = json.loads(text)
            # Codex uses different envelope fields
            text = str(parsed.get("output", parsed.get("result", text)))
            session_id = parsed.get("session_id")
            ok = ok and not bool(parsed.get("error"))
        except Exception:
            pass
        return {
            "ok": ok,
            "result": text,
            "session_id": session_id,
            "returncode": returncode,
            "stderr": stderr,
            "result_struct": None,
        }

    def is_available(self) -> bool:
        """Check if this agent's command is on PATH."""
        return shutil.which(self.command[0]) is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Built-in backend registry
# ---------------------------------------------------------------------------

_BUILTINS: dict[str, AgentBackend] = {}


def _register_builtin(b: AgentBackend) -> None:
    _BUILTINS[b.name] = b


# Import built-in adapters from the adapters subpackage and register them.
# Adding a new built-in agent means: (1) drop a new module in
# ``hermes_collab_engine/adapters/`` exposing ``BACKEND``, (2) add its
# import here. The ``adapters`` subpackage re-exports the public API
# (``list_adapters`` / ``get_adapter`` / ...) under the new vocabulary.
from .adapters.claude_code import BACKEND as _CLAUDE_CODE  # noqa: E402
from .adapters.codex import BACKEND as _CODEX              # noqa: E402
from .adapters.opencode import BACKEND as _OPENCODE        # noqa: E402
from .adapters.hermes import BACKEND as _HERMES            # noqa: E402

for _b in (_CLAUDE_CODE, _CODEX, _OPENCODE, _HERMES):
    _register_builtin(_b)


def list_backends() -> list[AgentBackend]:
    """List all registered backends (built-in + custom)."""
    return list(_BUILTINS.values())


def get_backend(name: str) -> AgentBackend:
    """Get a backend by name. Raises KeyError if not found."""
    if name not in _BUILTINS:
        raise KeyError(f"Unknown agent backend: {name!r}. Available: {sorted(_BUILTINS.keys())}")
    return _BUILTINS[name]


def detect_available_backends() -> list[AgentBackend]:
    """Return only backends whose command is available on PATH."""
    return [b for b in _BUILTINS.values() if b.is_available()]


def backends_for_capability(capability: str) -> list[AgentBackend]:
    """Return backends that declare the given capability."""
    return [b for b in _BUILTINS.values() if capability in b.capabilities]


def register_backend(backend: AgentBackend) -> None:
    """Register a custom backend at runtime (or override a built-in)."""
    _BUILTINS[backend.name] = backend


def delete_backend(name: str) -> bool:
    """Remove a registered backend by name. Returns True if removed, False if not found."""
    if name in _BUILTINS:
        del _BUILTINS[name]
        return True
    return False
