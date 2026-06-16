"""Provider Profile — structured multi-provider configuration.

Maps the cc-switch Provider pattern into a Python dataclass for
Hermes Collab Engine's worker adapter layer. Each ``ProviderProfile``
describes one API provider (Anthropic, OpenAI, Gemini, or custom)
with its base URL, API key, model rules, and environment variable
mappings.

A provider can be attached to an ``AgentBackend`` at registration time
or passed at runtime via CLI flags (``--provider``, ``--provider-base-url``,
``--provider-api-key``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Protocol → env-var mapping table
# ---------------------------------------------------------------------------

_PROTOCOL_ENV_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "anthropic": {
        "base_url": ("ANTHROPIC_BASE_URL",),
        "api_key": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        "model": ("ANTHROPIC_MODEL",),
    },
    "openai": {
        "base_url": ("OPENAI_BASE_URL",),
        "api_key": ("OPENAI_API_KEY",),
        "model": ("OPENAI_MODEL",),
    },
    "gemini": {
        "api_key": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "model": ("GOOGLE_MODEL", "GEMINI_MODEL"),
    },
}

# Protocols that have no base_url or custom field mappings — resolved via env_aliases
_CUSTOM_PROTOCOLS = frozenset({"custom"})


# ---------------------------------------------------------------------------
# ProviderProfile
# ---------------------------------------------------------------------------


@dataclass
class ProviderProfile:
    """Structured provider configuration.

    Attributes:
        name: Human-readable label, e.g. ``"default"``, ``"deepseek-relay"``.
        protocol: One of ``"anthropic"``, ``"openai"``, ``"gemini"``,
            ``"custom"``.  Controls which environment variables are set.
        base_url: Root URL of the API (no ``/v1`` suffix).
        api_key: Authentication key for this provider.
        default_model: Recommended model identifier for this provider.
        allowed_models: Optional whitelist of acceptable model names.
            Empty/``None`` means no restriction.
        model_prefix: Optional prefix prepended to the model string
            when building the ``--model`` flag.  OpenCode 1.17.x
            requires ``"opencode-go/"`` here.
        path_mode: ``"append"`` appends the protocol's default path
            (e.g. ``/v1/messages``); ``"full"`` uses ``base_url`` as-is.
        headers_extra: Additional HTTP headers for API requests.
        env_aliases: Custom environment variable mappings for
            ``"custom"`` protocol.  Key = provider field (lowercase),
            value = env var name.  E.g. ``{"api_key": "MY_KEY"}``.
    """
    name: str
    protocol: Literal["anthropic", "openai", "gemini", "custom"]
    base_url: str
    api_key: str
    default_model: str = ""
    allowed_models: list[str] | None = None
    model_prefix: str = ""
    path_mode: Literal["append", "full"] = "append"
    headers_extra: dict[str, str] = field(default_factory=dict)
    env_aliases: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderProfile:
        """Deserialize from a dict (e.g. from JSON config)."""
        # Filter to only known fields for forward compat
        valid_fields = {
            "name", "protocol", "base_url", "api_key", "default_model",
            "allowed_models", "model_prefix", "path_mode", "headers_extra",
            "env_aliases",
        }
        filtered = {k: v for k, v in data.items() if k in valid_fields and v is not None}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def env_targets_for_protocol(protocol: str) -> dict[str, tuple[str, ...]]:
    """Return the environment variable targets for a given *protocol*.

    Returns a dict with optional keys ``"base_url"``, ``"api_key"``,
    ``"model"`` each mapping to a tuple of env var names (first = primary).

    For ``"custom"`` protocol the dict is empty; callers should use
    :func:`apply_provider_to_env` instead.
    """
    if protocol in _CUSTOM_PROTOCOLS:
        return {}
    return dict(_PROTOCOL_ENV_MAP.get(protocol, {}))


def apply_provider_to_env(
    env: dict[str, str],
    provider: ProviderProfile | None,
    model_override: str | None = None,
) -> None:
    """Mutate *env* in-place with provider-specific environment variables.

    Sets ``BASE_URL``, ``API_KEY``, and ``MODEL`` env vars according to
    the provider's protocol.  If *model_override* is provided it takes
    precedence over ``provider.default_model``.
    """
    if provider is None:
        return

    # "custom" protocol — use env_aliases dict
    if provider.protocol in _CUSTOM_PROTOCOLS:
        for field_name, env_name in provider.env_aliases.items():
            value = getattr(provider, field_name, None)
            if value is not None:
                env[env_name] = str(value)
        return

    targets = _PROTOCOL_ENV_MAP.get(provider.protocol)
    if targets is None:
        return

    # Base URL
    base_url_targets = targets.get("base_url")
    if base_url_targets and provider.base_url:
        env[base_url_targets[0]] = provider.base_url

    # API key
    key_targets = targets.get("api_key")
    if key_targets and provider.api_key:
        env[key_targets[0]] = provider.api_key

    # Model
    model = model_override or provider.default_model
    model_targets = targets.get("model")
    if model_targets and model:
        env[model_targets[0]] = model


def resolve_model(
    cli_model: str | None,
    provider: ProviderProfile | None,
) -> str | None:
    """Resolve the effective model identifier.

    Priority:
    1. *cli_model* (CLI ``--model`` flag)
    2. ``provider.default_model``
    3. ``HERMES_COLLAB_MODEL`` env var
    4. ``ANTHROPIC_MODEL`` env var
    """
    if cli_model:
        return cli_model
    if provider and provider.default_model:
        return provider.default_model
    return os.environ.get("HERMES_COLLAB_MODEL") or os.environ.get("ANTHROPIC_MODEL")


def build_model_flag_value(
    model: str,
    provider: ProviderProfile | None,
) -> str:
    """Prepend *model_prefix* if the model doesn't already carry it.

    OpenCode 1.17.x requires the ``--model`` value to be prefixed with
    ``"opencode-go/"``.  This helper avoids double-prefixing when the
    model string already starts with the prefix.
    """
    if provider and provider.model_prefix and not model.startswith(provider.model_prefix):
        return provider.model_prefix + model
    return model


__all__ = [
    "ProviderProfile",
    "env_targets_for_protocol",
    "apply_provider_to_env",
    "resolve_model",
    "build_model_flag_value",
]
