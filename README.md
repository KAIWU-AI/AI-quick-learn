# AI Quick Learn：AI 基础 Demo 与开源贡献技能

先用三个 Python Demo 看懂模型调用、对话记忆和 Agent Loop，再使用开源贡献 Skill 完成真实项目实践。

## 三个 AI 基础 Demo

| 顺序 | 入口 | 本课新增概念 |
|---|---|---|
| 1 | [`demo1`](demo1/README.md) | 分别直接调用大语言模型和 JEV，以可展开的 JSON 树、图表和字段解读观察两边输入与返回 |
| 2 | [`demo2`](demo2/README.md) | 保存并回传历史，通过可回放的时间线与历史快照观察多轮对话记忆；没有工具 |
| 3 | [`demo3`](demo3/README.md) | 模型选择多个工具，用流程图、逐步回放与调用/结果配对观察完整 Agent Loop |

大语言模型使用 OpenAI Python SDK，JEV 使用 Python 标准库直接发 HTTP 请求；不依赖 Agent 框架、Node、Docker 或数据库。共用的 `demo_support.py` 只处理认证和错误显示；对话历史与 Agent Loop 都直接写在各课的 `__main__.py` 中。

### 准备 Python 环境

Demo 需要 Python 3.10+（当前 OpenAI SDK 的最低要求；开源贡献 Skill 仍支持 Python 3.9+）。在仓库根目录运行，Windows PowerShell：

```powershell
py -3 -m venv .venv-demos
.\.venv-demos\Scripts\python.exe -m pip install -r requirements-demos.txt
Copy-Item .env.example .env
```

macOS/Linux：

```bash
python3 -m venv .venv-demos
.venv-demos/bin/python -m pip install -r requirements-demos.txt
cp .env.example .env
```

`.env.example` 只有占位配置；复制后编辑 `.env`，不要提交真实端点、密钥或调用报告。已有进程环境变量优先于 `.env`。若已有 `.env`，请保留并按示例补充字段，不要直接覆盖。

### Azure CLI 认证

先运行 `az login`，并确认所选账号拥有目标模型的数据面调用权限（如 `Cognitive Services OpenAI User`）。订阅读取权限不等于模型调用权限，不需要在示例中保存 Access Token。

在 `.env` 中配置：

```dotenv
OPENAI_AUTH=azure-cli
OPENAI_BASE_URL=https://YOUR_RESOURCE.openai.azure.com/openai/v1/
OPENAI_MODEL=YOUR_DEPLOYMENT_NAME
AZURE_TOKEN_SCOPE=https://ai.azure.com/.default
```

`OPENAI_MODEL` 填 Azure 部署名，例如已部署的 `gpt-6-luna`。API 地址也支持资源提供的 `cognitiveservices.azure.com` 域名，但必须使用 `/openai/v1/` 路径，不追加旧式 `api-version`。使用 `AzureCliCredential` 和可刷新的 token provider，不把一次性的 Token 当作固定 API Key。

如果现有部署要求旧 token audience，可将 `AZURE_TOKEN_SCOPE` 设置为 `https://cognitiveservices.azure.com/.default`。程序不会切换订阅、修改权限或自动创建模型部署。

### OpenAI 或 Azure API Key 认证

改为 `OPENAI_AUTH=api-key` 并设置 `OPENAI_API_KEY`。OpenAI 公共服务使用 `https://api.openai.com/v1/` 和支持 Responses 的模型名；Azure 保留资源的 `/openai/v1/` 地址与部署名。配置示例也在 [`.env.example`](.env.example) 中。

### 依次运行

Demo 1 还需要 JEV 配置：在本地 `.env` 设置 `JEV_AUTH=api-key`、`JEV_API_KEY` 和 `JEV_MODEL=jev-latest`；已有 Windows 凭据时可改用 `JEV_AUTH=windows-credential`，并设置 `JEV_CREDENTIAL_TARGET=TypeSafe/Jev/APIKey`。`.env.example` 只保留占位符，真实密钥不进入版本控制。JEV 的专用 API 不能用作 `OPENAI_BASE_URL`。

