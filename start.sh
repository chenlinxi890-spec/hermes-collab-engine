#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
opc - 启动 Hermes 协同引擎

用法:
  opc           启动（交互式配置）
  opc -q        快速启动（使用上次配置，跳过全部提示）
  opc --quick   同上
EOF
  exit 0
fi
cd /root/hermes-collab-engine
exec python3 start.py "$@"
