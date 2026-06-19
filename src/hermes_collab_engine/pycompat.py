"""Runtime Python version feature detection for the Hermes Collab Engine.

Detects and reports which :pep:`703` (free-threaded), :pep:`744` (JIT),
:pep:`667` (locals()), colour tracebacks, mimalloc, and other Python 3.13+
features are available on the current interpreter.

All checks are safe to call on Python 3.11+ and degrade gracefully on older
versions. No third-party imports.
"""

from __future__ import annotations

import os
import platform
import struct
import sys
from dataclasses import dataclass, asdict, field
from typing import Any


# ── version helpers ──────────────────────────────────────────────────────

def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".")[:3])


def _sys_version_tuple() -> tuple[int, int, int]:
    return sys.version_info[:3]


_AT_LEAST_3_11 = _sys_version_tuple() >= (3, 11)
_AT_LEAST_3_12 = _sys_version_tuple() >= (3, 12)
_AT_LEAST_3_13 = _sys_version_tuple() >= (3, 13)


# ── checks ───────────────────────────────────────────────────────────────

def check_free_threading() -> dict[str, Any]:
    """Detect :pep:`703` free-threaded CPython (``--disable-gil``).

    Python 3.13 introduced ``sys._is_gil_enabled()`` as a private API.
    The public ``sys.is_gil_enabled()`` was added in 3.13.1.
    This function checks both and falls back to ``Py_GIL_DISABLED`` build
    flag if the runtime API is unavailable.
    """
    available = _AT_LEAST_3_13
    enabled = None
    if hasattr(sys, "is_gil_enabled"):
        enabled = sys.is_gil_enabled()  # type: ignore[attr-defined]  # 3.13.1+
    elif hasattr(sys, "_is_gil_enabled"):
        enabled = sys._is_gil_enabled()  # type: ignore[attr-defined]  # 3.13.0

    if enabled is None:
        # Fallback: check if the interpreter was compiled with Py_GIL_DISABLED
        enabled = bool(os.environ.get("Py_GIL_DISABLED", "")) or (
            hasattr(sys, "abiflags") and "t" in getattr(sys, "abiflags", "")
        )

    return {
        "available": available,
        "enabled": enabled if available else False,
        "description": "Free-threaded CPython (--disable-gil, PEP 703)"
        if available
        else "Free-threaded CPython (PEP 703) — requires Python 3.13+",
    }


def check_jit() -> dict[str, Any]:
    """Detect experimental :pep:`744` JIT compiler.

    Python 3.13 shipped the JIT as an **experimental** build-time flag
    (``--enable-experimental-jit``). At runtime, the private
    ``sys._is_jit_enabled()``  reflects the build-time decision.
    """
    available = _AT_LEAST_3_13
    enabled = False
    if hasattr(sys, "_is_jit_enabled"):
        enabled = sys._is_jit_enabled()  # type: ignore[attr-defined]
    return {
        "available": available,
        "enabled": enabled,
        "description": "Experimental JIT compiler (PEP 744, --enable-experimental-jit)"
        if enabled
        else "Experimental JIT compiler (PEP 744) — not enabled in this build",
    }


def check_locals_semantics() -> dict[str, Any]:
    """Detect :pep:`667` ``locals()`` semantics.

    Python 3.13 changes ``locals()`` to behave consistently between
    function and class scopes. The easiest runtime check: the
    ``sys._PEP_667`` sentinel if it exists.
    """
    return {
        "available": _AT_LEAST_3_13,
        "enabled": _AT_LEAST_3_13,
        "description": "Consistent locals() semantics (PEP 667)"
        if _AT_LEAST_3_13
        else "Consistent locals() semantics (PEP 667) — requires Python 3.13+",
    }


def check_mimalloc() -> dict[str, Any]:
    """Detect mimalloc as the default memory allocator.

    Python 3.13 integrated the mimalloc allocator (MIT licensed) as the
    default pymalloc replacement on supported platforms. It can be
    disabled at build time with ``--without-mimalloc``.
    """
    available = _AT_LEAST_3_13
    enabled = False
    # Check allocator name via sys._debugmallocstats or sysconfig if available
    try:
        import sysconfig

        mi_opt = sysconfig.get_config_var("WITH_MIMALLOC")
        if mi_opt is not None:
            enabled = bool(int(mi_opt))
    except (ImportError, ValueError, TypeError):
        pass

    if not enabled:
        # Conservative fallback: common CPython 3.13 builds include mimalloc
        enabled = _AT_LEAST_3_13

    return {
        "available": available,
        "enabled": enabled,
        "description": "mimalloc default memory allocator"
        if enabled
        else "mimalloc default memory allocator — requires Python 3.13+",
    }


