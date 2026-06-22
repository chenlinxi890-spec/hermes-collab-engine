# Agent 管理

引擎支持多种 Agent Backend。Leader 使用 Hermes，Worker 默认使用 opencode。

## 内置 Agent

| Agent | 命令 | 角色 | 输出解析 | 需协议代理 |
|-------|------|------|---------|:---------:|
| hermes | `hermes -z` | Leader | text | |
| opencode | `opencode` | Worker | text | |
| claude-code | `claude -p` | Worker | session ID + text | ✓ |
| codex | `codex` | Worker | JSON | ✓ |
| openclaw | `openclaw --prompt` | Worker | text | |
| cursor | `cursor --prompt` | Worker | text | |

## 角色分配

v6.0 起引擎使用双 Agent 架构：

| 角色 | Agent | 职责 |
|------|-------|------|
| **Leader** | Hermes | WBS 分解、任务规划、结果聚合 |
| **Worker** | opencode | 执行具体任务节点 |
| **Aggregate** | Hermes | 汇总报告生成 |

## 动态注册 Agent

通过 `opc add-agent` 命令动态发现并注册自定义 Agent：

```bash
opc add-agent openclaw                    # 注册 OpenClaw Worker
opc add-agent cursor                      # 注册 Cursor Worker
opc add-agent copilot --hint "custom url" # 带提示注册
```

LLM 自动搜索 Agent 的 API 格式和安装方式，支持 npm/pip/cargo 包管理器兜底。

## 查看已注册 Agent

```bash
hermes-collab agents               # 全部已注册
hermes-collab agents --available   # 仅在 PATH 上的
```

## Leader 配置

Leader 使用 Hermes Agent，可通过以下方式配置：

```bash
# CLI 指定
hermes-collab run "任务" --cwd . --agent hermes

# 环境变量
export HERMES_COLLAB_LEADER_MODEL=opencode-go/deepseek-v4-flash
export HERMES_COLLAB_LEADER_BASE_URL=https://opencode.ai/zen/go
export HERMES_COLLAB_LEADER_API_KEY=***
```

Hermes Agent 的 skills（如 `engine-memory`）在 Leader 模式下自动加载，用于注入历史经验。
