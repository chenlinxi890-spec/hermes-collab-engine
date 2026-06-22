# CLI 命令参考

## hermes-collab run — 运行任务

```bash
# 基本用法
hermes-collab run "分析当前项目结构" --cwd .
hermes-collab run "实现用户登录功能" --cwd /path/to/project

# 从文件读取任务描述
hermes-collab run --request-file task.md --cwd .

# 指定工作线程数
hermes-collab run "重构模块" --cwd . --concurrency 4

# JSON 格式输出（适合程序消费）
hermes-collab run "检查代码规范" --cwd . --json

# 指定 Agent（覆盖默认）
hermes-collab run "分析" --cwd . --agent hermes
hermes-collab run "实现" --cwd . --agent opencode
```

### 常用选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--cwd` | 当前目录 | 工作目录 |
| `--concurrency` | 2 | 并行 Worker 数 |
| `--timeout` | 86400 | 任务超时（秒） |
| `--agent` | opencode | Agent 后端 |
| `--model` | — | 模型名（同时覆盖 leader 和 worker） |
| `--leader-model` | — | Leader 模型 |
| `--worker-model` | — | Worker 模型 |
| `--json` | false | JSON 格式输出 |

## hermes-collab server — 启动面板

```bash
# 默认启动
hermes-collab server --cwd .

# 指定监听地址和端口
hermes-collab server --host 0.0.0.0 --port 8765 --cwd .

# 指定模型
hermes-collab server --cwd . --leader-model gpt-4 --worker-model gpt-3.5
```

面板提供实时流水线视图、Worker 状态、日志和模型管理。

## hermes-collab skills — 技能管理

```bash
hermes-collab skills                    # 列出全部技能
hermes-collab skills --node-type implementation  # 按节点类型筛选
hermes-collab tools                     # 列出全部工具
```

## hermes-collab agents — Agent 管理

```bash
hermes-collab agents                    # 已注册的 Agent
hermes-collab agents --available        # 系统 PATH 上可用的
```

## hermes-collab lessons — 经验管理

```bash
hermes-collab lessons                   # 列出经验
hermes-collab lessons --scope L2        # 按级别筛选
hermes-collab lessons --limit 20        # 限制数量
hermes-collab add-lesson --category timeout --lesson "描述"
```

## 运行中干预

```bash
hermes-collab kill-node <run_id> <node_id>   # 终止节点
hermes-collab split-node <run_id> <node_id>  # 拆分节点
hermes-collab skip-node <run_id> <node_id>   # 跳过节点
hermes-collab redo-node <run_id> <node_id>   # 重做节点
hermes-collab log <run_id> <node_id> "msg"   # 写入日志
```

## opc — 启动器

```bash
opc                     # 交互式配置并启动
opc -q                  # 使用上次配置快速启动
opc add-agent <name>    # 动态注册 Agent
```

## 环境变量

```bash
HERMES_COLLAB_MODEL=model-name           # 全局模型
HERMES_COLLAB_LEADER_MODEL=model-name    # Leader 模型
HERMES_COLLAB_WORKER_MODEL=model-name    # Worker 模型
HERMES_COLLAB_LEADER_API_KEY=***         # API Key
HERMES_COLLAB_WORKER_API_KEY=***         # Worker API Key
```
