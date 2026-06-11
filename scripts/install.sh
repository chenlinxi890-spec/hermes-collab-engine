#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/hermes-collab-engine}"
REPO_URL="${REPO_URL:-https://github.com/lpc0387/hermes-collab-engine.git}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "缺少依赖: $1" >&2; return 1; }
}

echo "==> 检查基础依赖"
need_cmd git
need_cmd python3
need_cmd bash

if ! command -v claude >/dev/null 2>&1; then
  echo "未找到 Claude Code CLI: claude"
  echo "请先安装并登录 Claude Code，然后重新运行本脚本。"
  echo "参考: https://docs.anthropic.com/en/docs/claude-code"
  exit 1
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "未找到官方 Hermes Agent: hermes"
  echo "将尝试安装官方 NousResearch Hermes Agent。"
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
fi

mkdir -p "$BIN_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "==> 更新已有仓库: $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "==> 克隆仓库: $REPO_URL -> $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

chmod +x "$INSTALL_DIR/hermes-collab" "$INSTALL_DIR/start.sh" "$INSTALL_DIR/start.py"
ln -sf "$INSTALL_DIR/hermes-collab" "$BIN_DIR/hermes-collab"
ln -sf "$INSTALL_DIR/start.sh" "$BIN_DIR/opc"

mkdir -p "$INSTALL_DIR/data"

echo "==> 安装完成"
echo "命令:"
echo "  opc                  # 选择模型并启动面板，然后进入 Hermes 命令行"
echo "  hermes-collab --help # 查看协同引擎 CLI"
echo ""
echo "如果 $BIN_DIR 不在 PATH 中，请执行:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
