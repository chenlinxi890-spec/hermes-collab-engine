#!/usr/bin/env python3
"""Hermes Collab Engine launcher — reads API config from ~/.hermes/ first, falls back to ~/.claude/."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HERMES_DIR = Path.home() / '.hermes'
CLAUDE_DIR = Path.home() / '.claude'

PROXY_BINARY = ROOT / 'proxy' / 'opencode-proxy'
PROXY_PORT = 18080

VERSION = 'v5.0'
GITHUB_URL = 'https://github.com/lpc0387/hermes-collab-engine'
TAGLINE_ZH = '多 Agent 协同引擎 · Leader 拆解 · Worker 并行 · 面板可视化'
TAGLINE_EN = 'Multi-agent collab engine · Leader plans · Workers run in parallel · Live dashboard'

# Agent config files this launcher reads/writes. Must share the same parent
# directory as the project root (path-consistency invariant).
AGENT_CONFIG_DIRS = [HERMES_DIR, CLAUDE_DIR]
AGENT_CONFIG_FILES = [
    HERMES_DIR / '.env',
    HERMES_DIR / 'config.yaml',
    HERMES_DIR / 'auth.json',
    CLAUDE_DIR / 'settings.json',
]
RUNTIME_CONFIG_PATH = ROOT / '.runtime-config.json'


def _supports_color() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    return hasattr(__import__('sys').stdout, 'isatty') and __import__('sys').stdout.isatty()


def print_banner() -> None:
    """Render the launcher banner: project name, tagline, GitHub link, version."""
    use_color = _supports_color()
    C = {
        'reset': '\033[0m' if use_color else '',
        'cyan':  '\033[38;5;51m'  if use_color else '',
        'blue':  '\033[38;5;75m'  if use_color else '',
        'mag':   '\033[38;5;213m' if use_color else '',
        'gray':  '\033[38;5;245m' if use_color else '',
        'green': '\033[38;5;120m' if use_color else '',
        'bold':  '\033[1m'         if use_color else '',
        'dim':   '\033[2m'         if use_color else '',
    }

    # Compact ASCII logo — readable at 80 cols, Hermes caduceus motif on the side.
    logo_lines = [
        " _   _                                ____      _ _       _     ",
        "| | | | ___ _ __ _ __ ___   ___  ___ / ___|___ | | | __ _| |__  ",
        "| |_| |/ _ \\ '__| '_ ` _ \\ / _ \\/ __| |   / _ \\| | |/ _` | '_ \\ ",
        "|  _  |  __/ |  | | | | | |  __/\\__ \\ |__| (_) | | | (_| | |_) |",
        "|_| |_|\\___|_|  |_| |_| |_|\\___||___/\\____\\___/|_|_|\\__,_|_.__/ ",
        "                          E N G I N E                            ",
    ]

    width = max(len(line) for line in logo_lines)
    bar = '─' * width

    print()
    print(f"{C['gray']}{bar}{C['reset']}")
    for line in logo_lines:
        print(f"{C['cyan']}{C['bold']}{line}{C['reset']}")
    print(f"{C['gray']}{bar}{C['reset']}")
    print(f"  {C['mag']}{C['bold']}Hermes Collab Engine{C['reset']}  "
          f"{C['green']}{VERSION}{C['reset']}  "
          f"{C['dim']}{C['gray']}— 协同引擎启动器 / Launcher{C['reset']}")
    print(f"  {C['blue']}▸{C['reset']} {C['gray']}{TAGLINE_ZH}{C['reset']}")
    print(f"  {C['blue']}▸{C['reset']} {C['gray']}{TAGLINE_EN}{C['reset']}")
    print(f"  {C['blue']}⌬{C['reset']} {C['cyan']}GitHub:{C['reset']} "
          f"{C['bold']}{GITHUB_URL}{C['reset']}")
    print(f"{C['gray']}{bar}{C['reset']}")
    print()


DEFAULT_MODELS = [
    'kimi-k2.6', 'glm-5.1', 'deepseek-v4-pro', 'deepseek-v4-flash',
    'doubao-seed-2.0-lite', 'doubao-seed-2.0-pro', 'doubao-seed-2.0-code',
    'minimax-m2.7', 'minimax-m3',
    'mimo-v2.5', 'mimo-v2.5-pro[1M]', 'mimo-v2-pro[1M]',
]


def load_json_lenient(path: Path):
    text = path.read_text(encoding='utf-8')
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(text)


def unique(items):
    out = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


# ── Hermes config sources ──────────────────────────────────────────────

def read_hermes_env() -> dict | None:
    """Read ~/.hermes/.env for ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL."""
    env_path = HERMES_DIR / '.env'
    if not env_path.exists():
        return None
    kv = {}
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            kv[k.strip()] = v.strip()
    token = kv.get('ANTHROPIC_API_KEY') or kv.get('ANTHROPIC_AUTH_TOKEN')
    base_url = kv.get('ANTHROPIC_BASE_URL')
    if not token or not base_url:
        return None
    return {'source': 'Hermes .env', 'source_path': str(env_path),
            'base_url': base_url, 'token': token, 'models': None,
            'default_leader': None, 'default_worker': None}


def read_hermes_auth() -> dict | None:
    """Read ~/.hermes/auth.json credential pool for anthropic credentials."""
    auth_path = HERMES_DIR / 'auth.json'
    if not auth_path.exists():
        return None
    try:
        data = load_json_lenient(auth_path)
    except Exception:
        return None
    pool = data.get('credential_pool', {})
    anthropic = pool.get('anthropic', [])
    if not anthropic:
        return None
    cred = anthropic[0]  # highest priority
    base_url = cred.get('base_url')
    if not base_url:
        return None
    # The actual secret is not stored in auth.json, need the env var
    token = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN')
    if not token:
        return None
    return {'source': 'Hermes auth.json', 'source_path': str(auth_path),
            'base_url': base_url, 'token': token, 'models': None,
            'default_leader': None, 'default_worker': None}


def read_hermes_config_yaml() -> dict | None:
    """Read ~/.hermes/config.yaml for model.base_url and model.default."""
    config_path = HERMES_DIR / 'config.yaml'
    if not config_path.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    except Exception:
        # Fallback: simple regex parse for base_url
        text = config_path.read_text(encoding='utf-8')
        m = re.search(r'base_url:\s*["\']?(\S+?)["\']?\s*$', text, re.M)
        base_url = m.group(1) if m else None
        dm = re.search(r'default:\s*(\S+)', text)
        default_model = dm.group(1) if dm else None
        if not base_url:
            return None
        token = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN')
        if not token:
            return None
        return {'source': 'Hermes config.yaml', 'source_path': str(config_path),
                'base_url': base_url, 'token': token,
                'models': [default_model] if default_model else None,
                'default_leader': default_model, 'default_worker': None}
    base_url = (data.get('model') or {}).get('base_url')
    default_model = (data.get('model') or {}).get('default')
    if not base_url:
        return None
    token = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN')
    if not token:
        return None
    return {'source': 'Hermes config.yaml', 'source_path': str(config_path),
            'base_url': base_url, 'token': token,
            'models': [default_model] if default_model else None,
            'default_leader': default_model, 'default_worker': None}


def collect_hermes_configs():
    """Try Hermes config sources in priority order."""
    sources = []
    for reader in (read_hermes_env, read_hermes_config_yaml, read_hermes_auth):
        result = reader()
        if result:
            sources.append(result)
    return sources


# ── Claude config sources (fallback) ───────────────────────────────────

def collect_claude_profiles():
    profiles = []
    settings = CLAUDE_DIR / 'settings.json'
    if settings.exists():
        try:
            profiles.append({'name': 'Claude Code 当前配置', 'path': str(settings),
                             'data': load_json_lenient(settings)})
        except Exception:
            pass
    profiles_dir = CLAUDE_DIR / 'profiles'
    if profiles_dir.exists():
        for p in sorted(profiles_dir.glob('*.json')):
            try:
                profiles.append({'name': p.stem, 'path': str(p),
                                 'data': load_json_lenient(p)})
            except Exception:
                pass
    return profiles


def models_from_claude(profile):
    data = profile['data']
    env = data.get('env', {})
    models = []
    for key in ['ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL',
                'ANTHROPIC_DEFAULT_HAIKU_MODEL']:
        models.append(env.get(key))
    models.extend(data.get('availableModels') or [])
    return unique(models)


def get_config_from_claude():
    profiles = collect_claude_profiles()
    if not profiles:
        return None
    labels = []
    for p in profiles:
        env = p['data'].get('env', {})
        labels.append(f"{p['name']} | {env.get('ANTHROPIC_BASE_URL','未设置 BaseURL')} | 模型数 {len(models_from_claude(p))}")
    selected = choose('选择 Claude 配置来源', labels)
    profile = profiles[labels.index(selected)]
    env = profile['data'].get('env', {})
    token = env.get('ANTHROPIC_AUTH_TOKEN') or env.get('ANTHROPIC_API_KEY')
    base_url = env.get('ANTHROPIC_BASE_URL')
    models = models_from_claude(profile)
    if not token or not base_url:
        print('该配置缺少 BaseURL 或 API Key。')
        return None
    return {'source': profile['name'], 'source_path': profile['path'],
            'base_url': base_url, 'token': token,
            'models': models or DEFAULT_MODELS,
            'default_leader': env.get('ANTHROPIC_DEFAULT_OPUS_MODEL'),
            'default_worker': env.get('ANTHROPIC_DEFAULT_SONNET_MODEL')}


# ── UI helpers ─────────────────────────────────────────────────────────

def choose(label, items, default=1):
    print(f'\n{label}')
    for i, item in enumerate(items, 1):
        print(f'  {i}. {item}')
    while True:
        raw = input(f'请选择编号 [默认 {default}]: ').strip()
        try:
            idx = default if not raw else int(raw)
            if 1 <= idx <= len(items):
                return items[idx - 1]
        except ValueError:
            pass
        print('输入无效，请重新选择。')


def prompt(text, default=''):
    suffix = f' [默认 {default}]' if default else ''
    raw = input(f'{text}{suffix}: ').strip()
    return raw or default


# ── Path consistency & previous-runtime loading ────────────────────────

def enforce_path_consistency() -> None:
    """Verify agent config dirs share the project's parent directory.

    The launcher reads/writes config from ~/.hermes/ and ~/.claude/. We require
    those directories (and the project root) to live under a common parent so
    deployments stay self-contained — e.g. all of /root/hermes-collab-engine,
    /root/.hermes, /root/.claude under /root. If a dir exists but lives
    elsewhere, abort instead of silently reading the "wrong" config.
    """
    project_parent = ROOT.parent.resolve()

    print('检查 agent 配置路径一致性...')
    print(f'  项目根目录: {ROOT}')
    print(f'  期望共同父路径: {project_parent}')
    print('  将读取以下 agent 配置文件（如存在）：')
    for f in AGENT_CONFIG_FILES:
        print(f'    - {f}')

    errors = []
    for d in AGENT_CONFIG_DIRS:
        if not d.exists():
            # Missing dirs are fine — caller decides whether they were needed.
            continue
        try:
            real = d.resolve()
        except OSError as e:
            errors.append(f'无法解析 {d}: {e}')
            continue
        # Walk up parents looking for the shared parent.
        if project_parent not in real.parents and real != project_parent:
            errors.append(
                f'{d} 解析为 {real}，与项目父目录 {project_parent} '
                f'不在同一路径树下'
            )

    if errors:
        print()
        print('✗ 路径一致性检查失败（agent 配置目录与项目不在同一父路径下）：')
        for e in errors:
            print(f'  - {e}')
        print()
        print('请将 agent 配置目录放到与本项目相同的父目录下，或调整项目位置后重试。')
        raise SystemExit(2)

    print('  ✓ 路径一致性 OK')
    print()


def _warn_if_masked_env() -> None:
    """If ~/.hermes/.env holds a masked API key with no live replacement in
    os.environ, warn the user before they fill out 6 prompts. The engine
    would otherwise launch and 401 on the first model call.
    """
    env_path = HERMES_DIR / '.env'
    if not env_path.exists():
        return
    try:
        kv = {}
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            kv[k.strip()] = v.strip()
    except Exception:
        return

    on_disk = kv.get('ANTHROPIC_API_KEY', '') or kv.get('ANTHROPIC_AUTH_TOKEN', '')
    live = (os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN') or '').strip()
    is_mask = bool(on_disk) and (
        on_disk == '*' * len(on_disk)
        or (len(on_disk) <= 16 and '...' in on_disk)
    )

    if is_mask and not live:
        print()
        print('⚠ 检测到 ~/.hermes/.env 中的 ANTHROPIC_API_KEY 是占位符 (***) —')
        print('  引擎将无法调用模型。修复方法：')
        print('    1) 在接下来的 Leader/Worker 配置里手动填入真 key（不是 ***）')
        print('    2) 或者先在终端跑：hermes config set ANTHROPIC_API_KEY "sk-..."')
        print()


def load_previous_runtime() -> dict:
    """Load the most recent .runtime-config.json so empty answers can keep prior values."""
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_CONFIG_PATH.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'⚠ 无法读取上次的 runtime 配置（{RUNTIME_CONFIG_PATH}）：{e}')
        print('  将视为首次启动。')
        return {}


def _typing_animation(label: str, dots: int = 4, interval: float = 0.25) -> None:
    """Print '<label>。' progressively to convey 'filling in...' feedback."""
    sys = __import__('sys')
    sys.stdout.write(label)
    sys.stdout.flush()
    for _ in range(dots):
        time.sleep(interval)
        sys.stdout.write('。')
        sys.stdout.flush()
    sys.stdout.write('\n')
    sys.stdout.flush()


def _mask(token: str) -> str:
    if not token:
        return '(空)'
    if len(token) <= 8:
        return '*' * len(token)
    return f'{token[:4]}...{token[-4:]}'


# ── Adapter field schema ──────────────────────────────────────────────
# Each worker adapter has a different credential contract. This drives
# how ask_agent_config() presents fields and which env vars get written
# to ~/.hermes/.env. References:
#   - Codex CLI: OpenAI-compatible (OPENAI_API_KEY, no base_url required)
#   - Claude Code: Anthropic-compatible (ANTHROPIC_API_KEY + ANTHROPIC_BASE_URL)
#   - OpenCode: provider/model format ("opencode-go/<model>"), auth_token
#   - Hermes Agent: Anthropic-compatible (ANTHROPIC_API_KEY + ANTHROPIC_BASE_URL)
# The user's "go" / "zen" plan concept: "go" plan = key-only (model includes
# gateway info), "zen" plan = key + base_url. We honor that here.
ADAPTER_FIELD_SCHEMA = {
    'openclaw': {
        "fields": [
            "api_key",
            "model"
        ],
        "optional_fields": [],
        "format": "openai",
        "env_var": "OPENCLAW_API_KEY",
        "base_url_env": ""
    },

    'copilot': {
        "fields": [
            "api_key",
            "model"
        ],
        "optional_fields": [
            "base_url"
        ],
        "format": "openai",
        "env_var": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL"
    },

    'windsurf': {
        "fields": [
            "api_key",
            "model"
        ],
        "optional_fields": [],
        "format": "openai",
        "env_var": "OPENAI_API_KEY",
        "base_url_env": ""
    },

    'cursor': {
        "fields": [
            "api_key",
            "model"
        ],
        "optional_fields": [
            "base_url"
        ],
        "format": "openai",
        "env_var": "CURSOR_API_KEY",
        "base_url_env": "CURSOR_BASE_URL"
    },

    'claude-code': {
        'fields': ['base_url', 'api_key', 'model'],
        'optional_fields': ['base_url'],  # Anthropic API can default
        'format': 'anthropic',
        'env_var': 'ANTHROPIC_API_KEY',
        'base_url_env': 'ANTHROPIC_BASE_URL',
    },
    'codex': {
        'fields': ['api_key', 'model'],
        'optional_fields': ['base_url'],  # OpenAI default if omitted
        'format': 'openai',
        'env_var': 'OPENAI_API_KEY',
        'base_url_env': 'OPENAI_BASE_URL',
    },
    'opencode': {
        'fields': ['api_key', 'model'],  # model is "<provider>/<name>"
        'optional_fields': ['base_url'],
        'format': 'provider-routed',
        'env_var': 'OPENCODE_API_KEY',
        'base_url_env': 'OPENCODE_BASE_URL',
    },
    'hermes': {
        'fields': ['base_url', 'api_key', 'model'],
        'optional_fields': ['base_url'],
        'format': 'anthropic',
        'env_var': 'ANTHROPIC_API_KEY',
        'base_url_env': 'ANTHROPIC_BASE_URL',
    },
}


def _detect_creds_for_adapter(adapter_name: str) -> dict:
    """Auto-detect usable credentials for `adapter_name` from ~/.hermes/.env.

    Returns a dict with the same shape as a single role's runtime config
    (base_url / api_key / model), with any field left empty if not found
    or unusable. Masked (``***``) values are treated as unusable so we
    never propose them as defaults — that's how the previous
    self-poisoning loop happened.
    """
    schema = ADAPTER_FIELD_SCHEMA.get(adapter_name, ADAPTER_FIELD_SCHEMA['claude-code'])
    env_path = HERMES_DIR / '.env'
    if not env_path.exists():
        return {'base_url': '', 'api_key': '', 'model': ''}
    try:
        kv = {}
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            kv[k.strip()] = v.strip()
    except Exception:
        return {'base_url': '', 'api_key': '', 'model': ''}

    def _usable(val: str) -> str:
        """Return val only if non-empty and not a mask placeholder.

        We recognize two mask patterns:
          1. Pure asterisk run (``***``, ``****``, ...)
          2. Hermes-style partial mask (``sk-c...0uD3``) — middle is `...`
             and the prefix/suffix is suspiciously short (≤4 chars each).
             These are *display* formats, not real keys.
        """
        if not val:
            return ''
        if val == '*' * len(val):
            return ''
        if len(val) <= 16 and '...' in val:
            # 13-char sk-cMw...0uD3 pattern, 11-char sk-x...xxxx, etc.
            return ''
        return val

    api_key = _usable(kv.get(schema['env_var']) or kv.get(schema['env_var'].replace('_API_KEY', '_AUTH_TOKEN')) or '')
    base_url = _usable(kv.get(schema['base_url_env']) or '') if schema.get('base_url_env') else ''
    return {'base_url': base_url, 'api_key': api_key, 'model': ''}


def ask_agent_config(role_label: str, prev: dict, schema: dict | None = None) -> dict:
    """Prompt for one agent's base_url / api_key / model. Empty -> keep prev value.

    `prev` is the previously persisted dict for this role (may be empty).
    `schema` is the ADAPTER_FIELD_SCHEMA entry for the chosen worker
    adapter; it controls which fields are required vs optional and the
    one-tap "use detected" suggestion. If a required field has no
    previous value AND the user leaves it blank, abort.

    Auto-detect: when the detected credential differs from `prev`, print
    a one-tap "[Y/n] use detected value" prompt so the user can confirm
    in a single keystroke instead of retyping the key.
    """
    schema = schema or ADAPTER_FIELD_SCHEMA['claude-code']
    required = [f for f in schema['fields'] if f not in schema.get('optional_fields', [])]

    print(f'── 配置 {role_label} ──')
    if prev:
        print(f'  上次值：base_url={prev.get("base_url") or "(无)"}'
              f'  api_key={_mask(prev.get("api_key", ""))}'
              f'  model={prev.get("model") or "(无)"}')
        print('  留空则沿用上次配置；任意一项首次启动且留空将报错退出。')
    else:
        print('  首次配置，必填项需手动输入；带 * 的为可选。')

    fields = [
        ('base_url', f'{role_label} BaseURL'),
        ('api_key',  f'{role_label} API Key / Auth Token'),
        ('model',    f'{role_label} 模型名称'),
    ]
    out = {}
    for key, label in fields:
        is_required = key in required
        marker = '' if is_required else ' *可选*'
        prev_val = prev.get(key, '') if prev else ''
        hint = _mask(prev_val) if key == 'api_key' and prev_val else (prev_val or '')
        suffix = f' [留空保留上次值: {hint}]{marker}' if hint else f'{marker}'
        raw = input(f'  {label}{suffix}: ').strip()
        if not raw:
            if not prev_val:
                if not is_required:
                    out[key] = ''
                    continue
                print(f'  ✗ {label} 为空且无历史值，无法启动。')
                raise SystemExit(2)
            print(f'  · {label} 留空 → 沿用上次值')
            out[key] = prev_val
        else:
            out[key] = raw

    # Last-line defense: never let a masked value sneak through into the
    # runtime config or .env. If a previous value was already polluted,
    # surface it loudly so the user can fix it instead of silently
    # breaking their engine again.
    def _is_mask(v: str) -> bool:
        if not v:
            return False
        if v == '*' * len(v):
            return True
        if len(v) <= 16 and '...' in v:
            return True
        return False
    for k in ('api_key', 'base_url'):
        v = out.get(k, '')
        if _is_mask(v):
            print(f'  ✗ {k} 是占位符 ({v})，请重新输入真值。')
            raise SystemExit(2)

    print()
    _typing_animation(f'  正在填入 {role_label} 配置')
    print(f'  ✓ {role_label}: {out["base_url"] or "(默认)"}  |  '
          f'key={_mask(out["api_key"])}  |  model={out["model"]}')
    print()
    return out


def choose_worker_agent(prev: str = '') -> str:
    """Prompt the user to pick which agent backend the engine will spawn for
    worker nodes. Lists every registered adapter and annotates the ones whose
    CLI is on PATH with 「✓ 已挂载」. Falls back to the previous selection if
    the user just hits enter, and defaults to ``claude-code`` on a first run.
    """
    # Inline import keeps the launcher's module-load order light — start.py
    # is the entry point and shouldn't drag in the whole engine just to ask
    # one menu question.
    import sys as _sys
    _ROOT = Path(__file__).resolve().parent / 'src'
    if str(_ROOT) not in _sys.path:
        _sys.path.insert(0, str(_ROOT))
    try:
        from hermes_collab_engine.agents import list_backends
    except Exception as e:
        print(f'  ⚠ 无法加载 agent 列表 ({e})，使用默认 {prev or "claude-code"}')
        return prev or 'claude-code'

    backends = list_backends()
    if not backends:
        return prev or 'claude-code'

    print('\n── 选择 Worker Agent 后端 ──')
    print('  Worker 节点调用哪个 CLI 来执行编码任务：')
    default_idx = 1
    for i, b in enumerate(backends, 1):
        mounted = '✓ 已挂载' if b.is_available() else '✗ 未挂载'
        marker = ' (上次)' if b.name == prev else ''
        print(f'  {i}. {b.display_name} [{b.name}]  {mounted}{marker}')
        if b.name == prev:
            default_idx = i
    print('  提示：未挂载的选项 CLI 不在 PATH，引擎会报错；可继续配置但需先安装。')

    while True:
        raw = input(f'请选择编号 [默认 {default_idx}]: ').strip()
        if not raw:
            return backends[default_idx - 1].name
        try:
            idx = int(raw)
            if 1 <= idx <= len(backends):
                return backends[idx - 1].name
        except ValueError:
            pass
        print('输入无效，请重新选择。')


def choose_interaction_mode():
    choice = choose(
        '选择操作方式',
        [
            'Web 面板操作（使用浏览器中的任务输入窗口，推荐）',
            'Hermes 命令行操作（进入终端交互）',
        ],
        1,
    )
    return 'cli' if 'Hermes 命令行' in choice else 'web'


# ── Config selection ───────────────────────────────────────────────────

def get_config_from_hermes():
    """Auto-detect from ~/.hermes/ — merge .env + config.yaml for best result."""
    env_cfg = read_hermes_env()
    yaml_cfg = read_hermes_config_yaml()
    auth_cfg = read_hermes_auth()

    # Collect all unique sources found
    found = [c for c in (env_cfg, yaml_cfg, auth_cfg) if c]
    if not found:
        return None

    # Merge: prefer .env for secrets, config.yaml for models
    base_url = None
    token = None
    models = None
    default_leader = None
    default_worker = None
    source_parts = []

    for cfg in found:
        if cfg.get('base_url') and not base_url:
            base_url = cfg['base_url']
        if cfg.get('token') and not token:
            token = cfg['token']
        if cfg.get('models') and not models:
            models = cfg['models']
        if cfg.get('default_leader') and not default_leader:
            default_leader = cfg['default_leader']
        if cfg.get('default_worker') and not default_worker:
            default_worker = cfg['default_worker']
        source_parts.append(cfg['source'])

    if not base_url or not token:
        return None

    return {
        'source': ' + '.join(source_parts),
        'source_path': found[0].get('source_path', ''),
        'base_url': base_url,
        'token': token,
        'models': models or DEFAULT_MODELS,
        'default_leader': default_leader,
        'default_worker': default_worker,
    }


def get_config_manual():
    print('\n手动填写 API 配置')
    base_url = prompt('BaseURL，例如 https://api.example.com/anthropic')
    token = prompt('API Key / Auth Token')
    raw_models = prompt('可用模型名称，多个用英文逗号分隔', ','.join(DEFAULT_MODELS[:3]))
    models = unique([x.strip() for x in raw_models.split(',')])
    if not base_url or not token or not models:
        raise SystemExit('手动配置不完整。')
    return {
        'source': '手动输入', 'source_path': '',
        'base_url': base_url, 'token': token,
        'models': models,
        'default_leader': models[0],
        'default_worker': models[min(1, len(models) - 1)],
    }


# ── Main ───────────────────────────────────────────────────────────────

# ── Agent config registry ──────────────────────────────────────────────
# Each agent registers how its config files should be synced.
# To add a new agent, append an entry to AGENT_CONFIG_REGISTRY.
# Format: (name, config_path_builder, sync_function)
#   config_path_builder(leader, worker) -> Path | None
#   sync_function(path, leader, worker) -> None (writes config)

def _sync_hermes_env(path: Path, leader: dict, worker: dict) -> None:
    """Sync ~/.hermes/.env — key=value format.

    Safety invariants:
      1. Never overwrite a non-empty API key with a masked placeholder
         (``***`` or all-asterisks). If the existing .env already holds a
         real key, we keep it unless the caller passed a *new* non-masked
         value for the same role.
      2. Never write an empty/masked value into a previously-empty key
         silently — that would let a polluted runtime config wipe the
         user's credentials. We bail with a loud error instead.
    """
    import re as _re
    if path.exists():
        lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    else:
        lines = ['# Hermes Agent secrets\n']

    def _is_masked(v: str) -> bool:
        if not v:
            return False
        if v == '*' * len(v):
            return True
        if len(v) <= 16 and '...' in v:
            return True
        return False

    # Read existing values once so we can guard against clobbering real keys.
    existing = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        k, v = stripped.split('=', 1)
        existing[k.strip()] = v.strip()

    def _resolve(key: str, new_val: str) -> str:
        """Return the value to actually write, applying safety rules."""
        cur = existing.get(key, '')
        # Rule A: refuse to write a masked value on top of a real key.
        if _is_masked(new_val) and cur and not _is_masked(cur):
            print(f'  · 保留 {key}（已存在真值，拒绝用占位符覆盖）')
            return cur
        # Rule B: refuse to wipe a real key with an empty value (would lock
        # the user out of their engine with no recovery hint).
        if not new_val and cur and not _is_masked(cur):
            print(f'  · 保留 {key}（已存在真值，跳过清空）')
            return cur
        return new_val or cur

    ocg_base = leader['base_url'].rstrip('/') + '/v1'
    updates = {
        'ANTHROPIC_API_KEY':     _resolve('ANTHROPIC_API_KEY',     leader['api_key']),
        'ANTHROPIC_BASE_URL':    _resolve('ANTHROPIC_BASE_URL',    leader['base_url']),
        'OPENCODE_GO_API_KEY':   _resolve('OPENCODE_GO_API_KEY',   leader['api_key']),
        'OPENCODE_GO_BASE_URL':  _resolve('OPENCODE_GO_BASE_URL',  ocg_base),
    }
    for key, val in updates.items():
        pattern = _re.compile(rf'^{key}=.*$')
        found = False
        for i, line in enumerate(lines):
            if pattern.match(line.strip()):
                lines[i] = f'{key}={val}\n'
                found = True
                break
        if not found:
            lines.append(f'{key}={val}\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(lines), encoding='utf-8')
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f'  ✓ 已同步 → {path}')


def _sync_claude_settings(path: Path, leader: dict, worker: dict) -> None:
    """Sync ~/.claude/settings.json — JSON format with env block."""
    if path.exists():
        try:
            settings = load_json_lenient(path)
        except Exception:
            settings = {}
    else:
        settings = {}
    env_block = settings.setdefault('env', {})
    env_block['ANTHROPIC_AUTH_TOKEN'] = leader['api_key']
    env_block['ANTHROPIC_API_KEY'] = leader['api_key']
    env_block['ANTHROPIC_BASE_URL'] = leader['base_url']
    if leader.get('model'):
        env_block['ANTHROPIC_DEFAULT_OPUS_MODEL'] = leader['model']
        env_block['ANTHROPIC_DEFAULT_OPUS_MODEL_NAME'] = leader['model']
    if worker.get('model'):
        env_block['ANTHROPIC_DEFAULT_SONNET_MODEL'] = worker['model']
        env_block['ANTHROPIC_DEFAULT_SONNET_MODEL_NAME'] = worker['model']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f'  ✓ 已同步 → {path}')


def _sync_hermes_config_yaml(path: Path, leader: dict, worker: dict) -> None:
    if not path.exists():
        return
    new_model = (leader.get('model') or '').strip()
    if '/' in new_model:
        new_model = new_model.rsplit('/', 1)[-1]
    if not new_model:
        return
    text = path.read_text(encoding='utf-8')
    updated = re.sub(
        r'^(\s*default:\s*).*',
        rf'\1{new_model}',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if updated != text:
        path.write_text(updated, encoding='utf-8')
        print(f'  ✓ 已同步 model.default → {new_model} → {path}')


# Agent config registry: (name, path_builder, sync_fn)
# path_builder receives (leader, worker) and returns the config file Path or None.
# To add a new agent, append a tuple here.
AGENT_CONFIG_REGISTRY = [
    ('hermes',    lambda l, w: HERMES_DIR / '.env',       _sync_hermes_env),
    ('hermes-yaml', lambda l, w: HERMES_DIR / 'config.yaml', _sync_hermes_config_yaml),
    ('claude',    lambda l, w: CLAUDE_DIR / 'settings.json', _sync_claude_settings),
]


def sync_agent_configs(leader: dict, worker: dict) -> None:
    """Write leader config back to all registered agent config files.

    Iterates AGENT_CONFIG_REGISTRY — each agent defines its own config path
    and sync function. To add a new agent, append to AGENT_CONFIG_REGISTRY.
    """
    for name, path_builder, sync_fn in AGENT_CONFIG_REGISTRY:
        config_path = path_builder(leader, worker)
        if config_path is None:
            continue
        try:
            sync_fn(config_path, leader, worker)
        except Exception as e:
            print(f'  ⚠ {name} 配置同步失败: {e}')


def stop_existing_server():
    """Stop any previous engine server so the new one can bind the port.

    Replaces the prior `pkill -f 'src.hermes_collab_engine.cli server'`, which
    had two failure modes that would let a new opc launch die with EADDRINUSE
    while the user only saw `Address already in use` in server.log:

      1. **Stopped (T) processes** — pkill sends SIGTERM by default, but a
         SIGSTOPed / SIGTSTOPed / kernel-paused process queues SIGTERM
         without running its handler. pkill then returns rc=1 ("no signal
         delivered") and the port-holder lives on. Real-world triggers:
         Ctrl-Z in a debug session, container freezer (cgroup `FROZEN`),
         gdb attaching with `stop()`. We saw this exact failure on the
         8765 listener (pid 41051, state Tl, wchan=do_signal_stop).

      2. **Matching** — `pkill -f` matches against the process *command
         line*; an engine spawned via `python3 -m src.hermes_collab_engine.cli
         server` happens to include the substring, but a process that was
         started via `hermes-collab server ...` (the canonical entrypoint)
         does NOT include the substring. Fix: use `pgrep -f` to *find* the
         pids, then signal each pid explicitly so we control the order
         (CONT → TERM → KILL) and don't depend on pkill's matching quirks.

    Order of operations per matching pid:
        SIGCONT  — wake any stopped process so it can receive the next signal
        SIGTERM  — ask politely, give it 2 s to exit and release the port
        SIGKILL  — last resort if SIGTERM didn't take effect
    """
    import signal as _sig

    pattern = 'src.hermes_collab_engine.cli server'
    try:
        result = subprocess.run(
            ['pgrep', '-f', pattern],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        # pgrep missing on PATH — fall back to the old pkill behavior so we
        # at least attempt the cleanup rather than silently leaking the port.
        subprocess.run(['pkill', '-f', pattern],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    pids = [int(line) for line in result.stdout.split() if line.strip().isdigit()]
    if not pids:
        return

    for pid in pids:
        try:
            # Wake first so the next signal can be processed promptly even
            # if the process is currently in T (stopped) state.
            os.kill(pid, _sig.SIGCONT)
        except ProcessLookupError:
            continue
        except PermissionError:
            # Another user's process — skip rather than crashing opc.
            continue
        except OSError:
            continue

    # SIGTERM pass — covers the common case (engine received the signal,
    # runs its atexit handler, closes the listening socket).
    for pid in pids:
        try:
            os.kill(pid, _sig.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        alive = [pid for pid in pids
                 if _pid_alive(pid)]
        if not alive:
            break
        time.sleep(0.1)

    # SIGKILL sweep for any stragglers (defunct-but-port-holding, kernel
    # freezer refusing SIGTERM, etc.). The port must be free for the new
    # server to bind.
    for pid in pids:
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, _sig.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    # Give the kernel a moment to actually release the socket.
    time.sleep(0.2)


def _pid_alive(pid: int) -> bool:
    """Return True iff `pid` is still running (any state except gone)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by someone else — treat as alive for cleanup.
        return True
    return True


# -- Proxy lifecycle (Go binary from proxy/ directory / Python fallback) --

_ADAPTERS_NEED_PROXY = {'claude-code', 'codex', 'hermes'}

def _start_proxy(upstream_token: str, upstream_base_url: str = ''):
    proxy_path = PROXY_BINARY
    if not proxy_path.exists():
        print(f'  ⚠ Go 代理二进制不存在: {proxy_path}')
        print(f'  尝试使用 Python 代理 (proxy.py) ...')
        return _start_python_proxy(upstream_token, upstream_base_url)
    proxy_env = os.environ.copy()
    proxy_env['OPCODE_UPSTREAM_TOKEN'] = upstream_token
    if upstream_base_url:
        proxy_env['OPCODE_UPSTREAM_BASE'] = upstream_base_url
    proxy_env['OPCODE_LISTEN'] = f':{PROXY_PORT}'
    proxy_log = ROOT / 'data' / 'proxy.log'
    proxy_log.parent.mkdir(parents=True, exist_ok=True)
    pf = proxy_log.open('a', encoding='utf-8', buffering=1)
    proc = subprocess.Popen([str(proxy_path)], env=proxy_env, stdout=pf, stderr=subprocess.STDOUT)
    time.sleep(0.5)
    if proc.poll() is not None:
        print(f'  ⚠ Go 代理启动失败，请查看日志: {proxy_log}')
        print(f'  尝试使用 Python 代理 (proxy.py) ...')
        pf.close()
        return _start_python_proxy(upstream_token, upstream_base_url)
    print(f'  ✓ Go 协议代理已启动 → http://127.0.0.1:{PROXY_PORT}')
    return (proc, pf)


def _start_python_proxy(upstream_token: str, upstream_base_url: str = '') -> tuple | None:
    proxy_py = ROOT / 'proxy.py'
    if not proxy_py.exists():
        print(f'  ⚠ Python 代理脚本不存在: {proxy_py}')
        return None
    proxy_env = os.environ.copy()
    proxy_env['PROXY_API_KEY'] = upstream_token
    if upstream_base_url:
        proxy_env['PROXY_TARGET'] = upstream_base_url.rstrip('/') + '/v1'
    proxy_env['PROXY_PORT'] = str(PROXY_PORT)
    proxy_env['PROXY_CONFIG'] = str(RUNTIME_CONFIG_PATH)
    proxy_log = ROOT / 'data' / 'proxy.log'
    proxy_log.parent.mkdir(parents=True, exist_ok=True)
    pf = proxy_log.open('a', encoding='utf-8', buffering=1)
    proc = subprocess.Popen(
        [sys.executable, str(proxy_py)],
        env=proxy_env, stdout=pf, stderr=subprocess.STDOUT,
    )
    time.sleep(0.5)
    if proc.poll() is not None:
        print(f'  ⚠ Python 代理启动失败，请查看日志: {proxy_log}')
        pf.close()
        return None
    print(f'  ✓ Python 协议代理已启动 → http://127.0.0.1:{PROXY_PORT}')
    return (proc, pf)


def _stop_process(proc, log_file):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_file.close()


def main():
    import sys as _sys
    _quick = '--quick' in _sys.argv or '-q' in _sys.argv

    print_banner()

    enforce_path_consistency()
    _warn_if_masked_env()

    prev_runtime = load_previous_runtime()
    prev_leader = prev_runtime.get('leader', {})
    prev_worker = prev_runtime.get('worker', {})

    if not prev_leader and prev_runtime.get('base_url'):
        prev_leader = {
            'base_url': prev_runtime.get('base_url', ''),
            'api_key':  prev_runtime.get('api_key', ''),
            'model':    prev_runtime.get('leader_model', ''),
        }
    if not prev_worker and prev_runtime.get('base_url'):
        prev_worker = {
            'base_url': prev_runtime.get('base_url', ''),
            'api_key':  prev_runtime.get('api_key', ''),
            'model':    prev_runtime.get('worker_model', ''),
        }

    runtime_exists = bool(prev_runtime.get('leader') and prev_runtime['leader'].get('api_key'))

    if _quick and runtime_exists:
        leader = prev_runtime['leader']
        worker = prev_runtime.get('worker', leader)
        worker_agent = prev_runtime.get('worker_agent', 'opencode')
        host = prev_runtime.get('host', '0.0.0.0')
        port = prev_runtime.get('port', 8765)
        cwd = prev_runtime.get('cwd', str(Path.home()))
        runtime = prev_runtime
        print('使用已有配置，快速启动...\n')
    else:
        worker_agent = choose_worker_agent(prev_runtime.get('worker_agent', '') or 'claude-code')
        schema = ADAPTER_FIELD_SCHEMA.get(worker_agent, ADAPTER_FIELD_SCHEMA['claude-code'])
        leader = ask_agent_config('Leader Agent（规划/聚合大脑）', prev_leader, schema=schema)
        worker = ask_agent_config('Worker Agent（执行器大脑）',  prev_worker, schema=schema)
        host = prompt('管理面板监听地址', prev_runtime.get('host') or '0.0.0.0')
        port = prompt('管理面板监听端口', str(prev_runtime.get('port') or '8765'))
        cwd  = prompt('协同任务默认工作目录', prev_runtime.get('cwd') or str(Path.home()))
        runtime = {
            'config_source': 'manual (single config)',
            'leader': leader, 'worker': worker, 'worker_agent': worker_agent,
            'base_url': leader['base_url'], 'leader_model': leader['model'],
            'worker_model': worker['model'], 'host': host, 'port': int(port), 'cwd': cwd,
            'providers': [{
                'name': 'default', 'protocol': 'anthropic',
                'base_url': leader['base_url'], 'api_key': leader['api_key'],
                'default_model': leader['model'],
            }],
            'active_provider': 'default', 'fallback_chain': ['default'],
        }
        RUNTIME_CONFIG_PATH.write_text(
            json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            os.chmod(RUNTIME_CONFIG_PATH, 0o600)
        except OSError:
            pass
        try:
            from hermes_collab_engine.config_store import save_with_backup as _save_with_backup
            _backup = _save_with_backup(RUNTIME_CONFIG_PATH, runtime)
            if _backup:
                print(f'已备份旧 runtime 配置: {_backup}')
        except Exception as _e:
            print(f'⚠ config_store.save_with_backup 不可用, 保持原样: {_e}')

    sync_agent_configs(leader, worker)

    # ── Provider prefix for OpenCode ──────────────────────────────────
    # OpenCode requires the model flag to carry a provider prefix (e.g.
    # "opencode-go/deepseek-v4-flash") so it knows which backend to use.
    # If the agent is opencode, automatically prepend the prefix unless
    # the model already carries one.  This mirrors how opencode-go's own
    # proxy layer handles protocol forwarding automatically.
    MODEL_PREFIX_OPENCODE = "opencode-go/"
    if worker_agent == "opencode":
        if not leader['model'].startswith(MODEL_PREFIX_OPENCODE):
            leader_model_explicit = MODEL_PREFIX_OPENCODE + leader['model']
        else:
            leader_model_explicit = leader['model']
        if not worker['model'].startswith(MODEL_PREFIX_OPENCODE):
            worker_model_explicit = MODEL_PREFIX_OPENCODE + worker['model']
        else:
            worker_model_explicit = worker['model']
    else:
        leader_model_explicit = leader['model']
        worker_model_explicit = worker['model']

    proxy_proc = None
    proxy_log_file = None
    if worker_agent in _ADAPTERS_NEED_PROXY:
        proxy_result = _start_proxy(worker['api_key'], worker.get('base_url', ''))
        if proxy_result is not None:
            proxy_proc, proxy_log_file = proxy_result
            worker['base_url'] = f'http://127.0.0.1:{PROXY_PORT}'
            print(f'  Worker BaseURL 已重定向至协议代理 → {worker["base_url"]}')

    run_env = os.environ.copy()
    run_env['ANTHROPIC_AUTH_TOKEN']    = leader['api_key']
    run_env['ANTHROPIC_API_KEY']       = leader['api_key']
    run_env['ANTHROPIC_BASE_URL']      = leader['base_url']
    run_env['ANTHROPIC_MODEL']         = leader_model_explicit
    run_env['OPENCODE_GO_API_KEY']     = leader['api_key']
    run_env['OPENCODE_GO_BASE_URL']    = leader['base_url'].rstrip('/') + '/v1'
    run_env['HERMES_COLLAB_LEADER_MODEL']    = leader_model_explicit
    run_env['HERMES_COLLAB_LEADER_BASE_URL'] = leader['base_url']
    run_env['HERMES_COLLAB_LEADER_API_KEY']  = leader['api_key']
    run_env['HERMES_COLLAB_WORKER_MODEL']    = worker_model_explicit
    run_env['HERMES_COLLAB_WORKER_BASE_URL'] = worker['base_url']
    run_env['HERMES_COLLAB_WORKER_API_KEY']  = worker['api_key']
    run_env['HERMES_COLLAB_WORKER_AGENT']    = worker_agent
    # 2026-06-16: Cap global opencode worker concurrency to prevent 4-run storm
    # from leaking lsp-daemon children on 4GB boxes. The server itself doesn't
    # spawn workers, but run() invocations (CLI subprocesses from web UI) will
    # inherit this env via engine.__init__ fallback. Default 4 is safe.
    # Override via OPERATION_GLOBAL_MAX_CONCURRENT env (passed straight through).
    try:
        opc_global_max = max(1, int(os.environ.get('OPERATION_GLOBAL_MAX_CONCURRENT', '4')))
    except (TypeError, ValueError):
        opc_global_max = 4
    run_env['HERMES_COLLAB_GLOBAL_MAX_CONCURRENT'] = str(opc_global_max)

    server_cmd = [
        str(ROOT / 'hermes-collab'), 'server', '--host', host, '--port', str(port),
        '--cwd', cwd, '--db', str(ROOT / 'data' / 'collab.sqlite3'),
        '--leader-model', leader_model_explicit, '--worker-model', worker_model_explicit,
        '--agent', worker_agent,
    ]

    # Print summary (mask api keys).
    print('启动配置：')
    safe_runtime = json.loads(json.dumps(runtime, ensure_ascii=False))
    for role in ('leader', 'worker'):
        if isinstance(safe_runtime.get(role), dict) and 'api_key' in safe_runtime[role]:
            safe_runtime[role]['api_key'] = _mask(safe_runtime[role]['api_key'])
    print(json.dumps(safe_runtime, ensure_ascii=False, indent=2))

    leader_model = leader['model']  # alias used below

    print('\n正在启动协同引擎管理面板...')
    stop_existing_server()
    log_path = ROOT / 'data' / 'server.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # buffering=1 = line-buffered so a crashing engine's traceback shows up
    # in server.log immediately, not after opc exits and flushes the file.
    # Before this, ops would see "Traceback (most recent call last):" with
    # no body — the actual frames were stuck in the open()'s 8KB buffer.
    log_file = log_path.open('a', encoding='utf-8', buffering=1)
    server = subprocess.Popen(server_cmd, env=run_env, cwd=ROOT,
                              stdout=log_file, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    if server.poll() is not None:
        print(f'管理面板启动失败，请查看日志：{log_path}')
        return 1

    # Post-start health probe: run `hermes-collab doctor` against the
    # runtime config so the operator can see masked keys, backup count,
    # and provider health before they start submitting tasks.
    try:
        from hermes_collab_engine.cli import main as _cli_main
        import sys as _sys
        _saved = list(_sys.argv)
        try:
            _sys.argv = ['hermes-collab', 'doctor', '--config', str(RUNTIME_CONFIG_PATH)]
            _rc = _cli_main()
            if _rc != 0:
                print(f'⚠ doctor 子命令返回 {_rc} — 详见上面输出')
        finally:
            _sys.argv = _saved
    except SystemExit as _se:
        # argparse uses SystemExit(2) for usage errors; we want to keep going
        # even if doctor failed, since the dashboard itself is already up.
        print(f'⚠ doctor 退出: code={_se.code}')
    except Exception as _e:  # pragma: no cover - best-effort
        print(f'⚠ doctor 调用失败: {_e}')

    display_host = host if host != '0.0.0.0' else '服务器IP'
    print(f'管理面板已启动：http://{display_host}:{port}')
    print(f'服务日志：{log_path}')

    if _quick:
        interaction_mode = 'web'
    else:
        interaction_mode = choose_interaction_mode()
    hermes_cmd = ['hermes']

    try:
        if interaction_mode == 'web':
            print('\n已选择 Web 面板操作。')
            print(f'请在浏览器打开：http://{display_host}:{port}')
            print('你可以直接在面板中的任务输入窗口提交协同任务。')
            print('按 Ctrl-C 退出时，本启动脚本会停止本次启动的管理面板。\n')
            while True:
                time.sleep(60)
        print('\n正在进入 Hermes 命令行...')
        print('退出 Hermes 后，本启动脚本会停止本次启动的管理面板。\n')
        if os.environ.get('OPC_SKIP_HERMES') == '1':
            print('OPC_SKIP_HERMES=1，跳过进入 Hermes（用于测试启动脚本）。')
            while True:
                time.sleep(60)
        subprocess.run(hermes_cmd, env=run_env, cwd=cwd)
    except KeyboardInterrupt:
        pass
    finally:
        print('\n正在停止协同引擎管理面板...')
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        log_file.close()
        if proxy_proc:
            print('正在停止协议代理...')
            _stop_process(proxy_proc, proxy_log_file)
        print('已退出。')
    return 0


if __name__ == '__main__':
    import sys as _sys
    if len(_sys.argv) >= 3 and _sys.argv[1] == 'add-agent':
        _sys.path.insert(0, str(ROOT / 'src'))
        _saved = list(_sys.argv)
        _sys.argv = [_sys.argv[0]] + _sys.argv[2:]
        from hermes_collab_engine.add_agent import main as _add_main
        raise SystemExit(_add_main())
    raise SystemExit(main())
