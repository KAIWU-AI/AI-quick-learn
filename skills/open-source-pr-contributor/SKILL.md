---
name: open-source-pr-contributor
description: 用于结合本机环境发现、验证并提交一个真实的开源问题修复 PR.
version: 0.2.0
author: Bryan Nathan (hydraxman), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [github, open-source, pull-request, contribution]
    related_skills: []
---

# 高质量开源贡献

这个技能帮助 Coding Agent 从候选发现、问题复现、最小修复、测试验证一路走到 Pull Request。目标是完成一个维护者愿意审查的真实贡献，而不是为了数量制造 typo、格式化或重复 PR。

配套脚本 `scripts/contribution_radar.py` 对 GitHub 远端只读：它检测当前机器的系统、架构和工具链，优先扫描本机可验证的轻量项目，并从没有已关联 PR 的 Issue 中只推荐 1 个优先深挖机会。`scan` 只在本地生成报告。任何 fork、push、评论、Issue 或 PR 都必须在读完项目规则、确认问题可复现并完成测试之后进行。

## 适用场景

- 第一次尝试向 GitHub 开源项目贡献代码。
- 希望从知名项目、GitHub Trending 或 `good first issue` 中找到可执行的问题。
- 已有 Coding Agent，希望它按照一套可验证的流程完成一个 PR。
- 需要维护一个可持续扩展的候选仓库池。

不适合：批量刷 PR、无依据改文档、抢占已分配问题、绕过贡献政策，或需要凭据、付费服务、生产环境才能验证的修改。

## 前置条件

1. 安装 Git、Python 3.9+ 和 GitHub CLI（`gh`）。Linux/macOS 通常使用 `python3`，Windows 通常使用 `py -3`；下文以 `python3` 表示当前平台的 Python 3 启动命令。
2. 执行 `gh auth login`，并准备一个可 fork 公共仓库的 GitHub 账号。
3. 使用 `git config user.name` 与 `git config user.email` 检查当前生效的仓库级或全局提交身份；缺失时再按个人情况配置。
4. 确保网络能够访问 GitHub。
5. 不把 Token、Cookie、私钥或 `.env` 内容放进日志、Issue、PR 或仓库。

`<skill-dir>` 指安装后包含本文件的目录；安装器会输出可直接复制的完整验证命令。先运行：

```bash
python3 <skill-dir>/scripts/contribution_radar.py doctor
```

只有当 `ok` 为 `true` 时才继续。脚本不会读取或打印 GitHub Token。

## 候选仓库池

`references/repository-pool.json` 提供一个可扩展的初始池，重点覆盖依赖轻、可离线或用 fixture 验证的 Agent Skill、Python 库、SDK 和测试工具。每项都声明 `setup.level`、`required_commands` 和 `platforms`。代表项目包括：

- Agent Skill：`vercel-labs/skills`、`agentskills/agentskills`、`google/skills`、`huggingface/skills`、`addyosmani/agent-skills`、`antfu/skills`、`BuilderIO/skills`、`cloudflare/skills`；
- AI Agent：`NousResearch/hermes-agent`、`browser-use/browser-use`；
- MCP：`modelcontextprotocol/python-sdk`、`modelcontextprotocol/typescript-sdk`；
- Python 与 Web：`fastapi/fastapi`、`psf/requests`、`pallets/flask`、`Textualize/rich`；
- AI SDK/工具：`openai/openai-python`、`anthropics/anthropic-sdk-python`、`eslint/eslint`、`vitest-dev/vitest`、`THU-MAIC/OpenMAIC`、`browser-use/video-use`。

OpenClaw、Pydantic、Ruff、Pytest、LangChain、LlamaIndex、Transformers、Codex、Continue、Open WebUI、pnpm 和 Gitea 等大型或重依赖项目已从默认池移除；需要时仍可放入自定义 seed 扫描。

池中的 `stars_snapshot` 带日期，仅用于说明项目影响力。每次扫描会重新读取 stars、许可证、活跃时间、仓库大小和开放 Issue，不应把旧快照当成实时数据。

候选池不是白名单。也可以加入：

1. GitHub Trending 日榜和周榜；
2. 近 6–24 个月创建、约 2k–50k stars 的活跃项目；
3. 你正在使用的依赖及相邻生态；
4. 有 `good first issue`、`help wanted`、`bug` 或 `ready for work` 标签的项目；
5. 最近真实合并过外部贡献者 PR 的项目。

## 快速开始

### 1. 扫描候选池

```bash
python3 <skill-dir>/scripts/contribution_radar.py scan --max-repos 12 --max-issues 5 --output contribution-report.json --markdown contribution-report.md
```

按语言缩小范围：

```bash
python3 <skill-dir>/scripts/contribution_radar.py scan --language Python --max-repos 20
```

