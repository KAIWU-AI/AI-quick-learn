# AI Quick Learn：高质量开源贡献技能

这套中文 Skill 帮助 Coding Agent 从知名项目和 GitHub Issue 中寻找真实问题，完成复现、最小修复、测试、查重和 Pull Request 发布。

它由两部分组成：

- `SKILL.md`：约束 Agent 按证据执行完整贡献流程；
- `contribution_radar.py`：只读访问 GitHub，先检测当前机器的系统与工具链，再扫描本机可验证的仓库、Issue 线索和重复工作；`scan` 会在本地生成报告，并只推荐 1 个优先深挖机会。

脚本不会自动 fork、push、评论或创建 PR。所有公开操作都必须在确认项目政策、问题可复现、没有重复工作、测试通过并得到用户授权之后进行，避免给维护者制造垃圾 PR。

## 安装

需要 Python 3.9+、Git 和 [GitHub CLI](https://cli.github.com/)。Linux/macOS 以下示例使用 `python3`；Windows 请替换为 `py -3`。先执行：

```bash
gh auth login
gh auth status
```

### Hermes Agent

```bash
python3 install.py --agent hermes
```

### Claude Code

个人技能目录遵循 [Claude Code Skills 文档](https://docs.anthropic.com/en/docs/claude-code/skills)：

```bash
python3 install.py --agent claude
```

### Codex

个人技能目录遵循 [Codex Skills 文档](https://developers.openai.com/codex/build-skills)：

```bash
python3 install.py --agent codex
```

### 自定义目录

```bash
python3 install.py --agent custom --target /path/to/skills
```

更新已有安装时使用 `--force`。安装器会先备份旧目录，不会直接删除；完成后会打印安装目录和一条可直接运行的 `doctor` 验证命令。

安装后新建 Agent 会话，然后发送：

> 请使用 open-source-pr-contributor 技能，先检查环境并扫描适合我的开源贡献候选。只选择能够在当前机器复现、没有重复 PR、符合项目贡献政策的问题。完成最小修复和测试后，创建一个 PR，并回读 PR 的 head SHA、文件列表和 CI 状态。

## 快速验证

```bash
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py doctor
python3 -m unittest discover -s skills/open-source-pr-contributor/tests -v
python3 -m unittest discover -s tests -v
```

扫描最多 12 个**与本机配置匹配**的候选仓库，每个仓库保留 5 个 Issue 线索：

```bash
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py scan --max-repos 12 --max-issues 5 --output contribution-report.json --markdown contribution-report.md
```

默认不覆盖已有报告；确认更新时添加 `--force`。扫描器会检测 macOS/Linux/Windows、CPU 架构以及 Git、Python、Node、pnpm、uv、jq 等本机命令，先排除缺少必需工具或平台不兼容的仓库，再按准备成本、难度和 Issue 质量排序。报告顶部只给出 1 个 `needs_verification` 候选；它仍需阅读完整讨论、查重并在最新默认分支复现，不能直接当成可提交 PR。

Agent 接下来必须从这个待验证线索开始，逐个核对真实测试命令、工具版本、平台/硬件/服务要求、Issue 全部讨论、当前默认分支和重复工作，并实际运行最小复现。只有通过这些检查的一个候选才能称为“已选贡献机会”；当前代码已经修复、已有活跃实现或本机无法验证时，必须淘汰并继续下一名。全部失败时输出 0 个机会，不为满足数量硬选。

任一仓库读取失败时，脚本会保留成功结果和错误明细，但以非零状态退出，避免自动化把不完整扫描当成成功。扫描同时读取 Issue 关联 PR；已有实现中的 Issue 不会进入唯一推荐。除常用标签外，还会从近期无标签 Issue 中识别带有 crash、fail、incorrect、missing 等可复现症状的候选。

只看 Python 项目：

```bash
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py scan --language Python --max-repos 20
```

检查单个项目：

```bash
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py inspect modelcontextprotocol/python-sdk --max-issues 10
```

搜索潜在重复项：

```bash
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py duplicates OWNER/REPO "exact error or affected_symbol"
```

查重词只接受普通错误摘要、符号名或文件名；不要粘贴 Token、认证 URL，也不要加入 `repo:`、`is:`、`OR` 等 GitHub 查询操作符。

## 候选项目

初始池收敛为 22 个依赖相对可控的项目，默认优先扫描 8 个 Agent Skill 仓库：

- Agent Skill：`vercel-labs/skills`、`agentskills/agentskills`、`google/skills`、`huggingface/skills`、`addyosmani/agent-skills`、`antfu/skills`、`BuilderIO/skills`、`cloudflare/skills`；
- Python/网络：`psf/requests`、`pallets/flask`、`Textualize/rich`、`fastapi/fastapi`；
- SDK/测试工具：`modelcontextprotocol/python-sdk`、`modelcontextprotocol/typescript-sdk`、`openai/openai-python`、`anthropics/anthropic-sdk-python`、`eslint/eslint`、`vitest-dev/vitest`；
- Agent/应用：`browser-use/video-use`、`THU-MAIC/OpenMAIC`、`browser-use/browser-use`、`NousResearch/hermes-agent`。

已移除默认池中的大型或重依赖目标，如 OpenClaw、Pydantic、Ruff、Pytest、LangChain、LlamaIndex、Transformers、Codex、Continue、Open WebUI、pnpm 与 Gitea。仍可通过自定义 `--seed` 扫描它们，但不会再挤占默认的轻量候选名额。

完整数据在 `skills/open-source-pr-contributor/references/repository-pool.json`。其中的 stars 有快照日期；扫描脚本会重新读取实时 stars、许可证、活跃时间和 Issue。

候选池只是入口，不是推荐名单。真正提交前必须通过六项门禁：

1. 项目有许可证、近期活跃且接受外部贡献；
2. 已阅读贡献指南、模板、安全政策和 AI 使用政策；
3. 问题能在最新默认分支复现；
4. 开放/关闭 Issue、PR 和最近提交中没有重复工作；
5. 当前机器的系统、架构和已安装命令满足仓库的 `setup` 元数据，且能运行聚焦测试；
6. 修改解决真实用户问题，而不是 typo、徽章或无关格式化。

## 如何找问题

优先检查：

- `good first issue`、`help wanted`、`bug`、`ready for work`；
- 最近更新但没有标签的 bug；
- 关闭但未修复的 Issue；
- 长期停滞或放弃的 PR；
- 反复出现的解析、状态、路径、编码、超时和平台兼容问题；
- 会让用户执行错误命令的安装、示例和文档。

标签不等于可做。Issue 可能已分配、已有 PR、已经在默认分支修复，或需要私有服务才能验证。

## 目录结构

```text
.
├── CONTRIBUTING.md
├── LICENSE
├── NOTICE.md
├── README.md
├── install.py
├── tests/
│   └── test_install.py
└── skills/
    └── open-source-pr-contributor/
        ├── SKILL.md
        ├── references/
        │   ├── pr-workflow.md
        │   └── repository-pool.json
        ├── scripts/
        │   └── contribution_radar.py
        └── tests/
            └── test_contribution_radar.py
```

## 安全边界

- 不读取或打印 GitHub Token；错误输出会清理常见凭据格式。
- 所有子命令对 GitHub 远端只读；`scan` 只在本地创建报告，默认拒绝覆盖已有文件和符号链接。
- API 失败或组织 SSO 阻断时尝试公开只读 API；仍失败则记录为未知，不伪装成 0。
- 不自动发布评论、Issue、PR，也不自动合并。
- 不处理必须接触真实凭据、生产系统、恶意载荷或用户数据的问题。

## License

MIT

## 来源与改编

本项目基于 Hermes Agent 随附的 MIT 许可技能进行中文重构：

- `open-source-repo-portfolio` v1.3.4
- `trending-open-source-contributor` v1.5.0

改编保留了候选发现、贡献政策、重复项搜索、RED→GREEN、独立审查和远端回读等核心门禁；删除了本机绝对路径、个人账号、定时任务、私有仪表盘和特定工作区状态，并增加了跨 Agent 安装器、公开候选池和无第三方依赖的只读扫描脚本。详见 [NOTICE.md](NOTICE.md)。
