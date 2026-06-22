# Skill 与 MCP 工具

## Skill 分发机制

SkillDistributor 根据节点能力自动匹配最优技能和 MCP 工具。

```
Planner 创建 WBS 节点
    → 节点 capability (analysis/implementation/design)
    → SkillDistributor 匹配 skill + MCP
    → 注入 worker prompt
```

当 Leader（Hermes）提交任务时，Hermes 的 skills 可用；Worker（opencode）执行时加载 engine 分配的 skills。

## 内置 Skill

| Skill | 适用节点 | 说明 |
|-------|---------|------|
| search-verify | analysis | 多源搜索 → 交叉验证 → 结构化摘要 |
| frontend-optimization | design | daisyUI/Tailwind/unocss 设计规范 |
| ui-design-v2 | design | shadcn/ui v4 高级审美 |
| file-edit | implementation | 文件读写编辑 |
| git-local | implementation | 本地 Git 状态检查 |
| python-tests | verification | Python 单元测试运行 |

## MCP 工具

MCP 服务器在 worker 启动时自动连接，worker 退出后自动销毁（懒加载模式）。

| 服务器 | 工具数 | 工具 |
|--------|:------:|------|
| ferris-search | 7 | GitHub/HN/文档/学术/StackOverflow 搜索 |
| baidu-search | 1 | 百度搜索引擎 |
| open-websearch | 2 | DuckDuckGo + 内容提取 |
| daisyui-blueprint | 1 | daisyUI 组件生成 |
| shadcn-ui | 4 | shadcn/ui 组件管理 |
| puppeteer | 7 | navigate/screenshot/click/fill/hover/evaluate |

### 浏览器自动化

puppeteer MCP 提供完整浏览器控制能力：

```bash
puppeteer_navigate(url)      # 导航到页面
puppeteer_screenshot()       # 截图
puppeteer_click(selector)    # 点击元素
puppeteer_fill(sel, text)    # 填写表单
puppeteer_hover(selector)    # 悬停
puppeteer_evaluate(js)       # 执行 JS
puppeteer_close()            # 关闭页面
```

## 查看技能和工具

```bash
hermes-collab skills                    # 所有技能
hermes-collab skills --node-type impl   # 按类型筛选
hermes-collab tools                     # 所有工具
```

## 技能市场（Dragon Team 平台）

Dragon Team 平台提供了技能市场和自定义技能创建功能，支持用户通过对话创建私有技能。