`--language` 先按候选池中的语言字段缩小 API 请求范围，再用实时仓库元数据确认结果。报告文件已存在时，脚本默认拒绝覆盖；确认需要更新时显式添加 `--force`。

单独查看某个项目：

```bash
python3 <skill-dir>/scripts/contribution_radar.py inspect OWNER/REPO --max-issues 10
```

扫描器先按本机工具链、准备成本和难度决定要请求哪些仓库，再从标签候选及近期无标签的故障型 Issue 中挑选线索。报告顶部只给出一个 `needs_verification` 推荐；缺少必需命令、平台不兼容、已关联 PR、过旧、破坏性 API 变更或低价值元数据事项不会进入该推荐。

报告里的“线索分”只用于排序，不能证明 Issue 仍然有效、没人处理或已经适合提交。选中目标后必须继续执行下面的门禁。

### 1.1 收敛为一个真实机会

脚本给出的唯一推荐只是待验证起点。Agent 必须按排名逐个做以下检查，直到恰好一个候选通过；失败项立即记录原因并换下一个，不要同时铺开多个实现：

1. 对照 `local_environment` 和仓库 `setup`，再核对实际测试命令、包管理器版本、磁盘、OS/架构以及是否需要浏览器、Docker、GPU、账号或云服务。
2. 阅读 Issue 正文、全部评论、关联 PR 与当前默认分支代码；开放 Issue 不代表缺陷仍存在。
3. 在未改生产代码的干净 checkout 上运行最小复现。无法 RED、已有实现或需要本机缺失条件时淘汰。
4. 对通过者执行完整查重和政策检查，只保留一个最终机会，并记录仓库、Issue、默认分支 SHA、复现命令和本机适配依据。

最终对用户只能称通过以上检查的对象为“已选贡献机会”。脚本中的 `needs_verification` 只能称“待验证线索”。如果所有候选都失败，明确报告 0 个机会及各自失败门禁，不要硬选。

### 2. 搜索重复工作

先用报错文本、符号或根因关键词做宽搜索：

```bash
python3 <skill-dir>/scripts/contribution_radar.py duplicates OWNER/REPO "exact error or affected_symbol"
```

然后补充搜索：Issue 编号、文件名、模块名、相邻错误、开放与关闭 PR、最近默认分支提交。查重词只能包含普通错误摘要、符号名或文件名，不得粘贴凭据或加入 `repo:`、`is:`、`OR` 等查询操作符。标题不同但修改同一根因的 PR 仍然是重复项。

## 完整流程

### 第一步：固定当前事实

1. 读取仓库实时元数据、默认分支、许可证和最近更新时间。
2. 阅读目标 Issue 的完整正文、全部评论和关联 PR。
3. 冻结当前默认分支 SHA，后续复现和 diff 都以它为基准。
4. 记录实际查过的 URL、命令和结果；API 失败时标记“未知”，不要写成 0。

完成标准：目标仓库、Issue、默认分支 SHA 和证据链接都已明确。

### 第二步：执行六项准入门禁

任何一项失败，都停止当前候选并换下一个：

1. **项目可贡献**：未归档，有明确许可证，近期活跃，真实接收外部 PR。
2. **政策允许**：已阅读 `CONTRIBUTING*`、`CODE_OF_CONDUCT*`、`SECURITY*`、`AGENTS.md`、Issue/PR 模板和 AI 使用政策。
3. **问题可验证**：Issue 给出了具体症状或复现路径；克隆后必须在最新默认分支上确认，不能只相信标题。
4. **没有重复工作**：开放/关闭 Issue、PR、最近提交和当前代码都未覆盖同一根因。
5. **本地可验证**：先核对报告的 `local_environment` 与仓库 `setup`；不需要缺失的命令、私有服务、付费 API、GPU、大模型权重、超大数据集或无法获得的平台。
6. **改动有用户价值**：修复正确性、可靠性、兼容性、安装或会导致错误使用的文档；拒绝纯 typo、徽章和无关格式化。

优先选择：影响可见、根因清晰、修改范围小、能写回归测试、维护者明确欢迎的问题。

### 第三步：确认 Issue 所有权与公开互动规则

- 优先处理未分配且维护者标记可贡献的现有 Issue。
- 已分配、已有活跃 PR 或评论中有人明确认领时，默认跳过。
- 只有项目政策要求时才先留言申请；不要批量发送“我可以做吗”。
- 行为修改优先由现有 Issue 承载。若项目允许无 Issue PR，可在 PR 中给出完整复现和前后行为，不要为了流程制造空洞 Issue。
- 项目要求 AI 辅助披露时，按指定位置和格式如实披露；项目禁止 AI 生成 Issue/PR 时停止自动发布。