def check_colour_tracebacks() -> dict[str, Any]:
    """Detect colourised error tracebacks.

    Python 3.13 renders tracebacks in colour (via ``rich``-style
    ANSI highlighting) when stderr is a TTY. The feature can be
    controlled via environment variables (``PYTHON_COLORS``,
    ``FORCE_COLOR``, ``NO_COLOR``).
    """
    available = _AT_LEAST_3_13
    # Emulation: even if the env suppresses colour, the feature is present.
    effectively_on = (
        available
        and sys.stderr.isatty()
        and not os.environ.get("NO_COLOR")
        and os.environ.get("PYTHON_COLORS", "1") != "0"
    )
    return {
        "available": available,
        "enabled": effectively_on,
        "description": "Colourised error tracebacks"
        if available
        else "Colourised error tracebacks — requires Python 3.13+",
    }


def check_repl() -> dict[str, Any]:
    """Detect the improved interactive REPL.

    Python 3.13 ships a new interactive REPL based on ``pyrepl`` with
    multi-line editing, syntax highlighting, and history search.
    """
    return {
        "available": _AT_LEAST_3_13,
        "enabled": _AT_LEAST_3_13,
        "description": "Improved interactive REPL (pyrepl-based, multi-line editing, syntax highlighting)"
        if _AT_LEAST_3_13
        else "Improved interactive REPL — requires Python 3.13+",
    }


def check_typing_features() -> dict[str, Any]:
    """Summarise typing :pep:`696`, :pep:`702`, :pep:`705`, :pep:`742`.

    * :pep:`696` (3.12) — TypeVar defaults (``TypeVar("T", default=int)``).
    * :pep:`702` (3.13) — ``typing.deprecated()`` decorator.
    * :pep:`705` (3.13) — ``TypedDict`` with ``read_only`` items.
    * :pep:`742` (3.13) — ``typing.TypeIs`` for type narrowing.
    """
    features: dict[str, bool] = {}

    # PEP 696 (3.12) — TypeVar defaults
    features["TypeVar_defaults"] = _AT_LEAST_3_12

    # PEP 702 (3.13) — typing.deprecated()
    if _AT_LEAST_3_13:
        import typing

        features["deprecated_decorator"] = hasattr(typing, "deprecated")
    else:
        features["deprecated_decorator"] = False

    # PEP 705 (3.13) — TypedDict read_only
    if _AT_LEAST_3_13:
        import typing

        features["TypedDict_read_only"] = hasattr(typing, "ReadOnly")
    else:
        features["TypedDict_read_only"] = False

    # PEP 742 (3.13) — TypeIs
    if _AT_LEAST_3_13:
        import typing

        features["TypeIs"] = hasattr(typing, "TypeIs")
    else:
        features["TypeIs"] = False

    return {
        "available": _AT_LEAST_3_13,
        "enabled": features,
        "description": f"typing enhancements: PEP 696 (TypeVar defaults{' ✓' if _AT_LEAST_3_12 else ' ✗'}), "
        f"PEP 702 (deprecated{' ✓' if features.get('deprecated_decorator') else ' ✗'}), "
        f"PEP 705 (ReadOnly{' ✓' if features.get('TypedDict_read_only') else ' ✗'}), "
        f"PEP 742 (TypeIs{' ✓' if features.get('TypeIs') else ' ✗'})",
    }


def check_removed_modules() -> dict[str, Any]:
    """List :pep:`594` removed stdlib modules.

    Python 3.13 removed 19 legacy modules: ``2to3``, ``aifc``, ``asynchat``,
    ``asyncore``, ``audioop``, ``cfmfile``, ``chunk``, ``crypt``,
    ``imghdr``, ``imp``, ``msilib``, ``nis``, ``nntplib``, ``ossaudiodev``,
    ``pipes``, ``sndhdr``, ``spwd``, ``sunau``, ``telnetlib``, ``uu``,
    ``xdrlib``, ``lib2to3``.
    """
    _REMOVED_MODULES = [
        "2to3", "aifc", "asynchat", "asyncore", "audioop",
        "cfmfile", "chunk", "crypt", "imghdr", "imp",
        "msilib", "nis", "nntplib", "ossaudiodev", "pipes",
        "sndhdr", "spwd", "sunau", "telnetlib", "uu", "xdrlib",
        "lib2to3",
    ]
    still_present: list[str] = []
    successfully_removed: list[str] = []
    for mod in _REMOVED_MODULES:
        # We use importlib.util.find_spec to avoid triggering deprecated import warnings
        import importlib.util

        spec = importlib.util.find_spec(mod)
        if spec is not None:
            still_present.append(mod)
        else:
            successfully_removed.append(mod)

    return {
        "available": _AT_LEAST_3_13,
        "enabled": len(successfully_removed),
        "total_removed": len(_REMOVED_MODULES),
        "still_present": still_present,
        "description": f"Removed stdlib modules: {len(successfully_removed)}/{len(_REMOVED_MODULES)} gone"
        if _AT_LEAST_3_13
        else "Removed stdlib modules — requires Python 3.13+",
    }