Windows PowerShell：

```powershell
.\.venv-demos\Scripts\python.exe -m demo1
.\.venv-demos\Scripts\python.exe -m demo2
.\.venv-demos\Scripts\python.exe -m demo2 --interactive
.\.venv-demos\Scripts\python.exe -m demo3
```

macOS/Linux 将解释器换为 `.venv-demos/bin/python`；激活虚拟环境后，各平台都可使用 `python -m demo1` 等命令。

Demo 1 自动生成 `demo1/result.html`，直接用浏览器打开即可并排查看大语言模型和 JEV：共享输入、答案摘要、状态、token 用量、可展开的请求/返回树以及字段解读；JEV 还展示分类概率。无需启动服务器。若一边失败，页面标明错误并保留另一边的真实结果，进程返回非零状态。Demo 2 默认演示三轮，也可交互聊天，用 `/reset` 清空历史、`/exit` 退出。Demo 3 默认展示列课程、查详情和求总时长的工具协作；工具都是只读的虚构教学数据，不执行任意 shell。

Demo 2、3 分别生成 `demo2/result.html`、`demo3/result.html`：整体调用流程图、逐轮摘要、可播放/暂停的事件时间线、完整请求/返回 JSON 树、历史增长以及工具 `call_id` 配对跳转。支持 `--output` 自定义位置；每步更新报告，运行中刷新浏览器查看新增事件。页面可离线打开，回放不会再次调用 API；失败和次数上限保留部分轨迹且明确标错。观测逻辑位于 `demo_visualizer/`，不接管各课的历史或循环逻辑。

真实调用可能计费。每次请求有输出 token 上限、60 秒超时且不自动重试；对话和 Agent Loop 都有请求次数预算。`store=False` 表示由本地维护上下文，不代表服务商完全没有日志或数据保留。不要输入真实个人信息、秘密或私人代码。

### 教学来源与本地验证

教学节奏参考 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)：先解释一个限制，再引入一个机制，展示可运行代码，观察调用轨迹，最后做一个小改动。本项目是独立编写的 OpenAI Responses 示例，不是前三章的逐章翻译。

这里的 Demo 3 对应其 [`s01_agent_loop.py`](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/agents/s01_agent_loop.py) 的核心循环，并加入多工具分发；Demo 1、2 是为初学者增加的前置阶梯。原项目使用 Anthropic 协议和 Bash；本项目改用 Responses 的 `function_call` / `function_call_output`、严格参数校验及跨平台只读工具，不要求复制原项目的 shell 权限。来源与许可证说明见 [NOTICE.md](NOTICE.md)。

不调用 API 的回归测试：

```powershell
.\.venv-demos\Scripts\python.exe -m unittest discover -s demo_tests -v
```

测试覆盖历史回传与清空、完整 reasoning 项保存、批量工具调用与 `call_id` 配对、错误和次数上限、认证配置及可视化 HTML 的文本转义。离线测试不等于模型联网实测。

## 多 Agent 高质量开源贡献技能

这套中文 Skill 帮助 Coding Agent 从知名项目和 GitHub Issue 中寻找真实问题，完成复现、最小修复、测试、查重和 Pull Request 发布。

它由两部分组成：

- `SKILL.md`：主 Agent 筛选仓库，子 Agent 各自负责调研、复现、修复和测试；独立验证后由主 Agent 按授权发布一个或多个真实 PR；
- `contribution_radar.py`：只读访问 GitHub，先检测当前机器的系统与工具链，再扫描本机可验证的仓库、Issue 线索和重复工作；`scan` 会在本地生成报告，并只推荐 1 个优先深挖机会。