完成标准：公开互动方式符合该仓库规则，且不会制造重复或噪声。

### 第四步：建立只读上游工作区

先读取默认分支和当前 GitHub 账号，并把结果记为 `<DEFAULT_BRANCH>` 与 `<GITHUB_USER>`：

```bash
gh repo view OWNER/REPO --json defaultBranchRef --jq ".defaultBranchRef.name"
gh api user --jq ".login"
git clone --filter=blob:none --depth 1 https://github.com/OWNER/REPO.git
cd REPO
git remote rename origin upstream
git fetch upstream
git checkout -b fix/short-description upstream/<DEFAULT_BRANCH>
```

此时不要创建 fork。先在只读上游副本中完成复现和验证，避免失败候选留下无价值 fork。如果目录已经存在，先检查 remotes、当前分支和未提交改动，不要覆盖工作区。默认不拉取 LFS 和 submodule。

完成标准：工作树干净，`HEAD` 来自最新 upstream 默认分支，尚未对 GitHub 远端执行写操作。

### 第五步：先复现，再修改

1. 阅读受影响模块、相邻测试、构建文件和项目规定的测试命令。
2. 只安装最小依赖，优先使用项目已有虚拟环境或包管理器。
3. 写最小回归测试或确定性复现脚本。
4. 在修改生产代码前运行一次，保存失败结果（RED）；同时运行相关原生测试并记录已有失败基线。
5. 如果当前默认分支无法复现，停止；不要修复猜测。

文档、安装器或 CLI 元数据问题可以用确定性命令输出、链接检查或路径验证代替永久单元测试，但必须能展示修改前失败、修改后成功。

完成标准：有同一条命令可以稳定证明修改前的问题。

### 第六步：做最小完整修复

- 只改根因、回归测试和项目明确要求的文档/变更记录。
- 遵循原项目的命名、格式和抽象，不做顺手重构。
- 不新增依赖，除非修复无法在现有依赖内完成。
- 不修改凭据、认证、生产基础设施、恶意载荷或真实用户数据。
- 先跑原失败用例（GREEN），再跑与修改前相同的基线命令、相邻测试、格式化、lint、类型检查和可承受范围内的更广测试。已有失败必须保持不变并解释；任何新增失败都阻止发布。

完成标准：同一复现从失败变为成功，相关检查通过，diff 中没有无关文件。

### 第七步：独立审查最终 diff

先只暂存本次允许提交的文件，不要使用无法核对范围的全量暂存。独立审查必须基于 Git index，而不是只看尚未包含工作树修改的 `HEAD`：

```bash
git add <changed-files>
git diff --check
git status --short
git diff --cached --stat
git diff --cached
```

确认 `git status --short` 中没有漏掉的目标文件或无关文件。审查重点：边界条件、安全、兼容性、测试是否真正覆盖失败、是否泄漏秘密、是否误提交生成物，以及 PR 声称的测试是否都真实运行。必须让另一个 Agent 只读审查 `git diff --cached`；如果无法委派，则执行一次独立的结构化复审，逐项检查安全、逻辑、测试和范围，任何阻塞项都必须先修复。审查后若文件发生变化，重新暂存并重新审查。

发布前再次拉取 upstream，并重新搜索重复项。高活跃仓库的状态可能在实现期间发生变化。

完成标准：工作树干净，无阻塞审查意见，目标问题仍未被别人解决。

### 第八步：提交并创建 PR

这是首次远端写操作。执行前必须向用户确认：目标上游仓库、当前 `gh` 登录账号、将创建或复用的 fork、分支名，以及将执行 push 和 PR 创建。未获得明确授权时停在本地已验证状态。

授权后创建个人 fork，并把它设为 `origin`：

```bash
gh repo fork OWNER/REPO --clone=false
git remote add origin https://github.com/<GITHUB_USER>/REPO.git
git remote -v
```

如果 `origin` 已存在，先核对它确实属于 `<GITHUB_USER>`，不要覆盖已有 remote。提交信息遵循项目习惯；没有明确规范时使用简洁的 Conventional Commit：

```bash
git commit -m "fix(scope): describe the user-visible outcome"
git push -u origin HEAD
```

push 后、创建 PR 前，先运行 `git rev-parse HEAD` 取得 `<LOCAL_SHA>`，再回读 fork：

```bash
gh api repos/<GITHUB_USER>/REPO/commits/<LOCAL_SHA> --jq "{sha:.sha,author:.author.login,committer:.committer.login}"
```

要求返回的 SHA 与本地一致，且 `author` 和 `committer` 都与 `<GITHUB_USER>` 一致；如果 GitHub 没有关联该提交身份，先修复提交身份并重新提交，不要继续创建 PR。

优先使用仓库的 PR 模板。没有模板时使用：

