# API 参考

引擎提供 HTTP REST API 和 SSE 事件流。

## 基础信息

- **基础 URL:** `http://localhost:8765`
- **响应格式:** JSON
- **认证:** 无（本地服务，建议通过反向代理添加）

## Runs — 任务运行

### GET /api/overview

总览数据：运行统计、活动 Worker、最近教训。

```bash
curl http://localhost:8765/api/overview
```

### GET /api/runs

运行记录列表，按时间倒序。

```bash
curl http://localhost:8765/api/runs
```

### GET /api/runs/:id

运行详情。包含节点、Worker、日志、模型信息。

```bash
curl http://localhost:8765/api/runs/run_xxx
curl http://localhost:8765/api/runs/run_xxx?full=1  # 完整详情
```

### POST /api/runs

提交新任务。

```bash
curl -X POST http://localhost:8765/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"request":"分析项目结构并输出报告"}'
```

返回：
```json
{"accepted": true, "mode": "leader", "package": null}
```

## 注册表

### GET /api/lessons

经验教训列表。

```bash
curl http://localhost:8765/api/lessons
curl 'http://localhost:8765/api/lessons?scope=L2'
curl 'http://localhost:8765/api/lessons?limit=50'
```

### GET /api/agents

已注册的 Agent Backend 列表。

```bash
curl http://localhost:8765/api/agents
curl 'http://localhost:8765/api/agents?available=1'
```

### GET /api/skills

技能注册表。支持按节点类型和任务描述筛选。

```bash
curl http://localhost:8765/api/skills
curl 'http://localhost:8765/api/skills?node_type=implementation'
curl 'http://localhost:8765/api/skills?task=search'
```

### GET /api/tools

工具配置列表。

```bash
curl http://localhost:8765/api/tools
curl 'http://localhost:8765/api/tools?node_type=implementation'
```

## 日志 & 事件

### GET /api/logs

最近日志，按时间倒序。

```bash
curl http://localhost:8765/api/logs
curl 'http://localhost:8765/api/logs?limit=100'
```

### SSE /api/events

实时事件流，用于面板实时刷新。

```bash
curl -N http://localhost:8765/api/events
```

## 返回值格式

所有端点返回 JSON。成功时 HTTP 200，错误时返回对应状态码：

```json
{"error": "not found"}
```

常见状态码：
- `200` — 成功
- `404` — 资源不存在
- `500` — 服务端错误
