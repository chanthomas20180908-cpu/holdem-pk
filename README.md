# holdem-pk

由 CLI Agent 主持的六人终端德扑框架。Python 是规则裁判，Codex 是主持人和五名对手；没有模型 API 层，没有嵌套 CLI 调用，没有第三方依赖。

## 在 Codex 中玩

使用 Python 3.10+，在此目录启动 Codex，说：

> 读取 AGENTS.md，开始六人德扑。

Codex 按协议调用 `python3 -m holdem`，展示文本牌桌，轮到你时等待输入。关闭会话后可从本地存档恢复。本阶段只验证 Python 工具；Codex 实际交互仍需试玩验收。

## 文件

- `AGENTS.md`：Agent 对战、主持、工具使用协议。
- `holdem/__main__.py`：牌型比较、下注状态机、边池结算、CLI 与本地 JSON 存档。
- `tests/test_game.py`：规则与完整对局验证。
- `.holdem/`：运行时私有存档，不提交。

运行 `python3 -m unittest discover -s tests -v` 验证。`python3 -m holdem --help` 查看工具入口。

## 高级终端牌桌

默认 `python3 -m holdem table` 保持原来的纯文本输出。可在真实终端中启用彩色牌桌：

```bash
python3 -m holdem table --style rich
python3 -m holdem table --style rich --width 120
python3 -m holdem table --style rich --color never
```

高级模式使用独立玩家面板、四色花色、行动者高亮及公共牌区域。120 列以上的六人桌采用环桌布局；80–119 列采用两列面板；40–79 列采用单列面板。完整行动记录和结算保留在下方。此模式只使用标准库，无需安装 Rich。

`--color auto|always|never` 默认 auto：仅真实终端自动启用颜色，遵守 `NO_COLOR` 和 `TERM=dumb`；always 可显式覆盖。`--width` 最小 40；自动检测不足 40 列时回退纯文本。`--seat` 和全局 `--state` 仍可使用。

高级牌桌是一次性只读快照，不会自动刷新或执行动作。聊天代码块不保证呈现 ANSI 颜色，Agent 默认仍展示纯文本；在终端重跑命令可查看最新牌局。隔离工作树默认使用各自的 `.holdem/state.json`，查看其他目录的牌局需明确指定 `--state`。

MVP 为你加五名角色对手，固定 5/10 盲注、1000 起始筹码，支持弃牌、过牌、跟注、加注与全押。按钮轮转，破产玩家坐出，存档存在时 new 拒绝覆盖。需要独立新场次时，在另一个工作目录通过 PYTHONPATH 指向本仓库运行工具。

重要边界：同一个 Agent 看过多个视角，无法严格隔离底牌；这版用于验证可玩闭环。多个不足额全押的累积重开加注尚不支持。当前没有常驻 TUI，牌桌由 Agent 在终端排版；暂未提供 Claude Code 专用入口或验收。后续优先根据试玩修正规则与交互，再考虑独立角色上下文和专门 TUI。

## 文本牌桌与行动记录

`python3 -m holdem table` 只读展示当前用户牌桌，包括位置、状态、剩余筹码、本轮下注、本手投入，以及按阶段分组的完整行动过程。`view` 仍返回 JSON，供 Agent 决策；工具不调用模型。牌面统一为 `10 ♣ / A ♥`。

新手牌记录盲注、行动实际投入和下注总额、行动后底池、公共牌、轮次结束、退款与结算。结束后显示本手与累计盈亏、主池和边池。旧存档可直接恢复，但历史事件与盈亏基线缺失时显示不完整或未知，不回填推测记录；下一手开始完整记录。

可用全局参数 `--state /绝对路径/state.json` 指定已有存档，例如在隔离 worktree 中查看主目录存档；`table` 为只读操作。

旧四人存档在本手结束后运行 `python3 -m holdem expand`，保留原筹码，新增指南针与闪电各买入 1000，然后 `next` 开始六人牌局；进行中的手牌拒绝扩桌。
