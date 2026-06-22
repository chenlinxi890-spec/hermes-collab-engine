# CLI 命令参考

## 运行任务

```
hermes-collab run "<task>" --cwd .          # 直接运行
hermes-collab run --request-file task.md    # 文件提交
hermes-collab run --agent hermes            # 指定 Agent
```

## 启动面板

```
hermes-collab server --host 0.0.0.0 --port 8765 --cwd .
```

## 查看注册表

```
hermes-collab skills       # 技能列表
hermes-collab tools        # 工具列表
hermes-collab agents       # Agent 列表
hermes-collab lessons      # 经验总结
```

## 运行中干预

```
hermes-collab kill-node <run_id> <node_id>
hermes-collab split-node <run_id> <node_id>
hermes-collab skip-node <run_id> <node_id>
hermes-collab redo-node <run_id> <node_id>
```

> 完整命令参考: `hermes-collab --help`
