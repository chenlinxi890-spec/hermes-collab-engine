"""
Skill Distributor — centralized skill/tool/MCP dispatch for engine workers.

Replaces the old approach of injecting ALL 6 skills + ALL 6 tool profiles
into every worker's prompt. Instead, SkillDistributor resolves what a
specific node needs based on its capability + Leader assignment + Agent
backend support, and returns only the relevant skill content + tool
profiles + MCP server names.

The SKILL_TOOL_MAP and SKILL_MCP_MAP are kept in this standalone file so
they can be reused outside the dragon-team engine (e.g. by hermes-collab).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agents import AgentBackend
    from .skills import SkillEntry, SkillRegistry
    from .tools import ToolRegistry

logger = logging.getLogger(__name__)


# ── Skill → built-in tool mapping ───────────────────────────────────────
# Each skill name maps to the ToolProfile names it needs.
# Add new skills or tools here; the engine reads this at runtime.

SKILL_TOOL_MAP: dict[str, list[str]] = {
    "search-verify":            ["file-edit", "git-local", "mcp-readonly"],
    "implementation-focus":     ["file-edit", "git-local", "python-tests"],
    "test-verify":              ["file-edit", "python-tests"],
    "debug-root-cause":         ["file-edit", "git-local", "python-tests"],
    "risk-checkpoint":          [],
    "browser-automation":       ["browser-automation"],
    "frontend-optimization":   ["file-edit", "git-local"],
}


# ── Skill → MCP server mapping ─────────────────────────────────────────
# Each skill may need certain MCP server types.
# The actual MCP server list is fetched from the live UnifiedRegistry;
# this map only declares *types* of MCP servers needed.
# agent_compat restricts which agents can use these MCP servers.

SKILL_MCP_MAP: dict[str, dict] = {
    "search-verify": {
        "mcp_servers": ["ferris-search", "baidu-search", "open-websearch", "filesystem", "search"],
        "agent_compat": ["claude-code", "hermes"],
        "readonly": True,
    },
    "implementation-focus": {
        "mcp_servers": ["filesystem"],
        "agent_compat": ["claude-code", "hermes"],
        "readonly": False,
    },
    "test-verify": {
        "mcp_servers": [],
        "agent_compat": [],
        "readonly": True,
    },
    "debug-root-cause": {
        "mcp_servers": ["filesystem"],
        "agent_compat": ["claude-code", "hermes"],
        "readonly": False,
    },
    "risk-checkpoint": {
        "mcp_servers": [],
        "agent_compat": [],
        "readonly": True,
    },
    "browser-automation": {
        "mcp_servers": [],
        "agent_compat": [],
        "readonly": True,
    },
    "frontend-optimization": {
        "mcp_servers": ["daisyui"],
        "agent_compat": ["claude-code", "hermes"],
        "readonly": True,
    },
}


# ── Default node capability → skill mapping ────────────────────────────
# When the Leader hasn't explicitly assigned skills, the distributor
# falls back to these defaults based on node capability.

CAPABILITY_DEFAULT_SKILL: dict[str, str] = {
    "scope":            "search-verify",
    "evidence":         "search-verify",
    "analysis":         "search-verify",
    "implementation":   "implementation-focus",
    "coding":           "implementation-focus",
    "verification":     "test-verify",
    "debugging":        "debug-root-cause",
    "planning":         "risk-checkpoint",
    "docs":             "implementation-focus",
    # Fallback for unrecognised capabilities — use the general coding skill
    "general":          "implementation-focus",
    "design":           "frontend-optimization",
    "frontend":         "frontend-optimization",
    "ui":               "frontend-optimization",
}


# ── Map consistency validation ─────────────────────────────────────────


def validate_maps(tool_registry: Any = None) -> list[str]:
    """Check consistency between SKILL_TOOL_MAP, SKILL_MCP_MAP, and
    CAPABILITY_DEFAULT_SKILL.

    If *tool_registry* (a ``ToolRegistry`` instance) is provided, also
    validates that every tool profile name referenced in ``SKILL_TOOL_MAP``
    values is actually registered in the tool registry.

    Returns a list of warning messages (empty if all checks pass).
    Call at import time or during test setup to catch drift early.
    """
    warnings: list[str] = []
    all_skill_names = set(SKILL_TOOL_MAP) | set(SKILL_MCP_MAP)

    for name in all_skill_names:
        if name not in SKILL_TOOL_MAP:
            warnings.append(f"SKILL_MCP_MAP has key {name!r} missing from SKILL_TOOL_MAP")
        if name not in SKILL_MCP_MAP:
            warnings.append(f"SKILL_TOOL_MAP has key {name!r} missing from SKILL_MCP_MAP")

    for cap, skill in CAPABILITY_DEFAULT_SKILL.items():
        if skill not in SKILL_TOOL_MAP:
            warnings.append(
                f"CAPABILITY_DEFAULT_SKILL[{cap!r}] = {skill!r} not found in SKILL_TOOL_MAP"
            )
        if skill not in SKILL_MCP_MAP:
            warnings.append(
                f"CAPABILITY_DEFAULT_SKILL[{cap!r}] = {skill!r} not found in SKILL_MCP_MAP"
            )

    # Validate that tool names referenced in SKILL_TOOL_MAP values actually
    # exist in the tool registry (catches typos or renamed profiles).
    if tool_registry is not None:
        known_profiles = set()
        try:
            for p in tool_registry.list_all():
                known_profiles.add(p.name)
        except Exception:
            known_profiles = set()
        for skill_name, tool_names in SKILL_TOOL_MAP.items():
            for t in tool_names:
                if t not in known_profiles:
                    warnings.append(
                        f"SKILL_TOOL_MAP[{skill_name!r}] references unknown tool "
                        f"profile {t!r} — not found in ToolRegistry"
                    )

    return warnings


# validate_maps() is available for testing — call it with your live registries
# to verify SKILL_TOOL_MAP references exist. Not run at import time because
# the registries are not available yet.


class SkillDistributor:
    """Resolve skills, tools, and MCP servers for a specific worker node."""

    def __init__(
        self,
        skill_registry: Any = None,
        tool_registry: Any = None,
        unified_registry: Any = None,
    ):
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.unified_registry = unified_registry

    def resolve_for_node(
        self,
        node_capability: str,
        leader_skills: list[str] | None,
        agent_backend: AgentBackend | None = None,
    ) -> tuple[list[str], list[str]]:
        """Return (skill_names, tool_profile_names) for a worker node.

        Resolution priority:
        1. Leader explicitly assigned skills → filter by Agent support
        2. No leader skills → fall back to capability default
        3. No match → empty (worker runs with no skill/tool injection)

        Agent compatibility check: if agent_backend has a non-empty
        ``supported_skills`` list, only skills in that list are kept.
        Tool profiles are resolved from two sources:
        - The static ``SKILL_TOOL_MAP`` (primary)
        - Each skill's ``required_tools`` field from the SkillRegistry (supplement)
        """
        # Step 1: determine skill names
        if leader_skills is not None:
            skills = leader_skills
        else:
            default = CAPABILITY_DEFAULT_SKILL.get(node_capability)
            if default is None:
                default = CAPABILITY_DEFAULT_SKILL.get("general", "")
                logger.warning(
                    "Unknown capability %r; falling back to 'general' -> %r",
                    node_capability, default,
                )
            skills = [default] if default else []

        # Step 2: filter by Agent backend support
        if agent_backend and agent_backend.supported_skills:
            skills = [s for s in skills if s in agent_backend.supported_skills]

        # Step 3: resolve tool profiles for these skills
        tool_names: list[str] = []
        seen_tools: set[str] = set()
        for s in skills:
            for t in SKILL_TOOL_MAP.get(s, []):
                if t not in seen_tools:
                    seen_tools.add(t)
                    tool_names.append(t)
            if self.skill_registry is not None:
                entry: SkillEntry | None = self.skill_registry.get(s)  # type: ignore[assignment]
                if entry is not None and entry.required_tools:
                    for t in entry.required_tools:
                        if t not in seen_tools:
                            seen_tools.add(t)
                            tool_names.append(t)

        # Step 4: filter tool names by Agent backend tool support
        if agent_backend and agent_backend.supported_tools:
            tool_names = [t for t in tool_names if t in agent_backend.supported_tools]

        return skills, tool_names

    def resolve_mcp(
        self,
        skill_names: list[str],
        agent_name: str,
    ) -> list[dict]:
        """Return MCP server descriptors for the given skills.

        Returns a list of dicts with keys: name, readonly.
        The list is filtered by agent compatibility and current availability.

        Readonly merge policy: when the same MCP server type is referenced by
        multiple skills with different readonly flags, the permissive (OR) rule
        applies — if *any* skill needs read-write access (readonly=False), the
        merged result is read-write. This is because a more restrictive policy
        (first-writer-wins, the previous behaviour) would silently deny write
        access to a skill that legitimately needs it, causing confusing worker
        failures.
        """
        needed: list[dict] = []
        # Track per server: readonly flag, merged permissively (any RW → RW).
        seen_servers: dict[str, bool] = {}  # server_name → readonly

        for s in skill_names:
            entry = SKILL_MCP_MAP.get(s, {})
            compat = entry.get("agent_compat", [])
            if agent_name not in compat and compat:
                continue  # this MCP type doesn't support this agent

            for mcp_type in entry.get("mcp_servers", []):
                this_readonly = entry.get("readonly", True)
                if mcp_type in seen_servers:
                    # Permissive merge: if any skill needs read-write, grant it.
                    seen_servers[mcp_type] = seen_servers[mcp_type] and this_readonly
                else:
                    seen_servers[mcp_type] = this_readonly

        for mcp_type, readonly in seen_servers.items():
            needed.append({
                "name": mcp_type,
                "readonly": readonly,
            })

        # If UnifiedRegistry is available, cross-check against live MCP servers
        if self.unified_registry is not None:
            try:
                from .registry import MCPEntry
                # Match against server_name (e.g. "filesystem"), not the
                # qualified name (e.g. "mcp__filesystem__read_file").
                live_servers = {mcp.server_name for mcp in self.unified_registry.list_by_type(MCPEntry)}
                needed = [m for m in needed if m["name"] in live_servers]
            except Exception:
                pass  # registry unavailable; return as-configured

        return needed

    def render_for_prompt(
        self,
        skill_names: list[str],
        tool_names: list[str],
        mcp_servers: list[dict],
    ) -> tuple[str, str, str]:
        """Render skills, tools, and MCP blocks for the worker prompt.

        Returns (skills_block, tools_block, mcp_block).
        Each block contains the FULL content (not just names) for
        the resolved skills/tools, so the worker has actionable guidance.
        """
        skills_block = ""
        if skill_names:
            if self.skill_registry is not None:
                skills_list = []
                for name in skill_names:
                    entry = self.skill_registry.get(name)
                    if entry is not None:
                        skills_list.append(entry)
                    else:
                        logger.warning("render_for_prompt: skill %r not found in registry, skipping", name)
                skills_block = self.skill_registry.render_for_prompt(skills_list)
            else:
                logger.warning("skill_registry not set; skills block empty for %s", skill_names)

        tools_block = ""
        if tool_names:
            if self.tool_registry is not None:
                profiles = []
                for name in tool_names:
                    entry = self.tool_registry.get(name)
                    if entry is not None:
                        profiles.append(entry)
                if profiles:
                    tools_block = self.tool_registry.render_for_prompt(profiles)
            else:
                logger.warning("tool_registry not set; tools block empty for %s", tool_names)

        mcp_block = ""
        if mcp_servers:
            parts = ["MCP servers assigned to this worker:"]
            for m in mcp_servers:
                label = "read-only" if m.get("readonly") else "read-write"
                parts.append(f"  - {m['name']} ({label})")
            mcp_block = "\n".join(parts) + "\n\n"

        return skills_block, tools_block, mcp_block


__all__ = [
    "SKILL_TOOL_MAP",
    "SKILL_MCP_MAP",
    "CAPABILITY_DEFAULT_SKILL",
    "SkillDistributor",
]