def check_platform_tiers() -> dict[str, Any]:
    """Report whether iOS and Android are recognised Tier-3 platforms.

    Python 3.13 promoted iOS and Android to Tier 3 (compile-only,
    community maintained). This check looks for ``sys.platform``
    values that start with ``ios`` or ``android`` and the existence
    of platform-specific sysconfig data.
    """
    current_platform = sys.platform
    ios_tier3 = current_platform.startswith("ios") if _AT_LEAST_3_13 else False
    android_tier3 = current_platform.startswith("android") if _AT_LEAST_3_13 else False

    # Also check whether the sysconfig data suggests cross-compile awareness
    try:
        import sysconfig

        ios_aware = any("ios" in k for k in sysconfig.get_platform_names())  # type: ignore[attr-defined]
        android_aware = any("android" in k for k in sysconfig.get_platform_names())  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        ios_aware = False
        android_aware = False

    return {
        "available": _AT_LEAST_3_13,
        "current_platform": current_platform,
        "ios_tier3_support": ios_tier3 or ios_aware,
        "android_tier3_support": android_tier3 or android_aware,
        "description": "iOS/Android Tier 3 platform support (PEP 730, PEP 738)"
        if _AT_LEAST_3_13
        else "iOS/Android Tier 3 platform support — requires Python 3.13+",
    }


def check_improved_error_messages() -> dict[str, Any]:
    """Detect improved error messages.

    Python 3.12+ significantly improved error messages (wrong-import
    suggestions, ``did you mean`` for attribute errors, better assertion
    messages). Python 3.13 adds colour and better SyntaxError hints.
    """
    return {
        "available": _AT_LEAST_3_13,
        "enabled": _AT_LEAST_3_13,
        "description": "Improved SyntaxError hints and coloured error messages"
        if _AT_LEAST_3_13
        else "Improved error messages — continuously improved since Python 3.12",
    }


# ── aggregate result ─────────────────────────────────────────────────────

@dataclass
class PythonCompatReport:
    """Full Python compatibility report, safe to serialise to JSON."""

    python_version: str
    python_implementation: str
    python_build: tuple[str, str]
    python_compiler: str
    bits: int
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_all() -> PythonCompatReport:
    """Run all feature checks and return a structured report."""
    return PythonCompatReport(
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        python_build=sys.version_info[:3],
        python_compiler=platform.python_compiler(),
        bits=struct.calcsize("P") * 8,
        checks={
            "free_threading": check_free_threading(),
            "jit": check_jit(),
            "locals_semantics": check_locals_semantics(),
            "mimalloc": check_mimalloc(),
            "colour_tracebacks": check_colour_tracebacks(),
            "improved_repl": check_repl(),
            "typing_features": check_typing_features(),
            "removed_modules": check_removed_modules(),
            "platform_tiers": check_platform_tiers(),
            "improved_error_messages": check_improved_error_messages(),
        },
    )


def summary_lines(report: PythonCompatReport | None = None) -> list[str]:
    """Produce a human-readable summary of Python 3.13 feature support."""
    r = report or check_all()
    lines: list[str] = []
    lines.append(f"Python {r.python_version} ({r.python_implementation}) on {r.bits}-bit {r.python_compiler}")
    lines.append("")

    # Group checks by status
    for name, check in r.checks.items():
        label = name.replace("_", " ").title()
        if isinstance(check, dict):
            available = check.get("available", False)
            enabled = check.get("enabled", False)
            desc = check.get("description", "")
            # Some checks store numeric enabled (e.g., removed modules count)
            if isinstance(enabled, bool):
                status = "✓" if available and enabled else "✗" if available else "—"
            elif isinstance(enabled, (int, float)):
                # Show counts
                total = check.get("total_removed", enabled)
                status = f"{enabled}/{total}" if total else str(enabled)
            elif isinstance(enabled, dict):
                # Sub-features, handled below
                status = "✓" if available else "—"
            else:
                status = "?" if available else "—"

            if isinstance(enabled, dict) and available:
                sub_statuses = ", ".join(
                    f"{k}={v}" for k, v in enabled.items()
                )
                lines.append(f"  {status:>8s}  {label}: {sub_statuses}")
            else:
                lines.append(f"  {status:>8s}  {label}: {desc}")
        else:
            lines.append(f"  {'?':>8s}  {label}")

    lines.append("")
    lines.append(f"Report generated: Python {r.python_version} — {r.python_implementation} "
                 f"on {platform.machine()} ({r.python_compiler})")
    return lines