脚本不会自动 fork、push、评论或创建 PR。所有公开操作都必须在确认项目政策、问题可复现、没有重复工作、测试通过并得到用户授权之后进行，避免给维护者制造垃圾 PR。

### 多 Agent 与兼容性

v0.7.1 采用“主 Agent 初筛 → 各子 Agent 独立负责仓库 → 验证后逐个发布”的流程，目标是交付至少一个真实上游 PR，多个合格机会可以分别提交。负责人先读仓库指令、相关技能、Issue 和同类历史 PR，再复现、修复、测试，交回冻结补丁、证据及 PR 草稿，不能停在调研建议。主 Agent 安排独立验证并处理发布授权；一个仓库受阻时继续其他路径或从候补队列补位。本轮所有子 Agent 都无合格结果时，由主 Agent 评估后决定是否转向 HydraLab 兜底。

默认最多两个子 Agent 同时运行，包含实现和验证任务。每个负责人有独立的目标仓库工作区；主 Agent 不把不同仓库的修改混在一起。任务交接包含范围、停止条件、实际命令、退出码和证据位置；只有主 Agent 可以按用户授权进行公开写入。没有 PR 且仍有合格路径和预算时继续推进，零 PR 则明确报告未完成，不能把草稿当交付，也不保证上游合并。

运行时明确报告 `multi-agent`、`serial-subagent` 或 `single-agent`。不支持或不允许委派时保留串行流程，但不会声称做过独立 Agent 验证；上下文隔离也不等于文件系统隔离。没有独立工作区时，暂停修改再串行验证。

Agent Skills 标准定义技能文件格式，**没有统一的 sub-agent 通信协议**；调用遵循各宿主原生接口。Claude 的 `context: fork` 和 `isolation: worktree` 是平台扩展，不写死到通用入口。完整交接约定、隔离策略和官方依据见 [`multi-agent-workflow.md`](skills/open-source-contributor/references/multi-agent-workflow.md)。安装技能不等于启用宿主多 Agent 功能，也不需要额外安装 Agent 通信服务。

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

Windows 下打印的是 PowerShell 命令，支持带空格、中文或单引号的路径。

技能已从 `open-source-pr-contributor` 更名为 `open-source-contributor`。安装器只写入新名称目录，检测到旧目录时会提示但不会删除或覆盖它。新版本安装成功后，请把旧目录移到技能根目录之外，再新建会话，避免同时加载两个版本。`--force` 仅用于更新新名称目录。

安装后新建 Agent 会话，然后发送：

> 请使用 open-source-contributor 技能。由主 Agent 先筛选适合本机的仓库，再通过原生 sub-agent 工具让各负责人阅读技能、Issue 和历史 PR，分头复现、修复和测试，不支持时说明降级原因。只推进没有重复工作、符合项目政策且能实际验证的问题。独立验证后提交至少一个真实上游 PR；多个候选合格时可以分别提交。逐个回读 PR 的 URL、head SHA、文件列表和 CI 状态，不要只返回调研报告或 PR 草稿。

## 快速验证

```bash
python3 skills/open-source-contributor/scripts/contribution_radar.py doctor
python3 -m unittest discover -s skills/open-source-contributor/tests -v
python3 -m unittest discover -s tests -v
```

扫描最多 12 个**与本机配置匹配**的候选仓库，每个仓库保留 5 个 Issue 线索：

```bash
python3 skills/open-source-contributor/scripts/contribution_radar.py scan --max-repos 12 --max-issues 5 --output contribution-report.json --markdown contribution-report.md
```

默认不覆盖已有报告；确认更新时添加 `--force`。扫描器会检测 macOS/Linux/Windows、CPU 架构以及 Git、Python、Node、pnpm、uv、jq 等本机命令，先排除缺少必需工具或平台不兼容的仓库，再按准备成本、难度和 Issue 质量排序。报告顶部只给出 1 个 `needs_verification` 候选；它仍需阅读完整讨论、查重并在最新默认分支复现，不能直接当成可提交 PR。

