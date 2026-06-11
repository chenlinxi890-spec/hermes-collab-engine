#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLAUDE_DIR = Path('/root/.claude')


def load_json_lenient(path: Path):
    text = path.read_text(encoding='utf-8')
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(text)


def collect_profiles():
    profiles = []
    settings = CLAUDE_DIR / 'settings.json'
    if settings.exists():
        profiles.append({'name': '当前 Claude Code 配置', 'path': str(settings), 'data': load_json_lenient(settings)})
    for p in sorted((CLAUDE_DIR / 'profiles').glob('*.json')):
        try:
            profiles.append({'name': p.stem, 'path': str(p), 'data': load_json_lenient(p)})
        except Exception as e:
            print(f'跳过无法读取的配置 {p}: {e}')
    return profiles


def models_from(profile):
    data = profile['data']
    env = data.get('env', {})
    models = []
    for key in ['ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL']:
        if env.get(key):
            models.append(env[key])
    for m in data.get('availableModels') or []:
        if m:
            models.append(m)
    dedup = []
    for m in models:
        if m not in dedup:
            dedup.append(m)
    return dedup


def choose(label, items, default=1):
    print(f'\n{label}')
    for i, item in enumerate(items, 1):
        print(f'  {i}. {item}')
    raw = input(f'请选择编号 [默认 {default}]: ').strip()
    idx = default if not raw else int(raw)
    if idx < 1 or idx > len(items):
        raise SystemExit('选择超出范围')
    return items[idx - 1]


def stop_existing_server():
    subprocess.run(
        ['pkill', '-f', 'src.hermes_collab_engine.cli server'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    profiles = collect_profiles()
    if not profiles:
        raise SystemExit('没有找到 /root/.claude/settings.json 或 profiles/*.json')

    profile_labels = []
    for p in profiles:
        env = p['data'].get('env', {})
        profile_labels.append(f"{p['name']} | {env.get('ANTHROPIC_BASE_URL','无 BaseURL')} | 模型数 {len(models_from(p))}")
    chosen_label = choose('选择 API 配置来源', profile_labels)
    profile = profiles[profile_labels.index(chosen_label)]
    env = profile['data'].get('env', {})
    models = models_from(profile)
    if not models:
        raise SystemExit('选中的配置没有可用模型列表')

    opus = env.get('ANTHROPIC_DEFAULT_OPUS_MODEL')
    sonnet = env.get('ANTHROPIC_DEFAULT_SONNET_MODEL')
    default_leader = models.index(opus) + 1 if opus in models else 1
    default_worker = models.index(sonnet) + 1 if sonnet in models else min(2, len(models))

    leader_model = choose('选择 Leader Agent（Hermes 命令行 / 规划与聚合大脑）模型', models, default_leader)
    worker_model = choose('选择 Worker Agent（Claude Code 执行器大脑）模型', models, default_worker)

    host = input('\n管理面板监听地址 [默认 0.0.0.0]: ').strip() or '0.0.0.0'
    port = input('管理面板监听端口 [默认 8765]: ').strip() or '8765'
    cwd = input('协同任务默认工作目录 [默认 /root]: ').strip() or '/root'

    token = env.get('ANTHROPIC_AUTH_TOKEN') or env.get('ANTHROPIC_API_KEY')
    base_url = env.get('ANTHROPIC_BASE_URL')
    if not token or not base_url:
        raise SystemExit('选中的配置缺少 ANTHROPIC_AUTH_TOKEN/ANTHROPIC_API_KEY 或 ANTHROPIC_BASE_URL')

    runtime = {
        'profile': profile['name'],
        'profile_path': profile['path'],
        'base_url': base_url,
        'leader_model': leader_model,
        'worker_model': worker_model,
        'host': host,
        'port': int(port),
        'cwd': cwd,
    }
    (ROOT / '.runtime-config.json').write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')

    run_env = os.environ.copy()
    run_env['ANTHROPIC_AUTH_TOKEN'] = token
    run_env['ANTHROPIC_API_KEY'] = token
    run_env['ANTHROPIC_BASE_URL'] = base_url
    run_env['ANTHROPIC_MODEL'] = leader_model
    run_env['HERMES_COLLAB_LEADER_MODEL'] = leader_model
    run_env['HERMES_COLLAB_WORKER_MODEL'] = worker_model

    server_cmd = [
        str(ROOT / 'hermes-collab'), 'server',
        '--host', host,
        '--port', str(port),
        '--cwd', cwd,
        '--db', str(ROOT / 'data' / 'collab.sqlite3'),
        '--leader-model', leader_model,
        '--worker-model', worker_model,
    ]

    print('\n启动配置：')
    print(json.dumps(runtime, ensure_ascii=False, indent=2))

    print('\n正在启动协同引擎管理面板...')
    stop_existing_server()
    log_path = ROOT / 'data' / 'server.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open('a', encoding='utf-8')
    server = subprocess.Popen(server_cmd, env=run_env, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    if server.poll() is not None:
        print(f'管理面板启动失败，请查看日志：{log_path}')
        return 1

    display_host = host if host != '0.0.0.0' else '服务器IP'
    print(f'管理面板已启动：http://{display_host}:{port}')
    print(f'服务日志：{log_path}')

    hermes_cmd = ['hermes', '--provider', 'anthropic', '--model', leader_model]
    print('\n正在进入 Hermes 命令行...')
    print('退出 Hermes 后，本启动脚本会停止本次启动的管理面板。\n')

    if os.environ.get('OPC_SKIP_HERMES') == '1':
        print('OPC_SKIP_HERMES=1，跳过进入 Hermes（用于测试启动脚本）。')
        print('按 Ctrl+C 或结束进程后会停止面板。')
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass
    else:
        subprocess.run(hermes_cmd, env=run_env, cwd=cwd)

    print('\n正在停止协同引擎管理面板...')
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
    log_file.close()
    print('已退出。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
