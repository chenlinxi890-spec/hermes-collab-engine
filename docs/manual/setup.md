# 安装与配置

## 系统要求

- **Python** ≥ 3.11
- **Git**
- **curl**

### 必需 CLI 工具

| 工具 | 用途 | 安装方式 |
|------|------|---------|
| Hermes | Leader Agent | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash` |
| opencode | Worker Agent | `npm install -g opencode-ai` 或参考 [opencode.ai](https://opencode.ai) |

### 可选工具

| 工具 | 用途 |
|------|------|
| Go | 编译协议代理（提供高性能流式转发） |
| Node.js | puppeteer MCP 浏览器自动化 |
| claude-code | 可作为备选 Worker Agent |

## 一行安装

```bash
curl -fsSL https://raw.githubusercontent.com/lpc0387/hermes-collab-engine/main/scripts/install.sh | bash
```

脚本自动完成：
1. 检查依赖（python3、git、curl、hermes、opencode）
2. 克隆仓库到 `~/hermes-collab-engine`
3. 创建 Python 虚拟环境并安装包
4. 编译协议代理（如已安装 Go）
5. 创建 `hermes-collab` 和 `opc` 启动命令

## 手动安装

```bash
git clone https://github.com/lpc0387/hermes-collab-engine.git ~/hermes-collab-engine
cd ~/hermes-collab-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 环境变量配置

引擎通过环境变量配置模型和 API 密钥：

```bash
export HERMES_COLLAB_LEADER_MODEL=opencode-go/deepseek-v4-flash
export HERMES_COLLAB_LEADER_BASE_URL=https://opencode.ai/zen/go
export HERMES_COLLAB_LEADER_API_KEY=your-key-here
export HERMES_COLLAB_WORKER_MODEL=opencode-go/deepseek-v4-flash
export HERMES_COLLAB_WORKER_API_KEY=your-key-here
```

建议将配置写入 `.env` 文件，启动前 `source .env`。

## 验证安装

```bash
hermes-collab run "1+1=?" --cwd .
```