### 课堂分流与多轮发现

默认保留 Agent Skill 优先级，并在同等适配、难度和类别优先级内随机打散扫描顺序。推荐时只在通过门禁、与最高分相差不超过 10 分的候选中选择，每个仓库一票，避免 Issue 多的项目挤占概率。每次产生新随机种子，不使用学员姓名、账号或机器标识；这只能降低碰撞，不能保证全班不重复。

JSON 的 `selection.random_seed` 与 Markdown 会记录种子，`attempted_repositories` 记录本轮尝试读取的仓库（包括读取失败项）。相同种子、候选数据和环境可复现选择；实时 GitHub 数据变化时不保证结果相同。

```bash
python3 skills/open-source-contributor/scripts/contribution_radar.py scan --random-seed 42 --output round1.json --markdown round1.md
python3 skills/open-source-contributor/scripts/contribution_radar.py scan --exclude-repo pallets/click --exclude-repo psf/requests --output round2.json --markdown round2.md
```

固定种子仅用于调试或复现，不要让全班照抄同一值。排除参数可重复指定，既可排除已充分检查的仓库，也可应用讲师的分配表。不要因为一个 Issue 不合适就排除整个项目；先用 `inspect --max-issues 20` 阅读其他线索。读取失败项仍是未知，不能当成已充分排查。

扫描没有推荐不等于没有机会：先检查错误、扩大 Issue 范围，关注无标签问题和技能安装/路径/索引/校验的真实行为。待本轮所有仓库负责人返回后，主 Agent 汇总证据；没有合格结果且没有仍在推进的可行任务时，可以选择继续换一批仓库，或读取 [`references/contribution-fallback.md`](skills/open-source-contributor/references/contribution-fallback.md) 转向 HydraLab。无需先遍历全部 30 个候选，也不强制多轮；记录切换依据，不能把未检查项或读取失败写成已排除。

教学完成目标是创建并回读真实上游 PR，不是仅输出报告。该引用指定 `microsoft/HydraLab` 为最后兜底，不放入默认候选池；它是 Java/Gradle 项目，不保证只用 Python 即可验证。权限、CLA、项目政策或验证阻塞必须明确报告“未完成”，不能为交作业硬发低质量 PR，也不保证上游接受或合并。

环境检测只是初筛：架构仅用于报告，工具版本、依赖 wheel、服务和硬件要求仍需逐项验证。`python3` 能力代表当前运行扫描器的 Python，不要求 PATH 中一定有同名命令。

主 Agent 接下来必须核对这些待验证线索的环境与政策，把适配仓库分给各负责人；单个推荐不是并行候选或 PR 数上限。各负责人逐项核对真实测试命令、工具版本、平台/硬件/服务要求、Issue 全部讨论、当前默认分支和重复工作，并实际运行最小复现。只有通过检查的候选才是“已选贡献机会”；当前代码已经修复、已有活跃实现或本机无法验证时，淘汰该问题并继续其他线索。当前批次全部失败则记录 0 个合格机会，由主 Agent 评估继续发现或转入 HydraLab；最终仍无可交付路径时如实报告未完成，不为满足数量硬选。

任一仓库读取失败时，脚本会保留成功结果和错误明细，但以非零状态退出，避免自动化把不完整扫描当成成功。REST 搜索返回 `incomplete_results` 时也按失败处理，不能当作查重通过。扫描同时读取 Issue 关联 PR；已分配或已有实现中的 Issue 会在截取候选名额前排除。除常用标签外，还会从近期无标签 Issue 中识别带有 crash、fail、incorrect、missing 等可复现症状的候选。

只看 Python 项目：

```bash
python3 skills/open-source-contributor/scripts/contribution_radar.py scan --language Python --max-repos 20
```

检查单个项目：

```bash
python3 skills/open-source-contributor/scripts/contribution_radar.py inspect modelcontextprotocol/python-sdk --max-issues 10
```

