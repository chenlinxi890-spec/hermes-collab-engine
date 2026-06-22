# 常见问题

## 安装问题

### "hermes: not found"

Leader Agent 未安装。Hermes 是必需依赖：

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

### "opencode: not found"

Worker Agent 未安装：

```bash
npm install -g opencode-ai
```

或参考 [opencode.ai](https://opencode.ai) 获取其他安装方式。

### "command not found: hermes-collab"

安装脚本创建的启动命令不在 PATH 中。手动添加：

```bash
export PATH=$HOME/.local/bin:$PATH
```

## 运行问题

### "Invalid API key"

OpenCode API 密钥无效或缺失。检查 `.env` 或环境变量：

```bash
echo $HERMES_COLLAB_LEADER_API_KEY
echo $HERMES_COLLAB_WORKER_API_KEY
```

### "no such table: agents_profiles"

数据库缺少 agent 配置表。创建空表即可：

```bash
sqlite3 data/agents.db "CREATE TABLE IF NOT EXISTS agents_profiles (...)"
```

或删除 `data/agents.db` 让引擎自动创建。

### Worker 一直 pending

可能原因：
1. 并发上限已满（默认全局 4 个 worker）
2. opencode 二进制未安装或不在 PATH
3. API key 过期

检查 Worker 状态：

```bash
hermes-collab status
```

### 沙盒启动失败

确保沙盒目录和 jail 构建正常：

```bash
ls /var/hermes/jail/bin/opencode
bash scripts/build-jail.sh
```

## 代理问题

### 协议代理连接失败

Go 代理编译失败时自动降级到 Python 代理。手动检查：

```bash
# 启动 Python 代理
python3 proxy.py
```

## 数据库

### SQLite 锁定

引擎使用 SQLite 存储运行状态。极端情况下可能出现数据库锁定：

```bash
# 检查锁定状态
lsof data/collab.sqlite3

# 清理 WAL 文件
sqlite3 data/collab.sqlite3 "PRAGMA wal_checkpoint(TRUNCATE);"
```
