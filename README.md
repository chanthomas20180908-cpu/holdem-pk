# holdem-pk

由 CLI Agent 主持的四人终端德扑框架。Python 是规则裁判，Codex 是主持人和三名对手；没有模型 API 层，没有嵌套 CLI 调用，没有第三方依赖。

## 在 Codex 中玩

使用 Python 3.10+，在此目录启动 Codex，说：

> 读取 AGENTS.md，开始四人德扑。

Codex 按协议调用 `python3 -m holdem`，展示文本牌桌，轮到你时等待输入。关闭会话后可从本地存档恢复。本阶段只验证 Python 工具；Codex 实际交互仍需试玩验收。

## 文件

- `AGENTS.md`：Agent 对战、主持、工具使用协议。
- `holdem/__main__.py`：牌型比较、下注状态机、边池结算、CLI 与本地 JSON 存档。
- `tests/test_game.py`：规则与完整对局验证。
- `.holdem/`：运行时私有存档，不提交。

运行 `python3 -m unittest discover -s tests -v` 验证。`python3 -m holdem --help` 查看工具入口。

MVP 为你加三名角色对手，固定 5/10 盲注、1000 起始筹码，支持弃牌、过牌、跟注、加注与全押。按钮轮转，破产玩家坐出，存档存在时 new 拒绝覆盖。需要独立新场次时，在另一个工作目录通过 PYTHONPATH 指向本仓库运行工具。

重要边界：同一个 Agent 看过多个视角，无法严格隔离底牌；这版用于验证可玩闭环。多个不足额全押的累积重开加注尚不支持。当前没有常驻 TUI，牌桌由 Agent 在终端排版；暂未提供 Claude Code 专用入口或验收。后续优先根据试玩修正规则与交互，再考虑独立角色上下文和专门 TUI。