搜索潜在重复项：

```bash
python3 skills/open-source-contributor/scripts/contribution_radar.py duplicates OWNER/REPO "exact error or affected_symbol"
```

查重词只接受普通错误摘要、符号名或文件名；不要粘贴 Token、认证 URL，也不要加入 `repo:`、`is:`、`OR` 等 GitHub 查询操作符。

## 候选项目

候选池包含 30 个项目，保留原有 8 个 Agent Skill 仓库，并新增 6 个知名 Python 库。面向课堂优先选择无需部署服务即可验证的局部问题，而不是安装候选项目的完整生产环境：

- Agent Skill：`vercel-labs/skills`、`agentskills/agentskills`、`google/skills`、`huggingface/skills`、`addyosmani/agent-skills`、`antfu/skills`、`BuilderIO/skills`、`cloudflare/skills`；
- Python/网络：`psf/requests`、`pallets/flask`、`Textualize/rich`、`fastapi/fastapi`；
- CLI/数据校验：`pallets/click`、`python-jsonschema/jsonschema`；
- 新增轻量 Python：`urllib3/urllib3`、`python-attrs/attrs`、`marshmallow-code/marshmallow`、`jd/tenacity`、`Delgan/loguru`、`pyparsing/pyparsing`；
- SDK/测试工具：`modelcontextprotocol/python-sdk`、`modelcontextprotocol/typescript-sdk`、`openai/openai-python`、`anthropics/anthropic-sdk-python`、`eslint/eslint`、`vitest-dev/vitest`；
- Agent/应用：`browser-use/video-use`、`THU-MAIC/OpenMAIC`、`browser-use/browser-use`、`NousResearch/hermes-agent`。

已移除默认池中的大型或重依赖目标，如 OpenClaw、Pydantic、Ruff、Pytest、LangChain、LlamaIndex、Transformers、Codex、Continue、Open WebUI、pnpm 与 Gitea。仍可通过自定义 `--seed` 扫描它们，但不会再挤占默认的轻量候选名额。

新增的 [Click](https://github.com/pallets/click) 适合 CLI 参数、路径与终端行为修复；[jsonschema](https://github.com/python-jsonschema/jsonschema) 适合用小型 schema/instance 验证数据校验问题。2026-09-27 核对时，两者均未归档、有近期提交，许可证分别为 BSD-3-Clause 和 MIT；当前开发分支都要求 Python 3.10+。jsonschema 的 `rpds-py` 依赖需要兼容 wheel，否则可能需要 Rust 工具链。这里的入池核查不代表某个 Issue 已可贡献，也不替代最新贡献政策和 AI 使用规则检查。

新补充的 6 个 Python 项目已核对公开元数据与 `pyproject.toml`，均未归档且有近期活动；库逻辑可用 Python 环境与按项目声明安装的测试依赖验证，不等于零依赖。课堂建议准备 Python 3.11+ 和独立虚拟环境，实际版本仍以目标分支为准。优先考虑数据类、序列化、重试、日志和解析问题；urllib3 的完整网络/TLS 测试准备成本较高，标为 `moderate`，仅在能跑聚焦测试时选择。原有重依赖项目保留供环境匹配者探索，不要求学员为它们额外搭建服务。

完整数据在 `skills/open-source-contributor/references/repository-pool.json`。其中的 stars 有快照日期；扫描脚本会重新读取实时 stars、许可证、活跃时间和 Issue。

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
├── .env.example
├── requirements-demos.txt
├── demo_support.py
├── demo1/
├── demo2/
├── demo3/
├── demo_tests/
├── CONTRIBUTING.md
├── LICENSE
├── NOTICE.md
├── README.md
├── install.py
├── tests/
│   └── test_install.py
└── skills/
    └── open-source-contributor/
        ├── SKILL.md
        ├── references/
        │   ├── contribution-fallback.md
        │   ├── multi-agent-workflow.md
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
