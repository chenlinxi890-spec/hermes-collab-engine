# API 参考

## Runs

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/overview` | 总览 |
| GET | `/api/runs` | 运行列表 |
| GET | `/api/runs/:id` | 运行详情 |
| POST | `/api/runs` | 提交任务 |

## 注册表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/lessons` | 经验总结 |
| GET | `/api/agents` | Agent 列表 |
| GET | `/api/skills` | Skill 列表 |
| GET | `/api/tools` | 工具列表 |

## 日志&事件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs` | 最近日志 |
| SSE | `/api/events` | 实时事件流 |

> 返回格式为 JSON。详细字段说明见 `hermes-collab server --help`。
