# 经验总结（Distill）

引擎每日自动总结 lessons 经验到 MEMORY.md。

## 数据流

```
_learn() → lessons 表 (L1/L2/L3)
    ↓ 每日 23:59 (cron)
daily_distill.py
    ↓ 去重 + 提炼
MEMORY.md 条目
```

## Lesson 级别

| 级别 | 范围 | 说明 |
|------|------|------|
| L1 | 近期 | 现场日志，30 天后清理 |
| L2 | 永久 | 可复用的经验教训，有根因和修复方案 |
| L3 | 永久 | 模式变化，对比前后行为差异 |

L1→L2 晋升条件：同类失败 ≥2 次 + 有明确根因 + 可操作修复方案。

## 查看 lessons

```bash
hermes-collab lessons                   # 全部
hermes-collab lessons --scope L2        # 仅 L2
hermes-collab lessons --limit 20        # 最近 20 条
hermes-collab add-lesson --category timeout --lesson "..." # 手动添加
```

## 每日总结

cron 定时任务每晚 23:59 运行：

```
59 23 * * * cd /root/hermes-collab-engine/src && python3 -m \
  hermes_collab_engine.distill.daily_distill >> /var/log/hermes-distill.log 2>&1
```

自动回填：如果前一天总结缺失，第二天运行时自动补上。

## 数据存储

- Lessons 表：`data/collab.sqlite3.lessons`
- 每日归档：`data/memory/daily-YYYY-MM-DD.json`
- MEMORY.md：`~/.hermes/memories/MEMORY.md`
