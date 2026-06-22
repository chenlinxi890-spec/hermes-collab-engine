# 沙盒与隔离

## 沙盒模式

沙盒用于演示和测试，使用 mock API 和脱敏数据，**不调真实 worker、不写生产数据**。

```bash
# 一键启动（默认 2 小时，超时自动停止）
sandbox

# 自定义运行时间
sandbox 4               # 4 小时
sandbox 0.5             # 30 分钟
sandbox --hours 8       # 8 小时
sandbox --port 8877     # 自定义端口

# 真实 worker 执行
sandbox --real          # 启用真实 worker（需 API 额度）
sandbox --no-reseed     # 复用已有数据库
```

## Level 4 Jail 隔离

Worker 进程运行在隔离环境中，支持以下隔离级别：

| 隔离 | 说明 |
|------|------|
| Mount namespace | 独立的文件系统视图 |
| PID namespace | Worker 看不见宿主机进程 |
| User namespace | root 在 jail 内 ≠ 宿主机 root |
| Network | 可选网络隔离 |

### 暴露目录

Jail 内 worker 可访问的宿主机目录：

| 路径 | 权限 | 用途 |
|------|:----:|------|
| workspace (cwd) | rw | 项目文件 |
| ~/.cache/opencode | ro | 模型配置 |
| ~/.local/state/opencode | ro | 会话状态 |
| ~/.config/opencode | ro | API 密钥 |

### Aggregate 跳过 Jail

汇总报告节点（aggregate）不经过 jail，直接使用 Hermes Agent 执行。Worker 节点执行经过 jail。

## 构建 Jail 根文件系统

```bash
bash scripts/build-jail.sh
```

构建内容：
- bash、opencode 二进制
- 系统库（libtinfo、libc 等）
- /dev 设备节点（null、zero、random、urandom）
- DNS 配置（resolv.conf）
- /proc 挂载点

## 故障排查

```bash
# 检查 jail 是否可用
ls /var/hermes/jail/bin/opencode

# 检查沙盒状态
ps aux | grep sandbox

# 手动清理过期沙盒
rm -rf /var/hermes/sandbox/run_*
```