```markdown
## Summary
- 修复了什么可观察问题
- 为什么这是最小改动

## Reproduction
- Before: `<命令>` → `<失败现象>`
- After: `<同一命令>` → `<通过结果>`

## Tests
- `<实际运行的命令>` — `<结果>`

Fixes #ISSUE
```

只有真正完整解决现有 Issue 时才写 `Fixes #ISSUE`。PR 正文只写问题、影响、修复和测试，不写 Agent 内部流程、候选评分、私有路径或未运行的检查。

把完整正文保存为 `pr-body.md`，再用显式标题和正文文件非交互创建：

```bash
gh pr create --repo OWNER/REPO --base <DEFAULT_BRANCH> --head <GITHUB_USER>:<BRANCH> --title "fix(scope): concise user-visible outcome" --body-file pr-body.md
```

命令会返回 PR URL。后续命令中的 `<PR_URL>` 必须替换为该返回值。完成标准：PR 已存在于上游仓库，远端 head SHA 与本地 `HEAD` 一致。

### 第九步：回读并跟进

```bash
gh pr view <PR_URL> -R OWNER/REPO --json number,url,state,isDraft,mergeable,mergeStateStatus,headRefOid,files,statusCheckRollup
gh pr checks <PR_URL> -R OWNER/REPO
```

- `pending`、`skipped`、`action_required` 都不等于通过。
- CI 因补丁失败时，读取日志、做最小修复并重新验证；最多两轮，之后报告阻塞。
- 基础设施失败、缺少上游 secret、审批门禁或主分支本身失败时，不要改代码掩盖。
- 收到 review 后读取完整线程，修复有效问题，回复并回读远端状态。
- 不要自行合并上游 PR，除非你同时是该项目维护者且得到明确授权。

完成标准：PR URL、head SHA、文件列表、合并状态和 CI 状态均已回读确认。

## 选择问题的方法

标签只是入口，真正有价值的问题常在这些位置：

1. 最近更新但没有标签、标题含明确失败症状的 bug；
2. 关闭但未修复的 Issue，以及关闭时留下的后续方向；
3. 长期停滞或被放弃的 PR 中仍可复现的问题；
4. 同一模块反复出现的错误、超时、路径、编码、状态同步或平台兼容问题；
5. 安装、示例和文档中会让用户执行错误命令的内容；
6. 测试和实现之间不一致的边界行为；
7. 最近提交引入、可用 `git bisect` 或小测试定位的回归。

搜索至少覆盖：Issue 编号、完整错误文本、函数/类名、文件路径、配置键、协议字段和根因词。必须阅读相近 PR 的最新 diff；原始标题和正文可能已经过时。

## 资源与时间控制

- 扫描阶段最多 10–15 分钟；单个候选在 20 分钟内没有得到失败复现就换目标。
- 默认只做一个 PR；第二个必须独立通过全部门禁。
- 避免无目标地克隆大型 monorepo。先读元数据、Issue 和贡献指南，再决定是否克隆。
- 预留至少三分之一时间给测试、diff 审查、推送、PR 回读和 CI。
- 没有合适问题时可以提交 0 个 PR，但要说明每个强候选失败在哪个门禁。

## 常见陷阱

1. **把高 stars 当成容易贡献。** 大项目常有饱和队列和复杂测试，影响力不能替代可验证性。
2. **只搜开放 PR。** 已关闭 PR、最近提交和 Issue 评论也可能证明工作重复。
3. **相信标签。** `good first issue` 可能已过期、已分配或需要私有环境。
4. **先改代码再复现。** 没有 RED 证据，很难证明修复的是当前问题。
5. **把 API 失败当成零。** 网络、限流或 SSO 失败必须写“未知”。
6. **为了数量做低价值修改。** typo、徽章和无关格式化会消耗维护者时间。
7. **在 PR 中泄漏内部信息。** 删除绝对路径、Token、日志凭据、模型名和私有记录。
8. **只看 CLI 退出码。** push、PR 和评论都要通过 GitHub API 回读目标对象。

## 验收清单

- [ ] `doctor` 通过，GitHub 身份与 Git 提交身份明确。
- [ ] 仓库未归档，许可证和贡献政策已确认。
- [ ] 问题在最新默认分支上可复现。
- [ ] 开放/关闭 Issue、PR、提交和当前代码均已查重。
- [ ] 问题未分配，或维护者明确允许参与。
- [ ] 修改有用户价值，不是凑数内容。
- [ ] 同一回归在修改前失败、修改后通过。
- [ ] 项目要求的聚焦测试和静态检查通过。
- [ ] 最终 diff 已独立审查且无秘密、无无关文件。
- [ ] PR 遵循模板和 AI 披露规则，测试声明真实。
- [ ] PR URL、head SHA、文件和 CI 已从上游回读。
