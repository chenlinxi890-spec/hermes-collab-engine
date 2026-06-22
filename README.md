# Hermes Collab Engine v6.0

**多智能体协同引擎** — Leader 拆解 WBS → Worker 并行执行 → 结果聚合。

[![English](https://img.shields.io/badge/English-README.en.md-blue)](README.en.md) [![Release v6.0](https://img.shields.io/badge/release-v6.0-blue)](CHANGELOG.md) [![Sandbox ready](https://img.shields.io/badge/sandbox-ready-success)](sandbox/README.md) [![License MIT](https://img.shields.io/badge/license-MIT-green)](#许可证) [![Security](https://img.shields.io/badge/security-policy-orange)](SECURITY.md)

多智能体编排引擎，支持 WBS 协同、并行 Worker、Skill/MCP 分发、Lessons 自学习。

> 📖 **[操作手册](docs/manual/)** · [`ROADMAP.md`](ROADMAP.md) · [`CHANGELOG.md`](CHANGELOG.md)

![像素协同工位仪表盘](docs/screenshots/dashboard.png)

![Hermes 协作流程演示](docs/demo/hermes-flow.svg)

## 发布与社区

如果这个项目对你有帮助，欢迎 star 关注。参与前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)，安全问题请走 [`SECURITY.md`](SECURITY.md)，路线图见 [`ROADMAP.md`](ROADMAP.md)，版本变化见 [`CHANGELOG.md`](CHANGELOG.md)。

## 一行部署

```bash
curl -fsSL https://raw.githubusercontent.com/lpc0387/hermes-collab-engine/main/scripts/install.sh | bash
```

安装后：

```bash
opc                  # 交互式配置并启动
hermes-collab run "分析项目结构" --cwd .   # 直接运行任务
hermes-collab server --host 0.0.0.0 --port 8765  # 启动 Web 面板
```

## 快速开始

```bash
pip install -e .
hermes-collab run "分析 src/ 结构" --cwd . --json
hermes-collab server --host 0.0.0.0 --port 8765 --cwd .
```

## 亮点

| 能力 | 发布说明 |
|---|---|
| WBS 协同 | Leader 评分、拆解、分发节点，Worker 按依赖并行执行 |
| Leader/Worker 双模型 | 启动时分别选择 Leader 模型与 Worker 模型，面板显示当前模型 |
| Leader=Hermes | 引擎领导者使用 Hermes Agent，加载 skills 做复杂决策 |
| 协议代理 | 内置 Go/Python 协议代理，自动翻译 Anthropic ↔ OpenAI 格式 |
| 真实沙盒执行 | 可在受限额度内启动真实 worker；默认 mock 演示 |
| 隔离 DB / workspace | 沙盒使用演示 SQLite；真实执行写入独立 workspace |
| TTL 清理 | 沙盒默认 2 小时，到期自动停止 |
| 轻量 API payload | 面板 API 返回必要字段，便于嵌入和代理转发 |
| Leader 反馈日记本 | 任务完成后弹出像素本子，支持复制/下载 Markdown |
| 一行 curl 部署 | 使用上方 `curl ... | bash` 即可安装 |

## v6.0 新增

> v6.0 — Leader=Hermes, Worker=OpenCode 双 Agent 架构

### Agent 分流
- **Leader=Hermes**：WBS 分解、aggregate 汇总均使用 Hermes Agent
- **Worker=OpenCode**：执行阶段使用 OpenCode，轻量高效
- **Planner 重构**：WBS 分解由 Hermes 完成，不再依赖 claude-code
- **prompt_flag 修正**：Hermes CLI 参数格式 `-z`，解决 invalid choice 错误

### 经验总结独立化
- 每日 lessons 自动归档到 `data/memory/`
- 回填前一天缺失的总结
- 无 Hermes 路径依赖，可拔插式记忆
- `engine-memory` skill：Hermes 端加载引擎 lessons

### 管理端 MCP 重构
- MCP 页面改为只读展示
- 后端新增 POST/DELETE/reload 端点
- Puppeteer MCP 浏览器自动化（7 个工具）

### Lesson 质量体系
- scope（L1/L2/L3）+ tags
- `_learn()` 增强：ARG_MAX、超时、慢 worker 检测
- `GET /api/lessons` + `GET /api/distill/daily/{date}`

## v5.6 已有功能

### 统一注册表 (UnifiedRegistry)
- Skill、Tool、MCP 统一管理，能力标签索引
- Web UI 注册 → 自动持久化，重启不丢失
- Leader 自动感知可用 skill/tool 并在 WBS 阶段预分配

### SkillDistributor 集中分发引擎
- **Skill/Tool/MCP 集中管理**：Planner 根据节点 capability 自动匹配最优 skill 和工具
- **搜索路由**：搜索/调查类请求 → analysis 节点 → `search-verify` skill
- **设计路由**：UI/设计类请求 → design → `frontend-optimization` skill
- **MCP 工具注入**：节点能力自动匹配 MCP 服务器
- **预算管理**：剩余预算 < 30s 自动跳过节点
- **subprocess 防挂死**：temp 文件替代 PIPE 捕获 stdout/stderr
- **运行状态修复**：去掉 planning 卡死状态

### MCP 工具集成
| 服务器 | 工具数 | 用途 |
|---|---|---|
| ferris-search | 7 工具 | GitHub / Hacker News / 文档 / 学术 / StackOverflow 聚合搜索 |
| baidu-search | 1 工具 | 百度搜索引擎 |
| open-websearch | 2 工具 | DuckDuckGo + Web 内容提取 |
| daisyui-blueprint | 1 工具 | daisyUI 组件 AI 生成 |
| shadcn-ui | 4 工具 | shadcn/ui v4 组件浏览/获取/块管理 |
| puppeteer | 7 工具 | 浏览器自动化（navigate/screenshot/click/fill/hover/evaluate/close） |

### Skill 系统
- **`search-verify`** skill：多源搜索 → 交叉验证 → 结构化摘要
- **`frontend-optimization`** skill：daisyUI/Tailwind/unocss 设计规范
- **`ui-design-v2`** skill：shadcn/ui v4 高级审美（Linear/Stripe/Vercel 风格）

### 资源驱动分片 & 负载感知 dispatch
- **分片策略重写**：基于任务估算量 + 系统负载 + WBS 最小颗粒度四级决策
- **负载感知 dispatch**：CPU > 85% 或 MEM > 90% 时暂停派发新 worker
- **ARG_MAX 防护**：prompt 拼装后 900KB 硬截断

### Agent 管理
- 内置 Agent（claude-code、hermes、codex、opencode）
- Web UI 注册自定义 Agent，严格验证（name/command/capabilities）

### 会话链
- 通过"接入上次会话"形成连续对话链
- 按 resume 链分组展示多个 run 的状态与进度

### Lessons 自学习系统
- 引擎自动记录运行经验并去重提炼
- 只读节点风险检测修复
- checkpoint 状态原子持久化

### 沙盒一键启动
```bash
sandbox              # 默认 2 小时，端口 8876
sandbox 4            # 运行 4 小时
sandbox --port 8877  # 自定义端口
```

## 架构

```
用户 → Leader (WBS 拆解) → Worker × N 并行 → 聚合 → 结果
                              │
                         Agent Backend
                    (Hermes Leader / OpenCode Worker)
                              │
                        MCP 工具池
                   (搜索/浏览器/UI 组件)
```

| 层 | 技术 |
|----|------|
| 引擎 | Python 标准库（零第三方依赖） |
| Leader | Hermes Agent（WBS 分解 + aggregate 汇总） |
| Worker | opencode（执行） |
| 面板 | 单 HTML 文件 (Alpine.js) |
| 数据库 | SQLite |
| 协议代理 | Go (默认) / Python (备用) |

## CLI

```bash
hermes-collab run "<task>" --cwd .          # 运行任务
hermes-collab run --request-file task.md    # 文件提交
hermes-collab server                        # 启动面板
hermes-collab lessons                       # 查看经验
hermes-collab skills                        # 查看技能
hermes-collab tools                         # 查看工具
hermes-collab agents                        # 查看 Agent
hermes-collab kill/split/skip/redo <run> <node>  # 运行中干预
```

> 完整 CLI 参考见 [`docs/manual/cli.md`](docs/manual/cli.md)

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/overview` | 总览数据 |
| GET | `/api/runs` | 运行记录 |
| GET | `/api/runs/:id` | 运行详情 |
| GET | `/api/logs` | 最近日志 |
| GET | `/api/lessons` | 自学习经验 |
| GET | `/api/agents` | Agent Backend |
| GET | `/api/skills` | Skill 注册表 |
| GET | `/api/tools` | Tool 配置 |
| POST | `/api/runs` | 提交任务 |
| SSE | `/api/events` | 实时事件流 |

> 完整 API 文档见 [`docs/manual/api.md`](docs/manual/api.md)

## 联系与支持

WeChat: `lg19961117`

<details>
<summary>可选赞助支持维护</summary>

<img src="docs/assets/money.png" alt="赞助二维码" width="260">

</details>

---

**License:** MIT · 多智能体 · AI编排 · WBS · Agentic AI

> **GitHub Topics 推荐:** `multi-agent`, `claude-code`, `ai-orchestration`, `wbs`, `llm`, `agentic-ai`
